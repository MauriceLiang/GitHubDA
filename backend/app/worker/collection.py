"""Windowed activity collection with durable per-page checkpoints."""
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient, PageObservation, PaginatedResult
from backend.app.persistence.models import CollectionCheckpoint, CollectionTask
from backend.app.pipeline.collection_archive import clear_page_files, page_paths, read_page, scope_fingerprint, trim_page_files, write_page
from backend.app.pipeline.event_normalizer import normalize_events
from backend.app.services.insights import MODULES
from backend.app.worker.progress import TaskProgressReporter
from backend.app.worker.telemetry import log_module_timing, log_page_progress


logger = logging.getLogger(__name__)


def collect_deep(
    github: GitHubClient,
    full_name: str,
    start,
    end,
    task: CollectionTask,
    reporter: TaskProgressReporter | None,
    session_factory,
    *,
    query_start=None,
) -> tuple[dict[str, Any], str, object | None]:
    query_start = query_start or start
    start_iso = iso_z(start)
    end_iso = iso_z(end)
    query_start_iso = iso_z(query_start)
    data: dict[str, dict[str, dict[str, Any]]] = {}
    event_counts: dict[str, dict[str, int]] = {}
    raw: dict[str, Any] = {}
    coverage: dict[str, str] = {}
    sources: dict[str, dict] = {}
    deferred_until = None
    budget_yielded = False

    for name in MODULES:
        module_started = time.monotonic()
        relevant_start = end - timedelta(days=365) if name == "releases" else start
        query = _query(name, query_start_iso, end_iso)
        relevant_start_iso = iso_z(relevant_start)
        checkpoint_scope = {"api_query": query, "scope_kind": task.scope_kind, "query_start": query_start_iso}
        fingerprint = scope_fingerprint(task.repository_id, name, checkpoint_scope, relevant_start_iso, end_iso)
        checkpoint = _get_checkpoint(session_factory, task.repository_id, name, fingerprint)
        paths = page_paths(task.repository_id, name, fingerprint)

        ordered_paths = all(Path(path).name == f"page-{index:06d}.json.gz" for index, path in enumerate(paths, start=1))
        if not ordered_paths or checkpoint["pages_fetched"] > len(paths):
            clear_page_files(task.repository_id, name, fingerprint)
            paths = []
            checkpoint = _reset_checkpoint(session_factory, task, name, fingerprint, relevant_start, end)
        elif checkpoint["pages_fetched"] < len(paths):
            paths = trim_page_files(task.repository_id, name, fingerprint, checkpoint["pages_fetched"])
            if checkpoint["pages_fetched"] and len(paths) != checkpoint["pages_fetched"]:
                clear_page_files(task.repository_id, name, fingerprint)
                paths = []
                checkpoint = _reset_checkpoint(session_factory, task, name, fingerprint, relevant_start, end)
        data[name] = {}
        event_counts[name] = _empty_event_counts()
        try:
            for path in paths:
                page = read_page(path)
                _append_normalized_page(name, page["raw_response"], data[name], event_counts[name])
        except (OSError, ValueError):
            logger.warning("Collection page archive is invalid; restarting scope task_id=%s module=%s", task.task_id, name)
            clear_page_files(task.repository_id, name, fingerprint)
            paths = []
            checkpoint = _reset_checkpoint(session_factory, task, name, fingerprint, relevant_start, end)
            data[name] = {}
            event_counts[name] = _empty_event_counts()

        page_cap = getattr(github, "max_pages", None)
        invalid_events = bool(event_counts[name]["rejected_records"] or event_counts[name]["invalid_event_times"])
        if checkpoint["status"] == "complete":
            module_coverage = "partial" if invalid_events else "complete"
            module_error = "INVALID_EVENT_RECORDS" if invalid_events else None
            if reporter:
                reporter.begin_module(name, page_cap, pages_fetched=checkpoint["pages_fetched"], observed_items=checkpoint["records_written"])
                reporter.finish_module(name, status="partial" if invalid_events else "complete", coverage=module_coverage, elapsed_seconds=0, error_code=module_error)
            result = PaginatedResult([], [], True, 0, 0, False)
        elif deferred_until is not None:
            coverage[name] = "deferred"
            raw[name] = {"page_files": paths, "error": "GITHUB_RATE_LIMITED", "message": "前一个接口受到限流，等待配额恢复后继续"}
            source_start_iso = relevant_start_iso if name == "releases" else query_start_iso
            sources[name] = _source(name, full_name, query, source_start_iso, end_iso, checkpoint, page_cap, coverage[name], error_code="GITHUB_RATE_LIMITED", deferred_until=deferred_until)
            if reporter:
                reporter.begin_module(name, page_cap, pages_fetched=checkpoint["pages_fetched"], observed_items=checkpoint["records_written"])
                reporter.finish_module(name, status="skipped", coverage="deferred", elapsed_seconds=time.monotonic() - module_started, error_code="GITHUB_RATE_LIMITED")
            continue
        else:
            if reporter:
                reporter.begin_module(name, page_cap, pages_fetched=checkpoint["pages_fetched"], observed_items=checkpoint["records_written"])
            _mark_checkpoint_running(session_factory, task, name, fingerprint, relevant_start, end)

            def on_page(observation: PageObservation, module=name, scope=fingerprint, collected_paths=paths) -> None:
                page_body = observation.raw_body or json.dumps(observation.records, ensure_ascii=False)
                relative_path, _digest = write_page(
                    task.repository_id, module, scope, observation.page_index,
                    observation.records, page_body, observation.request_url or f"/repos/{full_name}/{module}", observation.http_status,
                )
                collected_paths.append(relative_path)
                _append_normalized_page(module, observation.records, data[module], event_counts[module])
                _save_checkpoint_page(
                    session_factory, task, module, scope, relevant_start, end,
                    observation, relative_path,
                )
                if reporter:
                    reporter.page_fetched(module, observation.pages_fetched, observation.observed_items)
                log_page_progress(
                    task_id=task.task_id,
                    repository_id=task.repository_id,
                    module=module,
                    page_index=observation.page_index,
                    pages_fetched=observation.pages_fetched,
                    observed_items=observation.observed_items,
                    duration_ms=observation.duration_ms,
                    has_next=observation.has_next,
                )

            try:
                fetch = getattr(github, f"list_{name}_detailed", None)
                if fetch:
                    stop_after_page = None
                    if name == "pulls":
                        def stop_after_old_pull_page(records: list[dict[str, Any]]) -> bool:
                            updated = [parse_github_datetime(item.get("updated_at")) for item in records]
                            return bool(updated and all(value is not None for value in updated) and max(updated) < query_start)

                        stop_after_page = stop_after_old_pull_page
                    result = fetch(
                        full_name,
                        *([query_start_iso, end_iso] if name == "commits" else [query_start_iso, "all"] if name == "issues" else ["closed"] if name == "pulls" else []),
                        on_page=on_page,
                        resume_url=checkpoint["next_url"] if checkpoint["pages_fetched"] else None,
                        page_offset=checkpoint["pages_fetched"],
                        records_offset=checkpoint["records_written"],
                        collect_items=False,
                        collect_raw_pages=False,
                        stop_after_page=stop_after_page,
                    )
                    if result.items:
                        _append_normalized_page(name, result.items, data[name], event_counts[name])
                else:
                    legacy = getattr(github, f"list_{name}")
                    legacy_args = [full_name, query_start_iso, end_iso] if name == "commits" else [full_name, query_start_iso, "all"] if name == "issues" else [full_name, "closed"] if name == "pulls" else [full_name]
                    rows, complete, raw_pages = legacy(*legacy_args)
                    _append_normalized_page(name, rows, data[name], event_counts[name])
                    result = PaginatedResult(rows, raw_pages, complete, len(raw_pages), len(rows), not complete)
            except AppError as exc:
                result = PaginatedResult([], [], False, 0, 0, True, error_code=exc.code, error_message=exc.message, error_status_code=exc.status_code, error_details=dict(exc.details))

            checkpoint = _get_checkpoint(session_factory, task.repository_id, name, fingerprint)
            invalid_events = bool(event_counts[name]["rejected_records"] or event_counts[name]["invalid_event_times"])
            limit_reached = bool(result.has_next and result.error_code is None and page_cap is not None and result.pages_fetched == page_cap)
            if result.error_code == "GITHUB_RATE_LIMITED":
                retry_after = result.error_details.get("retry_after_seconds")
                backoff = retry_after if isinstance(retry_after, int) and retry_after > 0 else min(3600, 60 * (2 ** min(max(task.attempt - 1, 0), 5)))
                deferred_until = utc_now() + timedelta(seconds=backoff)
                _finish_checkpoint(session_factory, task, name, fingerprint, "deferred", deferred_until, result.error_code)
                module_coverage = "deferred"
            elif result.error_code is None and result.complete:
                _finish_checkpoint(session_factory, task, name, fingerprint, "complete", None, "INVALID_EVENT_RECORDS" if invalid_events else None)
                module_coverage = "partial" if invalid_events else "complete"
            elif limit_reached:
                _finish_checkpoint(session_factory, task, name, fingerprint, "budget_exhausted", None, "GITHUB_MAX_PAGES")
                module_coverage = "budget_exhausted"
                budget_yielded = task.scope_kind == "backfill" or budget_yielded
            else:
                _finish_checkpoint(session_factory, task, name, fingerprint, "partial", None, result.error_code or "GITHUB_INCOMPLETE_PAGINATION")
                module_coverage = "partial"
            coverage[name] = module_coverage
            checkpoint = _get_checkpoint(session_factory, task.repository_id, name, fingerprint)
            source_error = result.error_code or ("GITHUB_MAX_PAGES" if limit_reached else "GITHUB_INCOMPLETE_PAGINATION" if result.has_next else "INVALID_EVENT_RECORDS" if invalid_events else None)
            source_start_iso = relevant_start_iso if name == "releases" else query_start_iso
            sources[name] = _source(name, full_name, query, source_start_iso, end_iso, checkpoint, page_cap, module_coverage, error_code=source_error, deferred_until=deferred_until)
            raw[name] = {"page_files": paths}
            if source_error:
                raw[name].update({"error": source_error, "message": result.error_message or ("达到用户设置的页数预算，仍有后续页面" if limit_reached else "分页尚未完成")})
            module_status = "complete" if module_coverage == "complete" else "skipped" if module_coverage == "deferred" else "partial" if checkpoint["pages_fetched"] else "failed"
            if reporter:
                reporter.finish_module(name, status=module_status, coverage=module_coverage, elapsed_seconds=time.monotonic() - module_started, error_code=source_error)
            log_module_timing(
                task_id=task.task_id,
                repository_id=task.repository_id,
                module=name,
                http_calls=result.http_calls,
                pages_fetched=result.pages_fetched,
                observed_items=result.observed_items,
                duration_ms=result.duration_ms or (time.monotonic() - module_started) * 1000,
                coverage=module_coverage,
                error_code=source_error,
                rate_limited_count=result.rate_limited_count,
                timeout_count=result.timeout_count,
            )
            continue

        coverage[name] = module_coverage
        source_start_iso = relevant_start_iso if name == "releases" else query_start_iso
        sources[name] = _source(name, full_name, query, source_start_iso, end_iso, checkpoint, page_cap, module_coverage, error_code=module_error)
        raw[name] = {"page_files": paths}

    normalized_data = {module: list(rows.values()) for module, rows in data.items()}
    for module in MODULES:
        counts = event_counts[module]
        sources[module].update(counts)

    raw["_meta"] = {"schema_version": 2, "sources": sources, "window_start": start_iso, "window_end": end_iso}

    def in_window(value: str | datetime | None, lower=start, upper=end) -> bool:
        from backend.app.pipeline.event_normalizer import event_date

        parsed = value if isinstance(value, datetime) else event_date(value)
        return parsed is not None and lower <= parsed < upper

    issues = normalized_data["issues"]
    pulls = normalized_data["pulls"]
    releases = normalized_data["releases"]
    release_start = end - timedelta(days=365)
    values = {
        "commits_count": len(normalized_data["commits"]) if coverage["commits"] == "complete" else None,
        "issues_opened_count": sum(in_window(item.get("created_at")) for item in issues) if coverage["issues"] == "complete" else None,
        "issues_closed_count": sum(in_window(item.get("closed_at")) for item in issues) if coverage["issues"] == "complete" else None,
        "pulls_opened_count": sum(in_window(item.get("created_at")) for item in pulls) if coverage["pulls"] == "complete" else None,
        "pulls_merged_count": sum(in_window(item.get("merged_at")) for item in pulls) if coverage["pulls"] == "complete" else None,
        "releases_count": sum(in_window(item.get("published_at"), release_start, end) for item in releases) if coverage["releases"] == "complete" else None,
    }
    values["coverage_by_module"] = {
        "commits_count": coverage["commits"],
        "issues_closed_count": coverage["issues"],
        "pulls_merged_count": coverage["pulls"],
        "releases_count": coverage["releases"],
    }
    values["coverage"] = "complete" if all(value == "complete" for value in coverage.values()) else "partial"
    values["raw"] = raw
    values["events"] = normalized_data
    values["event_counts"] = event_counts
    values["sources"] = sources
    if deferred_until is None and budget_yielded:
        deferred_until = utc_now() + timedelta(seconds=10)
    values["deferred_until"] = deferred_until
    values["defer_reason"] = "rate_limit" if any(source.get("error_code") == "GITHUB_RATE_LIMITED" for source in sources.values()) else "page_budget" if budget_yielded else None
    return values, values["coverage"], deferred_until


def _empty_event_counts() -> dict[str, int]:
    return {
        "observed_records": 0,
        "accepted_events": 0,
        "rejected_records": 0,
        "invalid_event_times": 0,
        "filtered_pr_records": 0,
        "duplicate_records": 0,
    }


def _append_normalized_page(module: str, rows: list[dict[str, Any]], events: dict[str, dict[str, Any]], counts: dict[str, int]) -> None:
    normalized, page_counts = normalize_events(module, rows)
    for key in ("observed_records", "rejected_records", "invalid_event_times", "filtered_pr_records", "duplicate_records"):
        counts[key] += page_counts[key]
    for event in normalized:
        source_id = event["source_item_id"]
        if source_id in events:
            counts["duplicate_records"] += 1
        events[source_id] = event
    counts["accepted_events"] = len(events)


def _query(module: str, start_iso: str, end_iso: str) -> dict:
    if module == "commits":
        return {"since": start_iso, "until": end_iso}
    if module == "issues":
        return {"state": "all", "since": start_iso, "since_semantics": "updated_at"}
    if module == "pulls":
        return {"state": "closed", "sort": "updated", "direction": "desc"}
    return {}


def _get_checkpoint(session_factory, repository_id: int, module: str, fingerprint: str) -> dict:
    with session_factory() as session:
        row = session.get(CollectionCheckpoint, (repository_id, module, fingerprint))
        if row is None:
            return {"pages_fetched": 0, "records_written": 0, "status": "pending", "next_url": None}
        return {
            "pages_fetched": row.pages_fetched,
            "records_written": row.records_written,
            "status": row.status,
            "next_url": row.next_url,
        }


def _reset_checkpoint(session_factory, task, module, fingerprint, start, end) -> dict:
    with session_factory() as session:
        row = session.get(CollectionCheckpoint, (task.repository_id, module, fingerprint))
        now = utc_now()
        if row is None:
            row = CollectionCheckpoint(repository_id=task.repository_id, module=module, scope_fingerprint=fingerprint, window_start=start, window_end=end)
            session.add(row)
        row.task_id = task.task_id
        row.pages_fetched = row.records_written = 0
        row.next_url = row.last_seen_key = row.error_code = None
        row.status = "pending"
        row.resume_after = None
        row.updated_at = now
        session.commit()
    return {"pages_fetched": 0, "records_written": 0, "status": "pending", "next_url": None}


def _mark_checkpoint_running(session_factory, task, module, fingerprint, start, end) -> None:
    with session_factory() as session:
        row = session.get(CollectionCheckpoint, (task.repository_id, module, fingerprint))
        if row is None:
            row = CollectionCheckpoint(repository_id=task.repository_id, module=module, scope_fingerprint=fingerprint, window_start=start, window_end=end)
            session.add(row)
        row.task_id = task.task_id
        row.status = "running"
        row.resume_after = None
        row.error_code = None
        row.updated_at = utc_now()
        session.commit()


def _save_checkpoint_page(session_factory, task, module, fingerprint, start, end, observation: PageObservation, _relative_path: str) -> None:
    with session_factory() as session:
        row = session.get(CollectionCheckpoint, (task.repository_id, module, fingerprint))
        if row is None:
            row = CollectionCheckpoint(repository_id=task.repository_id, module=module, scope_fingerprint=fingerprint, window_start=start, window_end=end)
            session.add(row)
        row.task_id = task.task_id
        row.pages_fetched = observation.pages_fetched
        row.records_written = observation.observed_items
        row.next_url = observation.next_url
        rows = observation.records
        row.last_seen_key = _last_key(module, rows[-1]) if rows else row.last_seen_key
        row.status = "running" if observation.has_next else "complete"
        row.resume_after = None
        row.updated_at = utc_now()
        session.commit()


def _finish_checkpoint(session_factory, task, module, fingerprint, status, resume_after, error_code) -> None:
    with session_factory() as session:
        row = session.get(CollectionCheckpoint, (task.repository_id, module, fingerprint))
        if row:
            row.status = status
            row.resume_after = resume_after
            row.error_code = error_code
            row.updated_at = utc_now()
            session.commit()


def _last_key(module: str, item: dict) -> str | None:
    value = item.get("sha") if module == "commits" else item.get("id")
    return str(value)[:100] if isinstance(value, (str, int)) else None


def _source(module, full_name, query, start_iso, end_iso, checkpoint, page_cap, coverage, *, error_code=None, deferred_until=None):
    return {
        "coverage": coverage,
        "collected_at": iso_z(utc_now()),
        "requested_interval": [start_iso, end_iso],
        "observed_interval": None,
        "page_count": checkpoint["pages_fetched"],
        "has_next": coverage != "complete",
        "page_cap": page_cap,
        "limit_reached": coverage == "budget_exhausted",
        "observed_records": checkpoint["records_written"],
        "rate_limit_status": "limited" if error_code == "GITHUB_RATE_LIMITED" else "not_observed",
        "error_code": error_code,
        "deferred_until": iso_z(deferred_until),
        "endpoint": f"/repos/{full_name}/{module}",
        "query": query,
    }

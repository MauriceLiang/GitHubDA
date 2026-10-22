import hashlib
import json
import math
from collections import Counter
from datetime import date, datetime, time, timedelta
from uuid import uuid4

from sqlalchemy import desc, or_, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from backend.app.analytics.insights import LIMITATIONS, calculate_insights
from backend.app.core.clock import iso_z, utc_now
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import Repository, RepositoryActivityEvent, RepositoryInsightRun
from backend.app.pipeline.collection_archive import iter_module_pages, iter_module_records
from backend.app.pipeline.event_normalizer import normalize_events
from backend.app.pipeline.raw_archive import read_archive

METRIC_VERSION = "insights-v1"
MODULES = ("commits", "issues", "pulls", "releases")
PAGE_LIMIT_NOTE = "已达到用户设置的接口页数预算；仍有后续页未采集，当前指标只反映已观察样本。"


def persist_insights(session: Session, repository_id: int, task_id: str, rows: dict, sources: dict, start, end, archive_paths: list[str], *, normalized_event_counts: dict | None = None, aggregate_from_store=False, version=METRIC_VERSION, origin="collection"):
    normalized, checked_sources = {}, {}
    for module in MODULES:
        if normalized_event_counts is None:
            normalized[module], counts = normalize_events(module, rows.get(module, []))
        else:
            normalized[module] = rows.get(module, [])
            counts = normalized_event_counts[module]
        source = {**sources.get(module, {"coverage": "not_collected"}), **counts}
        if (counts["rejected_records"] or counts["invalid_event_times"]) and source["coverage"] == "complete":
            source["coverage"] = "partial"
            source["error_code"] = "INVALID_EVENT_RECORDS"
        checked_sources[module] = source
    fingerprint_payload = json.dumps({"repository": repository_id, "task": task_id, "version": version, "start": iso_z(start), "end": iso_z(end), "events": normalized, "sources": checked_sources, "archives": archive_paths}, default=iso_z, sort_keys=True)
    fingerprint = hashlib.sha256(fingerprint_payload.encode()).hexdigest()
    existing = session.scalar(select(RepositoryInsightRun).where(RepositoryInsightRun.input_fingerprint == fingerprint))
    if existing:
        return json.loads(existing.result_json)
    now = utc_now()
    # Same transaction as run and legacy snapshots. Never calculate from a mutable union
    # of historical observations; this run uses only its own collected inputs.
    for events in normalized.values():
        for offset in range(0, len(events), 250):
            batch = [{**e, "repository_id": repository_id, "source_task_id": task_id, "first_seen_at": now, "last_seen_at": now} for e in events[offset:offset + 250]]
            if batch:
                statement = insert(RepositoryActivityEvent).values(batch)
                mutable = {key: getattr(statement.excluded, key) for key in batch[0] if key not in {"repository_id", "event_type", "source_item_id", "first_seen_at"}}
                session.execute(statement.on_conflict_do_update(index_elements=["repository_id", "event_type", "source_item_id"], set_=mutable))
    source_task_ids = [task_id]
    if aggregate_from_store:
        normalized = _stored_window_events(session, repository_id, start, end)
        prior_runs = session.scalars(select(RepositoryInsightRun).where(
            RepositoryInsightRun.repository_id == repository_id,
            RepositoryInsightRun.metric_version == version,
            RepositoryInsightRun.window_end >= start,
            RepositoryInsightRun.window_start <= end,
        )).all()
        for prior in prior_runs:
            try:
                prior_task_ids = json.loads(prior.source_task_ids_json)
                prior_archives = json.loads(prior.source_archive_paths_json)
            except (TypeError, ValueError):
                continue
            if isinstance(prior_task_ids, list):
                source_task_ids.extend(item for item in prior_task_ids if isinstance(item, str))
            if isinstance(prior_archives, list):
                archive_paths.extend(item for item in prior_archives if isinstance(item, str))
        source_task_ids = list(dict.fromkeys(source_task_ids))
        archive_paths = list(dict.fromkeys(archive_paths))
        for source in checked_sources.values():
            source["calculation_basis"] = "local_unique_event_store"
    metrics = calculate_insights(normalized, checked_sources, start, end)
    states = [m["quality"]["status"] for m in metrics.values()]
    status = "missing" if all(s == "missing" for s in states) else "partial" if any(s in {"partial", "missing", "failed"} for s in states) else "ready"
    limitations = list(LIMITATIONS)
    if any(source.get("limit_reached") for source in checked_sources.values()):
        limitations.append(PAGE_LIMIT_NOTE)
    if not archive_paths:
        limitations.append("原始归档不可用；本次统计及事件仍保留，但原始响应的可复核性下降。")
    observed_counts = _observed_event_counts(normalized, start, end)
    result = {"repository_id": repository_id, "run_id": str(uuid4()), "metric_version": version, "status": status, "window_start": iso_z(start), "window_end": iso_z(end), "timezone": "UTC", "analyzed_at": iso_z(now), "source_task_ids": source_task_ids, "source_archive_paths": archive_paths, "origin": origin, "sources": checked_sources, "insights": metrics, "observed_counts": observed_counts, "limitations": limitations}
    session.add(RepositoryInsightRun(run_id=result["run_id"], input_fingerprint=fingerprint, repository_id=repository_id, metric_version=version, window_start=start, window_end=end, analyzed_at=now, source_task_ids_json=json.dumps(source_task_ids), source_archive_paths_json=json.dumps(archive_paths), module_coverage_json=json.dumps(checked_sources), status=status, limitations_json=json.dumps(limitations, ensure_ascii=False), result_json=json.dumps(result, ensure_ascii=False)))
    session.flush()
    return result


def _stored_window_events(session: Session, repository_id: int, start, end) -> dict[str, list[dict]]:
    release_start = end - timedelta(days=365)
    ranges = {
        "commit": (RepositoryActivityEvent.event_at >= start) & (RepositoryActivityEvent.event_at < end),
        "issue": or_(
            (RepositoryActivityEvent.created_at >= start) & (RepositoryActivityEvent.created_at < end),
            (RepositoryActivityEvent.closed_at >= start) & (RepositoryActivityEvent.closed_at < end),
            (RepositoryActivityEvent.updated_at >= start) & (RepositoryActivityEvent.updated_at < end),
        ),
        "pull_request": or_(
            (RepositoryActivityEvent.created_at >= start) & (RepositoryActivityEvent.created_at < end),
            (RepositoryActivityEvent.closed_at >= start) & (RepositoryActivityEvent.closed_at < end),
            (RepositoryActivityEvent.merged_at >= start) & (RepositoryActivityEvent.merged_at < end),
            (RepositoryActivityEvent.updated_at >= start) & (RepositoryActivityEvent.updated_at < end),
        ),
        "release": (RepositoryActivityEvent.published_at >= release_start) & (RepositoryActivityEvent.published_at < end),
    }
    module_by_type = {"commit": "commits", "issue": "issues", "pull_request": "pulls", "release": "releases"}
    events = {module: [] for module in MODULES}
    for event_type, predicate in ranges.items():
        stored = session.scalars(select(RepositoryActivityEvent).where(
            RepositoryActivityEvent.repository_id == repository_id,
            RepositoryActivityEvent.event_type == event_type,
            predicate,
        )).all()
        module = module_by_type[event_type]
        events[module] = [{
            "event_type": item.event_type,
            "source_item_id": item.source_item_id,
            "event_at": item.event_at,
            "created_at": item.created_at,
            "closed_at": item.closed_at,
            "merged_at": item.merged_at,
            "published_at": item.published_at,
            "updated_at": item.updated_at,
            "is_draft": item.is_draft,
            "is_prerelease": item.is_prerelease,
        } for item in stored]
    return events


def _observed_event_counts(events: dict[str, list[dict]], start, end) -> dict[str, int]:
    release_start = end - timedelta(days=365)

    def count(module, field, lower=start):
        return sum(1 for item in events[module] if item.get(field) is not None and lower <= item[field] < end)

    return {
        "commits_count": count("commits", "event_at"),
        "issues_opened_count": count("issues", "created_at"),
        "issues_closed_count": count("issues", "closed_at"),
        "pulls_opened_count": count("pulls", "created_at"),
        "pulls_merged_count": count("pulls", "merged_at"),
        "releases_count": count("releases", "published_at", release_start),
    }


def repository_insights(session, repository_id):
    if session.get(Repository, repository_id) is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    run = session.scalar(select(RepositoryInsightRun).where(RepositoryInsightRun.repository_id == repository_id, RepositoryInsightRun.metric_version == METRIC_VERSION).order_by(desc(RepositoryInsightRun.analyzed_at), desc(RepositoryInsightRun.run_id)).limit(1))
    if run:
        return json.loads(run.result_json)
    return {"repository_id": repository_id, "run_id": None, "metric_version": METRIC_VERSION, "status": "missing", "window_start": None, "window_end": None, "timezone": "UTC", "analyzed_at": None, "source_task_ids": [], "source_archive_paths": [], "origin": None, "sources": {}, "insights": {}, "limitations": ["尚无事件级分析。请采集活动数据，或通过本地命令安全回放已有归档；旧概况仍可查看。"]}


def repository_release_detail(session, repository_id, release_id):
    if session.get(Repository, repository_id) is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    run = session.scalar(select(RepositoryInsightRun).where(RepositoryInsightRun.repository_id == repository_id, RepositoryInsightRun.metric_version == METRIC_VERSION).order_by(desc(RepositoryInsightRun.analyzed_at), desc(RepositoryInsightRun.run_id)).limit(1))
    if run is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "尚无可读取 Release 说明的采集归档")
    for archive_path in json.loads(run.source_archive_paths_json):
        if not isinstance(archive_path, str):
            continue
        try:
            archive = read_archive(archive_path)
        except FileNotFoundError:
            continue
        try:
            for item in iter_module_records(archive.get("releases")):
                if item.get("id") == release_id:
                    return {
                        "id": str(release_id),
                        "name": item.get("name") if isinstance(item.get("name"), str) else None,
                        "body": item.get("body") if isinstance(item.get("body"), str) else None,
                    }
        except (OSError, ValueError, TypeError):
            continue
    raise AppError(404, "RESOURCE_NOT_FOUND", "当前采集归档中没有该 Release 说明，请重新采集仓库数据")


def repository_commit_activity(session, repository_id, *, page=1, per_page=20, search=None, week_start: date | None = None):
    """Return itemized commits and derived summaries from the latest saved archive."""
    repository = session.get(Repository, repository_id)
    if repository is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    run = session.scalar(select(RepositoryInsightRun).where(
        RepositoryInsightRun.repository_id == repository_id,
        RepositoryInsightRun.metric_version == METRIC_VERSION,
    ).order_by(desc(RepositoryInsightRun.analyzed_at), desc(RepositoryInsightRun.run_id)).limit(1))
    if run is None:
        return {
            "available": False,
            "coverage": {"state": "missing", "label": "尚无逐条数据", "detail": "请先采集仓库 Commit 数据"},
            "note": "尚无可读取的 Commit 采集归档。",
            "window_start": None,
            "window_end": None,
            "commit_count": 0,
            "author_count": 0,
            "daily_counts": [],
            "authors": [],
            "items": [],
            "total": 0,
        }

    try:
        task_ids = json.loads(run.source_task_ids_json)
        archive_paths = json.loads(run.source_archive_paths_json)
        module_coverage = json.loads(run.module_coverage_json).get("commits", {}).get("coverage", "not_collected")
    except (TypeError, ValueError, AttributeError) as exc:
        raise AppError(503, "COMMIT_ARCHIVE_UNAVAILABLE", "Commit 采集记录无法读取，请重新采集仓库数据") from exc
    task_ids = task_ids if isinstance(task_ids, list) else []
    archive_paths = archive_paths if isinstance(archive_paths, list) else []

    events = session.scalars(select(RepositoryActivityEvent).where(
        RepositoryActivityEvent.repository_id == repository_id,
        RepositoryActivityEvent.event_type == "commit",
        RepositoryActivityEvent.source_task_id.in_(task_ids) if task_ids else RepositoryActivityEvent.source_task_id == "",
        RepositoryActivityEvent.event_at.is_not(None),
        RepositoryActivityEvent.event_at >= run.window_start,
        RepositoryActivityEvent.event_at < run.window_end,
    )).all()
    event_by_sha = {event.source_item_id: event for event in events}

    if week_start is not None:
        week_begin = datetime.combine(week_start, time.min)
        week_end = week_begin + timedelta(days=7)
        event_by_sha = {
            sha: event for sha, event in event_by_sha.items()
            if week_begin <= event.event_at < week_end
        }

    archive_found = False
    missing_archive = False
    records_by_sha = {}
    try:
        for archive_path in archive_paths:
            if not isinstance(archive_path, str):
                continue
            try:
                archive = read_archive(archive_path)
            except FileNotFoundError:
                missing_archive = True
                continue
            archive_found = True
            commit_archive = archive.get("commits")
            pages = iter_module_pages(commit_archive)
            for raw_page in pages:
                if isinstance(raw_page, str):
                    if len(raw_page) > 16_000_000:
                        raise ValueError("commit archive page exceeds size limit")
                    page_items = json.loads(raw_page)
                else:
                    page_items = raw_page
                if not isinstance(page_items, list) or len(page_items) > 1000:
                    raise ValueError("invalid commit archive page")
                for raw_item in page_items:
                    if not isinstance(raw_item, dict):
                        continue
                    sha = raw_item.get("sha")
                    event = event_by_sha.get(sha) if isinstance(sha, str) else None
                    if event is None:
                        continue
                    commit = raw_item.get("commit") if isinstance(raw_item.get("commit"), dict) else {}
                    message = commit.get("message") if isinstance(commit.get("message"), str) else ""
                    title = message.splitlines()[0].strip()[:500] if message.strip() else "（无提交说明）"
                    github_author = raw_item.get("author") if isinstance(raw_item.get("author"), dict) else {}
                    git_author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
                    login = github_author.get("login") if isinstance(github_author.get("login"), str) else ""
                    git_name = git_author.get("name") if isinstance(git_author.get("name"), str) else ""
                    author = login or git_name or "匿名作者"
                    is_bot = github_author.get("type") == "Bot" or author.casefold().endswith("[bot]")
                    records_by_sha[sha] = {
                        "sha": sha,
                        "title": title,
                        "author": author,
                        "is_bot": is_bot,
                        "anonymous": not bool(login),
                        "date": iso_z(event.event_at),
                        "url": f"https://github.com/{repository.full_name}/commit/{sha}",
                        "_author_key": login.casefold() if login else (git_name.casefold() or "anonymous"),
                    }
    except (OSError, ValueError, TypeError, json.JSONDecodeError, RecursionError) as exc:
        raise AppError(503, "COMMIT_ARCHIVE_UNAVAILABLE", "Commit 采集归档损坏或不可读取，请重新采集仓库数据") from exc

    coverage_state = "partial" if module_coverage == "budget_exhausted" else module_coverage if module_coverage in {"complete", "partial"} else "missing"
    if not archive_found:
        coverage_state = "missing"
    elif missing_archive:
        coverage_state = "partial"
    coverage_labels = {"complete": "采集完整", "partial": "部分采集", "missing": "暂无逐条数据"}
    coverage_details = {
        "complete": "完整仅代表本次采集范围与页数设置已完成，不代表 GitHub 全部历史",
        "partial": "采集未覆盖全部设置范围，明细可能不完整",
        "missing": "当前没有可读取的 Commit 归档，请重新采集仓库数据",
    }
    available = archive_found and coverage_state != "missing"

    records = list(records_by_sha.values())
    records.sort(key=lambda item: (item["date"], item["sha"]), reverse=True)
    daily = Counter(item["date"][:10] for item in records)
    author_groups = {}
    for item in records:
        key = item["_author_key"]
        group = author_groups.setdefault(key, {
            "author": item["author"], "commits": 0, "is_bot": item["is_bot"], "anonymous": item["anonymous"],
        })
        group["commits"] += 1
    authors = sorted(author_groups.values(), key=lambda item: (-item["commits"], item["author"].casefold()))[:20]

    normalized_search = (search or "").strip().casefold()
    filtered = [item for item in records if not normalized_search or normalized_search in item["title"].casefold() or normalized_search in item["author"].casefold() or normalized_search in item["sha"].casefold()]
    for item in records:
        item.pop("_author_key", None)
    for item in filtered:
        item.pop("_author_key", None)
    if week_start is not None:
        range_start, range_end = week_begin, week_end
    else:
        range_start, range_end = run.window_start, run.window_end
    if not available:
        note = "当前采集没有可读取的 Commit 逐条归档，请重新采集深度活动数据。"
    else:
        note = "只展示本次采集窗口内已归档的 Commit；SHA 去重，作者邮箱不会返回。"
        if coverage_state == "partial" or missing_archive:
            note = "部分采集归档缺失或未覆盖完整设置范围，当前明细可能不完整；未采集的历史数据不会补造。"
    return {
        "available": available,
        "coverage": {"state": coverage_state, "label": coverage_labels[coverage_state], "detail": coverage_details[coverage_state]},
        "note": note,
        "window_start": iso_z(range_start),
        "window_end": iso_z(range_end),
        "commit_count": len(records),
        "author_count": len(author_groups),
        "daily_counts": [{"date": day, "count": count} for day, count in sorted(daily.items())],
        "authors": authors,
        "items": filtered[(page - 1) * per_page : page * per_page],
        "total": len(filtered),
    }


def repository_closed_issues(session, repository_id, search=None, *, include_body=False):
    """Return safe, itemized closed Issue details from the latest analysis archive."""
    repository = session.get(Repository, repository_id)
    if repository is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    run = session.scalar(select(RepositoryInsightRun).where(
        RepositoryInsightRun.repository_id == repository_id,
        RepositoryInsightRun.metric_version == METRIC_VERSION,
    ).order_by(desc(RepositoryInsightRun.analyzed_at), desc(RepositoryInsightRun.run_id)).limit(1))
    if run is None:
        return {
            "available": False, "coverage": {"state": "missing", "label": "尚无逐条数据", "detail": "请先采集深度活动数据"},
            "note": "尚无可读取的 Issue 采集归档。", "window_start": None, "window_end": None, "items": [],
        }

    try:
        task_ids = json.loads(run.source_task_ids_json)
        archive_paths = json.loads(run.source_archive_paths_json)
        module_coverage = json.loads(run.module_coverage_json).get("issues", {}).get("coverage", "not_collected")
    except (TypeError, ValueError, AttributeError) as exc:
        raise AppError(503, "ISSUE_ARCHIVE_UNAVAILABLE", "Issue 采集记录无法读取，请重新采集仓库数据") from exc
    if not isinstance(task_ids, list):
        task_ids = []
    if not isinstance(archive_paths, list):
        archive_paths = []

    events = session.scalars(select(RepositoryActivityEvent).where(
        RepositoryActivityEvent.repository_id == repository_id,
        RepositoryActivityEvent.event_type == "issue",
        RepositoryActivityEvent.source_task_id.in_(task_ids) if task_ids else RepositoryActivityEvent.source_task_id == "",
        RepositoryActivityEvent.closed_at.is_not(None),
        RepositoryActivityEvent.closed_at >= run.window_start,
        RepositoryActivityEvent.closed_at < run.window_end,
    )).all()
    event_by_id = {event.source_item_id: event for event in events}

    archive_found = False
    missing_archive = False
    items_by_id = {}
    try:
        for archive_path in archive_paths:
            if not isinstance(archive_path, str):
                continue
            try:
                archive = read_archive(archive_path)
            except FileNotFoundError:
                missing_archive = True
                continue
            archive_found = True
            issue_archive = archive.get("issues")
            pages = iter_module_pages(issue_archive)
            for raw_page in pages:
                if isinstance(raw_page, str):
                    if len(raw_page) > 16_000_000:
                        raise ValueError("issue archive page exceeds size limit")
                    page = json.loads(raw_page)
                else:
                    page = raw_page
                if not isinstance(page, list) or len(page) > 1000:
                    raise ValueError("invalid issue archive page")
                for raw_item in page:
                    if not isinstance(raw_item, dict) or "pull_request" in raw_item:
                        continue
                    identifier = raw_item.get("id")
                    if type(identifier) is not int or str(identifier) not in event_by_id:
                        continue
                    number = raw_item.get("number")
                    if type(number) is not int or number <= 0:
                        continue
                    event = event_by_id[str(identifier)]
                    created_at = event.created_at
                    closed_at = event.closed_at
                    elapsed_days = (closed_at - created_at).total_seconds() / 86400 if created_at else None
                    item = {
                        "number": number,
                        "title": raw_item.get("title") if isinstance(raw_item.get("title"), str) else "（无标题）",
                        "created_at": iso_z(created_at),
                        "closed_at": iso_z(closed_at),
                        "duration_days": round(elapsed_days, 1) if elapsed_days is not None and math.isfinite(elapsed_days) and elapsed_days >= 0 else None,
                        "state": "closed",
                        "url": f"https://github.com/{repository.full_name}/issues/{number}",
                        "_closed_at": closed_at,
                    }
                    if include_body:
                        item["body"] = raw_item.get("body") if isinstance(raw_item.get("body"), str) else None
                        item["comments_count"] = raw_item.get("comments") if type(raw_item.get("comments")) is int and raw_item.get("comments") >= 0 else 0
                    items_by_id[str(identifier)] = item
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise AppError(503, "ISSUE_ARCHIVE_UNAVAILABLE", "Issue 采集归档损坏或不可读取，请重新采集仓库数据") from exc

    coverage_state = "partial" if module_coverage == "budget_exhausted" else module_coverage if module_coverage in {"complete", "partial"} else "missing"
    if not archive_found:
        coverage_state = "missing"
    elif missing_archive:
        coverage_state = "partial" if archive_found else "missing"
    coverage_labels = {"complete": "采集完整", "partial": "部分采集", "missing": "暂无逐条数据"}
    coverage_details = {
        "complete": "仅代表本次采集窗口和已设置的分页范围完整",
        "partial": "本次采集未覆盖全部 Issue 分页，列表可能不完整",
        "missing": "当前没有可读取的 Issue 归档，请重新采集深度活动数据",
    }
    available = archive_found
    if available and not missing_archive and coverage_state == "missing":
        coverage_state = "partial"
    if coverage_state == "missing":
        note = "当前采集没有可读取的 Issue 逐条归档，请重新采集深度活动数据。"
    else:
        note = "仅展示本次采集窗口内已关闭的 Issue；Pull Request 已排除，未采集的历史数据不会补造。"
        if missing_archive:
            note = "部分归档不可读取，当前列表可能不完整；请重新采集深度活动数据。"

    rows = list(items_by_id.values())
    rows.sort(key=lambda row: (row["_closed_at"], row["number"]), reverse=True)
    normalized_search = (search or "").strip().casefold()
    if normalized_search:
        rows = [row for row in rows if normalized_search in row["title"].casefold() or normalized_search in str(row["number"])]
    for row in rows:
        row.pop("_closed_at", None)
    return {
        "available": available,
        "coverage": {"state": coverage_state, "label": coverage_labels[coverage_state], "detail": coverage_details[coverage_state]},
        "note": note,
        "window_start": iso_z(run.window_start),
        "window_end": iso_z(run.window_end),
        "items": rows,
    }


def repository_pull_requests(session, repository_id, search=None, *, include_body=False):
    """Return closed Pull Requests saved in the latest analysis archive."""
    repository = session.get(Repository, repository_id)
    if repository is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    run = session.scalar(select(RepositoryInsightRun).where(
        RepositoryInsightRun.repository_id == repository_id,
        RepositoryInsightRun.metric_version == METRIC_VERSION,
    ).order_by(desc(RepositoryInsightRun.analyzed_at), desc(RepositoryInsightRun.run_id)).limit(1))
    if run is None:
        return {
            "available": False, "coverage": {"state": "missing", "label": "尚无逐条数据", "detail": "请先采集深度活动数据"},
            "note": "尚无可读取的 Pull Request 采集归档。", "window_start": None, "window_end": None, "items": [],
        }

    try:
        task_ids = json.loads(run.source_task_ids_json)
        archive_paths = json.loads(run.source_archive_paths_json)
        module_coverage = json.loads(run.module_coverage_json).get("pulls", {}).get("coverage", "not_collected")
    except (TypeError, ValueError, AttributeError) as exc:
        raise AppError(503, "PULL_REQUEST_ARCHIVE_UNAVAILABLE", "Pull Request 采集记录无法读取，请重新采集仓库数据") from exc
    task_ids = task_ids if isinstance(task_ids, list) else []
    archive_paths = archive_paths if isinstance(archive_paths, list) else []

    events = session.scalars(select(RepositoryActivityEvent).where(
        RepositoryActivityEvent.repository_id == repository_id,
        RepositoryActivityEvent.event_type == "pull_request",
        RepositoryActivityEvent.source_task_id.in_(task_ids) if task_ids else RepositoryActivityEvent.source_task_id == "",
        RepositoryActivityEvent.closed_at.is_not(None),
        RepositoryActivityEvent.closed_at >= run.window_start,
        RepositoryActivityEvent.closed_at < run.window_end,
    )).all()
    event_by_id = {event.source_item_id: event for event in events}

    archive_found = False
    missing_archive = False
    pull_data_found = False
    items_by_id = {}
    try:
        for archive_path in archive_paths:
            if not isinstance(archive_path, str):
                continue
            try:
                archive = read_archive(archive_path)
            except FileNotFoundError:
                missing_archive = True
                continue
            archive_found = True
            pull_archive = archive.get("pulls")
            if pull_archive is None:
                continue
            pull_data_found = True
            pages = iter_module_pages(pull_archive)
            for raw_page in pages:
                if isinstance(raw_page, str):
                    if len(raw_page) > 16_000_000:
                        raise ValueError("pull request archive page exceeds size limit")
                    page = json.loads(raw_page)
                else:
                    page = raw_page
                if not isinstance(page, list) or len(page) > 1000:
                    raise ValueError("invalid pull request archive page")
                for raw_item in page:
                    if not isinstance(raw_item, dict):
                        continue
                    identifier = raw_item.get("id")
                    if type(identifier) is not int or str(identifier) not in event_by_id:
                        continue
                    number = raw_item.get("number")
                    if type(number) is not int or number <= 0:
                        continue
                    event = event_by_id[str(identifier)]
                    created_at, closed_at, merged_at = event.created_at, event.closed_at, event.merged_at
                    duration_days = (merged_at - created_at).total_seconds() / 86400 if created_at and merged_at else None
                    item = {
                        "number": number,
                        "title": raw_item.get("title") if isinstance(raw_item.get("title"), str) else "（无标题）",
                        "created_at": iso_z(created_at),
                        "closed_at": iso_z(closed_at),
                        "merged_at": iso_z(merged_at),
                        "duration_days": round(duration_days, 1) if duration_days is not None and math.isfinite(duration_days) and duration_days >= 0 else None,
                        "state": "merged" if merged_at else "closed",
                        "draft": raw_item.get("draft") is True,
                        "comments_count": raw_item.get("comments") if type(raw_item.get("comments")) is int and raw_item.get("comments") >= 0 else 0,
                        "url": f"https://github.com/{repository.full_name}/pull/{number}",
                        "_sort_at": merged_at or closed_at,
                    }
                    if include_body:
                        item["body"] = raw_item.get("body") if isinstance(raw_item.get("body"), str) else None
                    items_by_id[str(identifier)] = item
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise AppError(503, "PULL_REQUEST_ARCHIVE_UNAVAILABLE", "Pull Request 采集归档损坏或不可读取，请重新采集仓库数据") from exc

    coverage_state = "partial" if module_coverage == "budget_exhausted" else module_coverage if module_coverage in {"complete", "partial"} else "missing"
    if not archive_found or not pull_data_found:
        coverage_state = "missing"
    elif missing_archive:
        coverage_state = "partial"
    coverage_labels = {"complete": "采集完整", "partial": "部分采集", "missing": "暂无逐条数据"}
    coverage_details = {
        "complete": "仅代表本次采集窗口和已设置的分页范围完整",
        "partial": "本次采集未覆盖全部 Pull Request 分页，列表可能不完整",
        "missing": "当前没有可读取的 Pull Request 归档，请重新采集深度活动数据",
    }
    available = pull_data_found and archive_found
    rows = list(items_by_id.values())
    rows.sort(key=lambda row: (row["_sort_at"] or datetime.min, row["number"]), reverse=True)
    normalized_search = (search or "").strip().casefold()
    if normalized_search:
        rows = [row for row in rows if normalized_search in row["title"].casefold() or normalized_search in str(row["number"])]
    for row in rows:
        row.pop("_sort_at", None)
    if not available:
        note = "当前采集没有可读取的 Pull Request 逐条归档，请重新采集深度活动数据。"
    else:
        note = "仅展示本次采集窗口内已关闭的 PR（包含已合并和关闭未合并）；Open PR 和未采集历史不会补造。"
        if coverage_state == "partial" or missing_archive:
            note = "部分采集归档缺失或未覆盖完整设置范围，当前 PR 列表可能不完整。"
    return {
        "available": available,
        "coverage": {"state": coverage_state, "label": coverage_labels[coverage_state], "detail": coverage_details[coverage_state]},
        "note": note,
        "window_start": iso_z(run.window_start),
        "window_end": iso_z(run.window_end),
        "items": rows,
    }


def repository_pull_request_detail(session, repository_id, pull_number):
    result = repository_pull_requests(session, repository_id, include_body=True)
    if not result["available"]:
        raise AppError(409, "PULL_REQUEST_ARCHIVE_UNAVAILABLE", result["note"])
    for item in result["items"]:
        if item["number"] == pull_number:
            return {key: item[key] for key in ("number", "title", "created_at", "closed_at", "merged_at", "duration_days", "state", "draft", "comments_count", "url", "body")}
    raise AppError(404, "RESOURCE_NOT_FOUND", "本次采集归档中没有该 Pull Request")


def repository_pull_request_online_detail(session, repository_id, pull_number, github):
    repository_pull_request_detail(session, repository_id, pull_number)
    repository = session.get(Repository, repository_id)
    raw_pull = github.get_pull_request_detail(repository.full_name, pull_number)
    raw_user = raw_pull.get("user") if isinstance(raw_pull.get("user"), dict) else {}
    raw_labels = raw_pull.get("labels") if isinstance(raw_pull.get("labels"), list) else []
    labels = [label["name"] for label in raw_labels if isinstance(label, dict) and isinstance(label.get("name"), str)]
    comment_count = raw_pull.get("comments") if type(raw_pull.get("comments")) is int and raw_pull.get("comments") >= 0 else 0
    comments = []
    comments_complete = True
    comments_error = None
    if comment_count:
        try:
            result = github.list_pull_request_comments_detailed(repository.full_name, pull_number)
            if result.error_code:
                raise AppError(result.error_status_code or 502, result.error_code, result.error_message or "读取 Pull Request 评论失败", result.error_details)
            for row in result.items:
                user = row.get("user") if isinstance(row.get("user"), dict) else {}
                comments.append({
                    "author": user.get("login") if isinstance(user.get("login"), str) else "已删除用户",
                    "body": row.get("body") if isinstance(row.get("body"), str) else "",
                    "created_at": row.get("created_at") if isinstance(row.get("created_at"), str) else None,
                })
            comments_complete = not result.has_next
        except AppError as exc:
            comments_complete = False
            comments_error = exc.message

    merged_at = raw_pull.get("merged_at") if isinstance(raw_pull.get("merged_at"), str) else None
    raw_state = raw_pull.get("state")
    state = "merged" if merged_at else raw_state if raw_state in {"open", "closed"} else "closed"
    return {
        "number": pull_number,
        "title": raw_pull.get("title") if isinstance(raw_pull.get("title"), str) else "（无标题）",
        "body": raw_pull.get("body") if isinstance(raw_pull.get("body"), str) else None,
        "state": state,
        "author": raw_user.get("login") if isinstance(raw_user.get("login"), str) else None,
        "labels": labels,
        "created_at": raw_pull.get("created_at") if isinstance(raw_pull.get("created_at"), str) else None,
        "closed_at": raw_pull.get("closed_at") if isinstance(raw_pull.get("closed_at"), str) else None,
        "merged_at": merged_at,
        "updated_at": raw_pull.get("updated_at") if isinstance(raw_pull.get("updated_at"), str) else None,
        "url": raw_pull.get("html_url") if isinstance(raw_pull.get("html_url"), str) else f"https://github.com/{repository.full_name}/pull/{pull_number}",
        "comments_count": comment_count,
        "comments": comments,
        "comments_complete": comments_complete,
        "comments_error": comments_error,
    }


def repository_closed_issue_detail(session, repository_id, issue_number):
    result = repository_closed_issues(session, repository_id, include_body=True)
    if not result["available"]:
        raise AppError(409, "ISSUE_ARCHIVE_UNAVAILABLE", result["note"])
    for item in result["items"]:
        if item["number"] == issue_number:
            return {key: item[key] for key in ("number", "title", "created_at", "closed_at", "duration_days", "state", "url", "body", "comments_count")}
    raise AppError(404, "RESOURCE_NOT_FOUND", "本次采集归档中没有该已关闭 Issue")


def repository_closed_issue_online_detail(session, repository_id, issue_number, github):
    repository_closed_issue_detail(session, repository_id, issue_number)
    repository = session.get(Repository, repository_id)
    raw_issue = github.get_issue_detail(repository.full_name, issue_number)
    raw_user = raw_issue.get("user") if isinstance(raw_issue.get("user"), dict) else {}
    raw_labels = raw_issue.get("labels") if isinstance(raw_issue.get("labels"), list) else []
    labels = [label["name"] for label in raw_labels if isinstance(label, dict) and isinstance(label.get("name"), str)]
    comment_count = raw_issue.get("comments") if type(raw_issue.get("comments")) is int and raw_issue.get("comments") >= 0 else 0
    comments = []
    comments_complete = True
    comments_error = None
    if comment_count:
        try:
            result = github.list_issue_comments_detailed(repository.full_name, issue_number)
            if result.error_code:
                raise AppError(result.error_status_code or 502, result.error_code, result.error_message or "读取 Issue 评论失败", result.error_details)
            for row in result.items:
                user = row.get("user") if isinstance(row.get("user"), dict) else {}
                author = user.get("login") if isinstance(user.get("login"), str) else "已删除用户"
                comments.append({
                    "author": author,
                    "body": row.get("body") if isinstance(row.get("body"), str) else "",
                    "created_at": row.get("created_at") if isinstance(row.get("created_at"), str) else None,
                })
            comments_complete = not result.has_next
        except AppError as exc:
            comments_complete = False
            comments_error = exc.message

    raw_state = raw_issue.get("state")
    return {
        "number": issue_number,
        "title": raw_issue.get("title") if isinstance(raw_issue.get("title"), str) else "（无标题）",
        "body": raw_issue.get("body") if isinstance(raw_issue.get("body"), str) else None,
        "state": raw_state if raw_state in {"open", "closed"} else "closed",
        "author": raw_user.get("login") if isinstance(raw_user.get("login"), str) else None,
        "labels": labels,
        "created_at": raw_issue.get("created_at") if isinstance(raw_issue.get("created_at"), str) else None,
        "closed_at": raw_issue.get("closed_at") if isinstance(raw_issue.get("closed_at"), str) else None,
        "updated_at": raw_issue.get("updated_at") if isinstance(raw_issue.get("updated_at"), str) else None,
        "url": raw_issue.get("html_url") if isinstance(raw_issue.get("html_url"), str) else f"https://github.com/{repository.full_name}/issues/{issue_number}",
        "comments_count": comment_count,
        "comments": comments,
        "comments_complete": comments_complete,
        "comments_error": comments_error,
    }

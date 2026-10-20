import hashlib
import json
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from backend.app.analytics.insights import LIMITATIONS, calculate_insights
from backend.app.core.clock import iso_z, utc_now
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import Repository, RepositoryActivityEvent, RepositoryInsightRun
from backend.app.pipeline.event_normalizer import normalize_events
from backend.app.pipeline.raw_archive import read_archive

METRIC_VERSION = "insights-v1"
MODULES = ("commits", "issues", "pulls", "releases")
PAGE_LIMIT_NOTE = "已达到用户设置的接口页数上限；本次按设置完成，未请求后续页。"


def persist_insights(session: Session, repository_id: int, task_id: str, rows: dict, sources: dict, start, end, archive_paths: list[str], *, version=METRIC_VERSION, origin="collection"):
    normalized, checked_sources = {}, {}
    for module in MODULES:
        normalized[module], counts = normalize_events(module, rows.get(module, []))
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
    metrics = calculate_insights(normalized, checked_sources, start, end)
    states = [m["quality"]["status"] for m in metrics.values()]
    status = "missing" if all(s == "missing" for s in states) else "partial" if any(s in {"partial", "missing", "failed"} for s in states) else "ready"
    limitations = list(LIMITATIONS)
    if any(source.get("limit_reached") for source in checked_sources.values()):
        limitations.append(PAGE_LIMIT_NOTE)
    if not archive_paths:
        limitations.append("原始归档不可用；本次统计及事件仍保留，但原始响应的可复核性下降。")
    result = {"repository_id": repository_id, "run_id": str(uuid4()), "metric_version": version, "status": status, "window_start": iso_z(start), "window_end": iso_z(end), "timezone": "UTC", "analyzed_at": iso_z(now), "source_task_ids": [task_id], "source_archive_paths": archive_paths, "origin": origin, "sources": checked_sources, "insights": metrics, "limitations": limitations}
    session.add(RepositoryInsightRun(run_id=result["run_id"], input_fingerprint=fingerprint, repository_id=repository_id, metric_version=version, window_start=start, window_end=end, analyzed_at=now, source_task_ids_json=json.dumps([task_id]), source_archive_paths_json=json.dumps(archive_paths), module_coverage_json=json.dumps(checked_sources), status=status, limitations_json=json.dumps(limitations, ensure_ascii=False), result_json=json.dumps(result, ensure_ascii=False)))
    session.flush()
    return result


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
        for raw_page in archive.get("releases", []):
            page = json.loads(raw_page) if isinstance(raw_page, str) else raw_page
            if not isinstance(page, list):
                continue
            for item in page:
                if isinstance(item, dict) and item.get("id") == release_id:
                    return {
                        "id": str(release_id),
                        "name": item.get("name") if isinstance(item.get("name"), str) else None,
                        "body": item.get("body") if isinstance(item.get("body"), str) else None,
                    }
    raise AppError(404, "RESOURCE_NOT_FOUND", "当前采集归档中没有该 Release 说明，请重新采集仓库数据")

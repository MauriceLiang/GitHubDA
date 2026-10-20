"""Replay one validated activity archive; no network or decompression on page reads."""
import json
from sqlalchemy import select

from backend.app.core.clock import iso_z
from backend.app.persistence.models import ActivityWindow, CollectionLog
from backend.app.pipeline.raw_archive import read_archive
from backend.app.services.insights import MODULES, persist_insights


def replay_activity(session, repository_id, *, apply=False):
    activity = session.scalar(select(ActivityWindow).where(ActivityWindow.repository_id == repository_id, ActivityWindow.source_archive_path.is_not(None)).order_by(ActivityWindow.collected_at.desc()).limit(1))
    if activity is None:
        raise ValueError("没有可回放的活动归档，需要重新采集")
    raw = read_archive(activity.source_archive_path)
    meta = raw.get("_meta", {})
    if "_meta" in raw and (not isinstance(meta, dict) or meta.get("schema_version") != 1):
        raise ValueError("不支持的归档版本")
    if meta and (not isinstance(meta.get("sources"), dict) or meta.get("window_start") != iso_z(activity.window_start) or meta.get("window_end") != iso_z(activity.window_end)):
        raise ValueError("归档窗口或来源结构与采集记录不一致")
    legacy_coverage = json.loads(activity.details_json).get("coverage_by_module", {})
    mapping = {"commits": "commits_count", "issues": "issues_closed_count", "pulls": "pulls_merged_count", "releases": "releases_count"}
    rows, sources = {}, {}
    for module in MODULES:
        entry = raw.get(module)
        pages = entry.get("pages") if isinstance(entry, dict) else entry
        if not isinstance(pages, list) or len(pages) > 100:
            raise ValueError(f"{module}: 归档分页结构不兼容")
        records = []
        for page in pages:
            if not isinstance(page, str) or len(page) > 16_000_000:
                raise ValueError(f"{module}: 非法分页")
            try:
                value = json.loads(page)
            except (ValueError, RecursionError) as exc:
                raise ValueError(f"{module}: 非法分页 JSON") from exc
            if not isinstance(value, list) or len(value) > 1000 or any(not isinstance(r, dict) for r in value):
                raise ValueError(f"{module}: 非法记录")
            records.extend(value)
        rows[module] = records
        metadata = meta.get("sources", {}).get(module) if meta else None
        if metadata is not None and (not isinstance(metadata, dict) or metadata.get("coverage") not in {"complete", "partial", "not_collected"}):
            raise ValueError("非法覆盖元数据")
        # Old archives have no complete query contract; preserve evidence conservatively.
        sources[module] = metadata or {"coverage": "partial", "error_code": "LEGACY_QUERY_CONTRACT_UNKNOWN", "legacy_coverage": legacy_coverage.get(mapping[module]), "page_count": len(pages), "collected_at": iso_z(activity.collected_at)}
    log = session.scalar(select(CollectionLog).where(CollectionLog.repository_id == repository_id, CollectionLog.event_type == "collection_completed", CollectionLog.occurred_at >= activity.collected_at).order_by(CollectionLog.occurred_at).limit(1))
    task_id = log.task_id if log and log.task_id else f"archive:{activity.id}"
    preview = {"repository_id": repository_id, "archive": activity.source_archive_path, "window_start": iso_z(activity.window_start), "window_end": iso_z(activity.window_end), "records": {key: len(value) for key, value in rows.items()}, "sources": sources}
    if not apply:
        return preview
    result = persist_insights(session, repository_id, task_id, rows, sources, activity.window_start, activity.window_end, [activity.source_archive_path], origin="archived_replay")
    return result

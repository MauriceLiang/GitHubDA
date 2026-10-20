"""insights-v1: deterministic UTC event statistics, independent of HTTP/DB/UI."""
from datetime import datetime, timedelta
from statistics import median

import numpy as np

from backend.app.core.clock import iso_z

LIMITATIONS = [
    "UTC，左闭右开窗口；分页完成只代表指定端点与查询范围，不代表 GitHub 全历史。",
    "Commit 来自默认分支，包含合并提交；Issue 使用对象最近可观测关闭时间，不回溯 reopen 生命周期。",
    "PR 仅采集 closed 状态；合并耗时不是首次响应时间，不能计算所有创建 PR 的合并率。",
    "Release 仅统计已发布正式版本；预发布单独计数，纯 tag 不计入。",
    "GitHub 对象在分页期间可能更新；统计是采集时观察结果，不是事务一致的全站快照。",
]


def week_start(value):
    return value.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=value.weekday())


def quality(source, n, *, insufficient=False):
    coverage = source.get("coverage", "not_collected")
    status = "missing" if coverage == "not_collected" else "partial" if coverage != "complete" else "insufficient_samples" if insufficient else "ready"
    if source.get("error_code") and not source.get("observed_records"):
        status = "failed"
    return {"status": status, "coverage": coverage, "valid_samples": n, "reason": source.get("error_code") or ("采集覆盖不完整，仅为已观察样本" if status == "partial" else "样本不足" if insufficient else None), "rejected_records": source.get("rejected_records", 0), "invalid_event_times": source.get("invalid_event_times", 0)}


def weekly(events, start, end, source):
    current = week_start(start)
    points = []
    while current < end:
        stop = current + timedelta(days=7)
        full = current >= start and stop <= end
        ready = full and source.get("coverage") == "complete"
        count = sum(e["event_at"] is not None and current <= e["event_at"] < stop and start <= e["event_at"] < end for e in events)
        points.append({"start": iso_z(current), "end": iso_z(stop), "value": count if ready else None, "observed_events": count, "quality": "ready" if ready else "partial", "complete_week": full})
        current = stop
    return points


def duration_metric(events, start, end, source, field, key):
    terminal = [e for e in events if e[field] is not None and start <= e[field] < end]
    values = []
    invalid = 0
    for event in terminal:
        created = event["created_at"]
        if created is None or event[field] < created:
            invalid += 1
        else:
            values.append((event[field] - created).total_seconds() / 3600)
    n = len(values)
    edges = [0, 24, 72, 168, 720]
    histogram = [{"label": label, "count": sum(low <= v < high for v in values)} for low, high, label in zip(edges, edges[1:] + [float("inf")], ["<1 天", "1–3 天", "3–7 天", "7–30 天", "≥30 天"])]
    return {"metric_key": key, "unit": "hours", "window_start": iso_z(start), "window_end": iso_z(end), "quality": quality(source, n, insufficient=n == 0), "observed_terminal_count": len(terminal), "excluded_invalid_duration": invalid, "missing_duration_rate": invalid / len(terminal) if terminal else None, "observed_without_terminal": sum(e[field] is None for e in events), "median_hours": median(values) if values else None, "p75_hours": float(np.quantile(values, .75, method="linear")) if n >= 5 else None, "p90_hours": float(np.quantile(values, .9, method="linear")) if n >= 10 else None, "histogram": histogram, "weekly": weekly(terminal, start, end, source)}


def calculate_insights(events, sources, start, end):
    commits = events["commits"]
    points = weekly(commits, start, end, sources["commits"])
    completed_end = week_start(end)
    eight = [p for p in points if completed_end - timedelta(weeks=8) <= datetime.fromisoformat(p["start"].replace("Z", "")) < completed_end]
    comparable = len(eight) == 8 and all(p["quality"] == "ready" for p in eight)
    previous = sum(p["value"] for p in eight[:4]) if comparable else None
    recent = sum(p["value"] for p in eight[4:]) if comparable else None
    valid_commits = [e for e in commits if e["event_at"] and start <= e["event_at"] < end]
    activity = {"metric_key": "commits_weekly", "unit": "commits", "window_start": iso_z(start), "window_end": iso_z(end), "quality": quality(sources["commits"], len(valid_commits)), "weekly": points, "recent_4w": recent, "previous_4w": previous, "delta": recent - previous if comparable else None, "change_rate_pct": (recent - previous) / previous * 100 if comparable and previous else None, "comparison_reason": None if comparable and previous else "基期为零，不计算百分比" if comparable else "不足八个完整覆盖的已结束自然周，无法判断前后四周变化"}
    release_start = end - timedelta(days=365)
    releases = [e for e in events["releases"] if e["published_at"] and release_start <= e["published_at"] < end and not e["is_draft"]]
    formal = sorted([e for e in releases if not e["is_prerelease"]], key=lambda e: e["published_at"])
    gaps = [(b["published_at"] - a["published_at"]).total_seconds() / 86400 for a, b in zip(formal, formal[1:])]
    return {"commit_activity": activity,
            "issue_resolution": duration_metric(events["issues"], start, end, sources["issues"], "closed_at", "issue_closed_duration_hours"),
            "pr_merges": duration_metric(events["pulls"], start, end, sources["pulls"], "merged_at", "pr_merge_duration_hours"),
            "release_cadence": {"metric_key": "release_intervals_days", "unit": "days", "window_start": iso_z(release_start), "window_end": iso_z(end), "quality": quality(sources["releases"], len(formal), insufficient=len(formal) < 2), "release_count": len(formal), "prerelease_count": len(releases) - len(formal), "timeline": [{"id": e["source_item_id"], "published_at": iso_z(e["published_at"])} for e in formal], "intervals_days": gaps, "median_interval_days": median(gaps) if gaps else None}}

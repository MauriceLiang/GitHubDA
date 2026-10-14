import json
from datetime import timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.core.clock import iso_z, utc_now
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient
from backend.app.persistence.models import AnalysisResult, ActivityWindow, CollectionLog, CollectionTask, Repository, RepositorySnapshot
from backend.app.pipeline.cleaner import clean_repository_profile
from backend.app.pipeline.feature_builder import build_profile_metrics
from backend.app.pipeline.quality import overall_coverage
from backend.app.pipeline.raw_archive import archive_json
from backend.app.services.repositories import latest_analysis, latest_snapshot, repository_from_github
from backend.app.worker.queue import update_phase


def execute_task(session_factory, task_id: str, github: GitHubClient) -> None:
    session: Session = session_factory()
    try:
        task = session.get(CollectionTask, task_id)
        if task is None or task.status != "running":
            return
        repo = session.get(Repository, task.repository_id)
        if repo is None:
            _finish_failed(session, task, "RESOURCE_NOT_FOUND", "本地仓库记录不存在")
            return
        previous = latest_snapshot(session, repo.repository_id)
        reusable_basic_analysis = None
        request_etag = None
        if task.depth == "basic" and previous and previous.response_etag:
            candidate = latest_analysis(session, repo.repository_id, "basic")
            try:
                candidate_metrics = json.loads(candidate.metrics_json) if candidate else None
            except (TypeError, ValueError):
                candidate_metrics = None
            if (
                candidate
                and candidate.source_collected_at == previous.collected_at
                and (candidate.valid_sample_size or 0) > 0
                and candidate.coverage in {"complete", "partial"}
                and isinstance(candidate_metrics, dict)
            ):
                reusable_basic_analysis = candidate
                request_etag = previous.response_etag
        try:
            payload, status, etag = github.get_repository_by_id(repo.repository_id, request_etag)
            if status == 304:
                if reusable_basic_analysis is None:
                    raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 返回 304，但没有可复用的当前 basic 分析结果", {"http_status": 304})
                repo.last_seen_at = utc_now()
                task.status = "succeeded"
                task.phase = None
                task.message = "GitHub 确认仓库资料未变化，沿用最近一次有效观测"
                task.finished_at = utc_now()
                task.lease_until = None
                session.add(CollectionLog(request_id=task.task_id, task_id=task.task_id, repository_id=repo.repository_id, event_type="not_modified", source_endpoint=f"/repositories/{repo.repository_id}", http_status=304, message_redacted="ETag 命中；未新增指标快照"))
                session.commit()
                return
            if payload is None:
                raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 未返回仓库资料")
        except AppError as exc:
            _finish_failed(session, task, exc.code, exc.message, details=exc.details)
            return

        try:
            archive_path = archive_json(repo.repository_id, task.task_id, "repository", {"source_endpoint": f"/repositories/{repo.repository_id}", "collected_at": iso_z(utc_now()), "http_status": status, "etag": etag, "data": payload})
        except OSError:
            archive_path = None
            session.add(CollectionLog(request_id=task.task_id, task_id=task.task_id, repository_id=repo.repository_id, event_type="archive_failed", source_endpoint=f"/repositories/{repo.repository_id}", http_status=status, message_redacted="原始数据归档写入失败"))

        update_phase(session, task.task_id, "cleaning", "正在规范化 GitHub 仓库字段")
        try:
            cleaned = clean_repository_profile(payload, repo.repository_id)
        except AppError as exc:
            _finish_failed(session, task, exc.code, exc.message)
            return

        collected_at = utc_now()
        profile_metrics = build_profile_metrics(cleaned, collected_at)
        metrics = dict(profile_metrics)
        depth_coverage = "complete"
        activity: dict[str, Any] | None = None
        window_start = collected_at - timedelta(days=90)
        window_end = collected_at
        if task.depth == "deep":
            update_phase(session, task.task_id, "collecting", "正在采集有限时间窗的深度活动数据")
            activity, depth_coverage = _collect_deep(github, cleaned["full_name"], window_start, window_end, task)
            for metric, key in (("commits_90d", "commits_count"), ("issues_closed_90d", "issues_closed_count"), ("pr_merged_90d", "pulls_merged_count"), ("release_count_365d", "releases_count")):
                metrics[metric] = activity[key] if activity["coverage_by_module"][key] == "complete" else None

        update_phase(session, task.task_id, "analyzing", "正在计算基础指标与数据覆盖")
        coverage = overall_coverage({"profile": "complete", "activity": depth_coverage})
        limitations = ["关注度指标不等于代码质量"]
        if task.depth == "deep" and depth_coverage == "partial":
            limitations.append("部分深度活动端点或分页未能完整采集")
        update_phase(session, task.task_id, "persisting", "正在保存快照、分析结果与来源记录")

        repo = repository_from_github(session, payload)
        snapshot = RepositorySnapshot(
            repository_id=repo.repository_id,
            collected_at=collected_at,
            stars=cleaned["stars"],
            forks=cleaned["forks"],
            open_issues_and_pr_count=cleaned["open_issues_and_pr_count"],
            pushed_at=cleaned["pushed_at"],
            github_updated_at=cleaned["github_updated_at"],
            response_etag=etag,
            source_http_status=status,
            source_archive_path=archive_path,
            valid=True,
        )
        session.add(snapshot)
        if activity is not None:
            try:
                activity_archive = archive_json(repo.repository_id, task.task_id, "activity", activity["raw"])
            except OSError:
                activity_archive = None
                session.add(CollectionLog(request_id=task.task_id, task_id=task.task_id, repository_id=repo.repository_id, event_type="archive_failed", source_endpoint="activity", http_status=status, message_redacted="深度活动数据归档写入失败"))
            session.add(ActivityWindow(
                repository_id=repo.repository_id,
                depth="deep",
                window_start=window_start,
                window_end=window_end,
                commits_count=activity["commits_count"],
                issues_opened_count=activity["issues_opened_count"],
                issues_closed_count=activity["issues_closed_count"],
                pulls_opened_count=activity["pulls_opened_count"],
                pulls_merged_count=activity["pulls_merged_count"],
                releases_count=activity["releases_count"],
                coverage=depth_coverage,
                collected_at=collected_at,
                details_json=json.dumps({"coverage_by_module": activity["coverage_by_module"]}, ensure_ascii=False),
                source_archive_path=activity_archive,
            ))
        result = AnalysisResult(
            repository_id=repo.repository_id,
            analysis_kind=task.depth,
            metric_version="metrics-v1",
            window_start=window_start if task.depth == "deep" else None,
            window_end=window_end if task.depth == "deep" else None,
            source_collected_at=collected_at,
            calculated_at=utc_now(),
            coverage=coverage,
            metrics_json=json.dumps(metrics, ensure_ascii=False),
            limitations_json=json.dumps(limitations, ensure_ascii=False),
            valid_sample_size=1,
        )
        if task.depth == "deep":
            session.add(AnalysisResult(
                repository_id=repo.repository_id,
                analysis_kind="basic",
                metric_version="metrics-v1",
                source_collected_at=collected_at,
                calculated_at=utc_now(),
                coverage="complete",
                metrics_json=json.dumps(profile_metrics, ensure_ascii=False),
                limitations_json=json.dumps(["关注度指标不等于代码质量"], ensure_ascii=False),
                valid_sample_size=1,
            ))
        session.add(result)
        task.status = "partial" if coverage == "partial" else "succeeded"
        task.phase = None
        task.progress_percent = None
        task.message = "基础数据与分析已完成" if coverage == "complete" else "基础数据已保存，部分深度模块未完整采集"
        task.finished_at = utc_now()
        task.heartbeat_at = task.finished_at
        task.lease_until = None
        session.add(CollectionLog(request_id=task.task_id, task_id=task.task_id, repository_id=repo.repository_id, event_type="collection_completed", source_endpoint=f"/repositories/{repo.repository_id}", http_status=status, message_redacted=f"depth={task.depth}; coverage={coverage}"))
        session.commit()
    except Exception as exc:
        session.rollback()
        task = session.get(CollectionTask, task_id)
        if task:
            _finish_failed(session, task, "WORKER_EXECUTION_FAILED", f"采集任务执行失败：{type(exc).__name__}")
    finally:
        session.close()


def _parse(value: str | None):
    from backend.app.core.clock import parse_github_datetime

    return parse_github_datetime(value)


def _collect_deep(github: GitHubClient, full_name: str, start, end, task: CollectionTask) -> tuple[dict[str, Any], str]:
    start_iso = start.isoformat(timespec="seconds") + "Z"
    end_iso = end.isoformat(timespec="seconds") + "Z"
    raw: dict[str, Any] = {}
    coverage: dict[str, str] = {}
    data: dict[str, list[dict[str, Any]]] = {}
    calls = (
        ("commits", lambda: github.list_commits(full_name, start_iso, end_iso)),
        ("issues", lambda: github.list_issues(full_name, start_iso, "all")),
        ("pulls", lambda: github.list_pulls(full_name, "closed")),
        ("releases", lambda: github.list_releases(full_name)),
    )
    for name, fetch in calls:
        try:
            rows, complete, pages = fetch()
            data[name] = rows
            raw[name] = pages
            coverage[name] = "complete" if complete else "partial"
        except AppError as exc:
            data[name] = []
            raw[name] = {"error": exc.code, "message": exc.message}
            coverage[name] = "partial"
    try:
        archive_json(task.repository_id, task.task_id, "deep_responses", raw)
    except OSError:
        pass

    def in_window(value: str | None, lower=start, upper=end) -> bool:
        parsed = _parse(value)
        return parsed is not None and lower <= parsed <= upper

    issues = [item for item in data["issues"] if "pull_request" not in item]
    pulls = data["pulls"]
    releases = data["releases"]
    release_start = end - timedelta(days=365)
    values = {
        "commits_count": len(data["commits"]) if coverage["commits"] == "complete" else None,
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
    return values, values["coverage"]


def _finish_failed(session: Session, task: CollectionTask, code: str, message: str, details: dict[str, Any] | None = None) -> None:
    task.status = "failed"
    task.phase = None
    task.error_code = code
    task.error_message = message[:1000]
    task.message = message[:1000]
    task.finished_at = utc_now()
    task.lease_until = None
    session.add(CollectionLog(request_id=task.task_id, task_id=task.task_id, repository_id=task.repository_id, event_type="collection_failed", http_status=details.get("http_status") if details else None, message_redacted=f"{code}: {message[:800]}"))
    session.commit()

import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.config import get_settings
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import AnalysisResult, CollectionTask, Dataset, DatasetRepository, Repository, RepositorySnapshot
from backend.app.persistence.db import begin_immediate


LIBRARY_ID = "library-default"
RESEARCH_ID = "research-2026-v1"
FEATURED_ID = "featured-default"


def ensure_default_datasets(session: Session) -> None:
    defaults = (
        (LIBRARY_ID, "我的分析库", "library", None, None, "共享课程工作区的仓库集合"),
        (RESEARCH_ID, "开源软件研究样本 v1", "research", "selection-v1", None, "等待通过真实采样清单导入冻结成员；空样本不是研究结果"),
        (FEATURED_ID, "首页精选", "featured", None, None, "人工维护的公开仓库集合"),
    )
    for dataset_id, name, kind, rules, frozen_at, description in defaults:
        if session.get(Dataset, dataset_id) is None:
            session.add(Dataset(dataset_id=dataset_id, name=name, type=kind, rules_version=rules, frozen_at=frozen_at, description=description))
    session.commit()


def repository_from_github(session: Session, payload: dict[str, Any]) -> Repository:
    repository_id = payload.get("id")
    full_name = payload.get("full_name")
    if not isinstance(repository_id, int) or isinstance(repository_id, bool) or repository_id <= 0 or not isinstance(full_name, str):
        raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 仓库资料缺少有效 ID 或 full_name")
    from backend.app.integrations.github.client import validate_full_name

    owner, name = validate_full_name(full_name)
    full_name = f"{owner}/{name}"
    now = utc_now()
    repo = session.get(Repository, repository_id)
    if repo is None:
        repo = session.scalar(select(Repository).where(Repository.full_name == full_name))
    if repo is None:
        repo = Repository(repository_id=repository_id, full_name=full_name, html_url=payload.get("html_url") or f"https://github.com/{full_name}", first_seen_at=now, last_seen_at=now)
        session.add(repo)
    repo.full_name = full_name
    repo.html_url = f"https://github.com/{full_name}"
    repo.description = payload.get("description") if isinstance(payload.get("description"), str) else None
    repo.language = payload.get("language") if isinstance(payload.get("language"), str) else None
    topics = payload.get("topics")
    repo.topics_json = json.dumps([topic for topic in topics if isinstance(topic, str)] if isinstance(topics, list) else [], ensure_ascii=False)
    license_data = payload.get("license") if isinstance(payload.get("license"), dict) else {}
    repo.license_spdx = license_data.get("spdx_id") if isinstance(license_data.get("spdx_id"), str) else None
    repo.created_at = parse_github_datetime(payload.get("created_at"))
    repo.pushed_at = parse_github_datetime(payload.get("pushed_at"))
    repo.github_updated_at = parse_github_datetime(payload.get("updated_at"))
    repo.archived = payload.get("archived") if isinstance(payload.get("archived"), bool) else False
    repo.is_fork = payload.get("fork") if isinstance(payload.get("fork"), bool) else False
    size = payload.get("size")
    repo.size_kb = size if isinstance(size, int) and not isinstance(size, bool) and size >= 0 else None
    repo.last_seen_at = now
    return repo


def make_task(session: Session, repository_id: int, depth: str, *, retry_of: str | None = None, idempotency_key: str | None = None) -> CollectionTask:
    active = session.scalars(
        select(CollectionTask)
        .where(CollectionTask.repository_id == repository_id, CollectionTask.status.in_(["queued", "running"]))
        .order_by(desc(CollectionTask.created_at))
    ).all()
    for existing in active:
        if existing.depth == depth or (depth == "basic" and existing.depth == "deep"):
            return existing
    task = CollectionTask(task_id=str(uuid4()), repository_id=repository_id, depth=depth, status="queued", retry_of=retry_of, idempotency_key=idempotency_key)
    session.add(task)
    session.flush()
    return task


def latest_snapshot(session: Session, repository_id: int) -> RepositorySnapshot | None:
    return session.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_id == repository_id, RepositorySnapshot.valid.is_(True)).order_by(desc(RepositorySnapshot.collected_at), desc(RepositorySnapshot.id)).limit(1))


def latest_analysis(session: Session, repository_id: int, depth: str | None = "basic") -> AnalysisResult | None:
    statement = select(AnalysisResult).where(AnalysisResult.repository_id == repository_id)
    if depth is not None:
        statement = statement.where(AnalysisResult.analysis_kind == depth)
    return session.scalar(statement.order_by(desc(AnalysisResult.source_collected_at), desc(AnalysisResult.result_id)).limit(1))


def latest_task(session: Session, repository_id: int) -> CollectionTask | None:
    return session.scalar(select(CollectionTask).where(CollectionTask.repository_id == repository_id).order_by(desc(CollectionTask.created_at), desc(CollectionTask.task_id)).limit(1))


def analysis_status(session: Session, repository_id: int) -> str:
    analysis = latest_analysis(session, repository_id, None)
    if analysis:
        return "partial" if analysis.coverage == "partial" else "completed"
    task = latest_task(session, repository_id)
    if task is None:
        return "not_started"
    if task.status in ("queued", "running"):
        return "queued" if task.status == "queued" else "processing"
    return task.status if task.status in {"partial", "failed"} else "not_started"


def summary(session: Session, repo: Repository) -> dict[str, Any]:
    snapshot = latest_snapshot(session, repo.repository_id)
    task = latest_task(session, repo.repository_id)
    datasets = session.scalars(select(DatasetRepository.dataset_id).where(DatasetRepository.repository_id == repo.repository_id)).all()
    collected = snapshot.collected_at if snapshot else None
    data_status = "missing" if collected is None else ("fresh" if utc_now() - collected <= timedelta(hours=get_settings().base_refresh_hours) else "stale")
    return {
        "repository_id": repo.repository_id,
        "full_name": repo.full_name,
        "description": repo.description,
        "language": repo.language,
        "stars": snapshot.stars if snapshot else None,
        "forks": snapshot.forks if snapshot else None,
        "created_at": iso_z(repo.created_at),
        "pushed_at": iso_z(snapshot.pushed_at if snapshot else repo.pushed_at),
        "archived": repo.archived,
        "analysis_status": analysis_status(session, repo.repository_id),
        "data_status": data_status,
        "last_successful_collection_at": iso_z(collected),
        "latest_task_id": task.task_id if task else None,
        "datasets": sorted(datasets),
    }


def preview(payload: dict[str, Any], already_in_library: bool) -> dict[str, Any]:
    repository_id = payload.get("id")
    full_name = payload.get("full_name")
    if not isinstance(repository_id, int) or isinstance(repository_id, bool) or repository_id <= 0 or not isinstance(full_name, str):
        raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 仓库预览缺少有效 ID 或 full_name")
    from backend.app.integrations.github.client import validate_full_name

    owner, name = validate_full_name(full_name)
    full_name = f"{owner}/{name}"
    archived, is_fork = payload.get("archived"), payload.get("fork")
    if not isinstance(archived, bool) or not isinstance(is_fork, bool):
        raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 仓库预览缺少有效 archived 或 fork 字段")
    stars = payload.get("stargazers_count")
    forks = payload.get("forks_count")
    return {
        "repository_id": repository_id,
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "description": payload.get("description") if isinstance(payload.get("description"), str) else None,
        "language": payload.get("language") if isinstance(payload.get("language"), str) else None,
        "stars": stars if isinstance(stars, int) and not isinstance(stars, bool) and stars >= 0 else None,
        "forks": forks if isinstance(forks, int) and not isinstance(forks, bool) and forks >= 0 else None,
        "archived": archived,
        "is_fork": is_fork,
        "already_in_library": already_in_library,
        "github_updated_at": iso_z(parse_github_datetime(payload.get("updated_at"))),
    }


def membership_exists(session: Session, repository_id: int) -> bool:
    return session.get(DatasetRepository, (LIBRARY_ID, repository_id)) is not None


def enqueue_add(session: Session, github_payload: dict[str, Any], auto_analyze: bool, depth: str, idempotency_key: str | None) -> tuple[dict[str, Any], int]:
    begin_immediate(session)
    repo = repository_from_github(session, github_payload)
    session.flush()
    membership = session.get(DatasetRepository, (LIBRARY_ID, repo.repository_id))
    created = membership is None
    if created:
        session.add(DatasetRepository(dataset_id=LIBRARY_ID, repository_id=repo.repository_id))
    task = None
    if auto_analyze and (created or latest_analysis(session, repo.repository_id) is None):
        task = make_task(session, repo.repository_id, depth, idempotency_key=idempotency_key)
    elif auto_analyze:
        task = session.scalar(select(CollectionTask).where(CollectionTask.repository_id == repo.repository_id, CollectionTask.status.in_(["queued", "running"])).order_by(desc(CollectionTask.created_at)).limit(1))
    result = {
        "repository_id": repo.repository_id,
        "membership_created": created,
        "analysis_status": ("queued" if task and task.status == "queued" else ("processing" if task and task.status == "running" else analysis_status(session, repo.repository_id))),
        "task_id": task.task_id if task else None,
    }
    session.commit()
    return result, 201 if created else 200


def enqueue_refresh(session: Session, repository_id: int, depth: str, idempotency_key: str | None, force: bool = False) -> dict[str, Any]:
    if session.get(Repository, repository_id) is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    begin_immediate(session)
    existing_ids = {task.task_id for task in session.scalars(select(CollectionTask).where(CollectionTask.repository_id == repository_id, CollectionTask.status.in_(["queued", "running"]))).all()}
    if not existing_ids and not force and depth == "basic":
        snapshot = latest_snapshot(session, repository_id)
        analysis = latest_analysis(session, repository_id, "basic")
        if snapshot and analysis and analysis.source_collected_at == snapshot.collected_at and utc_now() - snapshot.collected_at <= timedelta(hours=get_settings().base_refresh_hours):
            completed = session.scalar(
                select(CollectionTask)
                .where(CollectionTask.repository_id == repository_id, CollectionTask.depth == "basic", CollectionTask.status.in_(["succeeded", "partial"]))
                .order_by(desc(CollectionTask.finished_at))
                .limit(1)
            )
            if completed:
                result = {"task_id": completed.task_id, "reused": True, "status": completed.status}
                session.commit()
                return result
    task = make_task(session, repository_id, depth, idempotency_key=idempotency_key)
    result = {"task_id": task.task_id, "reused": task.task_id in existing_ids, "status": task.status}
    session.commit()
    return result


def add_idempotency_response(session: Session, operation: str, key: str | None, payload: dict[str, Any], status_code: int) -> tuple[dict[str, Any], int]:
    if not key:
        return payload, status_code
    from backend.app.persistence.models import RequestIdempotency

    now = utc_now()
    row = session.get(RequestIdempotency, key)
    if row and row.expires_at > now:
        if row.operation != operation:
            raise AppError(409, "CONFLICTING_OPERATION", "Idempotency-Key 已用于其他操作")
        return json.loads(row.response_json), row.status_code
    if row:
        session.delete(row)
    old_tasks = session.scalars(select(CollectionTask).where(CollectionTask.idempotency_key == key)).all()
    for task in old_tasks:
        task.idempotency_key = None
    session.add(RequestIdempotency(key=key, operation=operation, created_at=now, expires_at=now + timedelta(hours=24), response_json=json.dumps(payload), status_code=status_code))
    session.commit()
    return payload, status_code


def cached_idempotency_response(session: Session, operation: str, key: str | None) -> tuple[dict[str, Any], int] | None:
    if not key:
        return None
    from backend.app.persistence.models import RequestIdempotency

    row = session.get(RequestIdempotency, key)
    if row is None:
        return None
    if row.expires_at <= utc_now():
        session.delete(row)
        for task in session.scalars(select(CollectionTask).where(CollectionTask.idempotency_key == key)).all():
            task.idempotency_key = None
        session.commit()
        return None
    if row.operation != operation:
        raise AppError(409, "CONFLICTING_OPERATION", "Idempotency-Key 已用于其他操作")
    return json.loads(row.response_json), row.status_code

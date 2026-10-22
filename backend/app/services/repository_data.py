"""Clear collected data and invalidate affected featured-bundle memberships."""

import logging
import shutil
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.exceptions import AppError
from backend.app.persistence.db import begin_immediate
from backend.app.persistence.models import (
    ActivityWindow,
    AnalysisResult,
    CollectionCheckpoint,
    CollectionLog,
    CollectionTask,
    DatasetImportJob,
    DatasetRepository,
    Repository,
    RepositoryActivityEvent,
    RepositoryInsightRun,
    RepositorySnapshot,
)
from backend.app.pipeline import collection_archive
from backend.app.services.dataset_import import invalidate_featured_import_for_repositories
from backend.app.services.repositories import LIBRARY_ID


logger = logging.getLogger("repovantage.repositories.data")


def clear_repository_data(
    session: Session,
    repository_ids: list[int],
    *,
    remove_from_library: bool = False,
) -> dict:
    ids = sorted(set(repository_ids))
    if not ids or any(repository_id <= 0 for repository_id in ids) or len(ids) > 100:
        raise AppError(422, "VALIDATION_ERROR", "请选择 1–100 个不同的有效仓库")

    raw_root = get_settings().raw_data_path.resolve()
    page_root = collection_archive.COLLECTED_ROOT.resolve()
    archive_directories = {}
    for repository_id in ids:
        raw_directory = (raw_root / str(repository_id)).resolve()
        page_directory = (page_root / str(repository_id)).resolve()
        if (
            raw_directory == raw_root
            or not raw_directory.is_relative_to(raw_root)
            or page_directory == page_root
            or not page_directory.is_relative_to(page_root)
        ):
            raise AppError(500, "REPOSITORY_ARCHIVE_PATH_INVALID", "仓库原始归档路径无效")
        archive_directories[repository_id] = (raw_directory, page_directory)

    begin_immediate(session)
    try:
        repositories = session.scalars(select(Repository).where(Repository.repository_id.in_(ids))).all()
        found_ids = {repository.repository_id for repository in repositories}
        missing_ids = [repository_id for repository_id in ids if repository_id not in found_ids]
        if missing_ids:
            raise AppError(404, "RESOURCE_NOT_FOUND", "部分仓库不存在或已被删除", {"repository_ids": missing_ids})

        active_task = session.execute(
            select(CollectionTask.task_id, CollectionTask.repository_id)
            .where(CollectionTask.repository_id.in_(ids), CollectionTask.status.in_(("queued", "running")))
            .limit(1)
        ).first()
        if active_task:
            raise AppError(
                409,
                "CONFLICTING_OPERATION",
                "所选仓库中有正在排队或采集的任务，请等待任务结束后再清除",
                {"task_id": active_task.task_id, "repository_id": active_task.repository_id},
            )

        active_import = session.scalar(
            select(DatasetImportJob.task_id)
            .where(DatasetImportJob.status.in_(("queued", "running")))
            .limit(1)
        )
        if active_import:
            raise AppError(409, "CONFLICTING_OPERATION", "精选数据导入期间不能清除仓库数据，请等待导入结束")

        invalidated_featured_ids = invalidate_featured_import_for_repositories(session, ids)

        removed_from_library = set()
        if remove_from_library:
            removed_from_library = set(session.scalars(
                select(DatasetRepository.repository_id).where(
                    DatasetRepository.dataset_id == LIBRARY_ID,
                    DatasetRepository.repository_id.in_(ids),
                )
            ).all())
            session.execute(
                delete(DatasetRepository).where(
                    DatasetRepository.dataset_id == LIBRARY_ID,
                    DatasetRepository.repository_id.in_(ids),
                )
            )

        deleted_by_repository = {repository_id: {} for repository_id in ids}
        records = {
            "snapshots": RepositorySnapshot,
            "activity_events": RepositoryActivityEvent,
            "activity_windows": ActivityWindow,
            "analysis_results": AnalysisResult,
            "insight_runs": RepositoryInsightRun,
            "checkpoints": CollectionCheckpoint,
            "collection_logs": CollectionLog,
        }
        for key, model in records.items():
            grouped_counts = session.execute(
                select(model.repository_id, func.count())
                .where(model.repository_id.in_(ids))
                .group_by(model.repository_id)
            ).all()
            for repository_id, count in grouped_counts:
                deleted_by_repository[repository_id][key] = int(count)
            session.execute(delete(model).where(model.repository_id.in_(ids)))
        for counts in deleted_by_repository.values():
            for key in records:
                counts.setdefault(key, 0)
        session.commit()
    except Exception:
        session.rollback()
        raise

    results = []
    for repository_id in ids:
        raw_directory, page_directory = archive_directories[repository_id]
        removed = {}
        for kind, directory in (("raw_archive_directory_removed", raw_directory), ("collection_archive_directory_removed", page_directory)):
            existed = directory.exists()
            try:
                if existed:
                    shutil.rmtree(directory)
            except OSError as exc:
                logger.exception("Could not remove repository %s repository_id=%s", kind, repository_id)
                raise AppError(
                    500,
                    "REPOSITORY_ARCHIVE_CLEANUP_FAILED",
                    "数据库记录已清除，但原始归档删除失败；请重试清除",
                    {"repository_id": repository_id, "archive_kind": kind},
                ) from exc
            removed[kind] = existed
        results.append({
            "repository_id": repository_id,
            "removed_from_library": repository_id in removed_from_library,
            "removed_from_featured": repository_id in invalidated_featured_ids,
            **deleted_by_repository[repository_id],
            **removed,
        })
    return {"repositories": results}

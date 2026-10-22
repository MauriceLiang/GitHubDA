"""Execute durable featured dataset import jobs in the application Worker."""

import json
import logging
import os
import shutil
from datetime import date, timedelta
from pathlib import Path, PurePosixPath
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.clock import iso_z, utc_now
from backend.app.core.config import get_settings
from backend.app.core.exceptions import AppError
from backend.app.persistence.db import begin_immediate
from backend.app.persistence.models import DatasetImportJob, DatasetImportStagingRecord
from backend.app.pipeline.raw_archive import archive_json
from backend.app.services import dataset_import
from backend.app.services.dataset_import import BundleError


logger = logging.getLogger("repovantage.worker.dataset_import")
STAGING_BATCH_SIZE = 500
MAX_ATTEMPTS = 3


def execute_dataset_import_job(
    session_factory: Callable[[], Session],
    task_id: str,
    worker_id: str,
    lease_seconds: int,
) -> None:
    with session_factory() as session:
        job = session.get(DatasetImportJob, task_id)
        if job is None or job.status != "running" or job.lease_owner != worker_id:
            return
        attempt = job.attempt
        expected_hash = job.bundle_hash

    _update_job(
        session_factory,
        task_id,
        worker_id,
        attempt,
        lease_seconds,
        phase="validating",
        progress_kind="indeterminate",
        progress_percent=None,
        message="正在校验精选数据包",
        current_file=None,
    )
    metadata, records, bundle_hash = dataset_import._load_bundle(dataset_import.BUNDLE_ROOT)
    if bundle_hash != expected_hash or metadata["version"] != job.bundle_version:
        raise BundleError("任务对应的精选数据包已发生变化，请刷新状态后重新导入")
    record_counts = {name: len(rows) for name, rows in records.items()}
    with session_factory() as session:
        dataset_import.record_bundle_verification(session, record_counts)

    total_records = sum(record_counts.values())
    _stage_records(session_factory, task_id, worker_id, attempt, lease_seconds, records, total_records)
    del records
    with session_factory() as session:
        staged_count = int(session.scalar(
            select(func.count()).select_from(DatasetImportStagingRecord)
            .where(DatasetImportStagingRecord.task_id == task_id)
        ) or 0)
    if staged_count != total_records:
        raise BundleError("暂存记录数量与校验结果不一致，请重试导入")
    _update_job(
        session_factory,
        task_id,
        worker_id,
        attempt,
        lease_seconds,
        phase="finalizing",
        progress_kind="indeterminate",
        progress_percent=None,
        message="正在准备安全详情归档",
        current_file=None,
    )

    job_created_at = _job_created_at(session_factory, task_id)
    archive_day = job_created_at.date()
    raw_root = get_settings().raw_data_path.resolve()
    temp_relative = Path(".dataset-import-staging") / task_id
    temp_root = raw_root / temp_relative
    with session_factory() as session:
        archive_paths = _write_insight_archives(_StagedRecords(session, task_id), task_id, temp_root, archive_day)
    _save_archive_state(
        session_factory,
        task_id,
        worker_id,
        attempt,
        lease_seconds,
        str(temp_relative),
        archive_paths,
    )
    _publish_archives(raw_root, temp_root, archive_paths)
    _update_job(
        session_factory,
        task_id,
        worker_id,
        attempt,
        lease_seconds,
        phase="importing",
        progress_kind="indeterminate",
        progress_percent=None,
        message="正在写入本地分析库",
        current_file=None,
    )

    with session_factory() as session:
        result = dataset_import._import_records(
            session,
            metadata,
            _StagedRecords(session, task_id),
            bundle_hash,
            task_id=task_id,
            worker_id=worker_id,
            attempt=attempt,
            archive_paths=archive_paths,
        )
    shutil.rmtree(temp_root, ignore_errors=True)
    logger.info(
        "Featured dataset import completed task_id=%s version=%s records=%s",
        task_id,
        metadata["version"],
        result.get("event_count", 0),
    )


def _stage_records(session_factory, task_id, worker_id, attempt, lease_seconds, records, total_records) -> None:
    with session_factory() as session:
        begin_immediate(session)
        job = _owned_job(session, task_id, worker_id, attempt)
        staged_count = int(session.scalar(
            select(func.count()).select_from(DatasetImportStagingRecord)
            .where(DatasetImportStagingRecord.task_id == task_id)
        ) or 0)
        job.total_records = total_records
        job.processed_records = staged_count
        job.phase = "staging"
        job.progress_kind = "records"
        job.progress_percent = min(90, int(staged_count * 90 / total_records)) if total_records else 90
        job.message = "正在准备导入数据"
        job.updated_at = utc_now()
        job.lease_until = job.updated_at + timedelta(seconds=lease_seconds)
        session.commit()

    processed = staged_count
    for record_type, rows in records.items():
        with session_factory() as session:
            start_ordinal = int(session.scalar(
                select(func.max(DatasetImportStagingRecord.ordinal))
                .where(
                    DatasetImportStagingRecord.task_id == task_id,
                    DatasetImportStagingRecord.record_type == record_type,
                )
            ) or -1) + 1
        for offset in range(start_ordinal, len(rows), STAGING_BATCH_SIZE):
            batch = rows[offset:offset + STAGING_BATCH_SIZE]
            now = utc_now()
            with session_factory() as session:
                begin_immediate(session)
                job = _owned_job(session, task_id, worker_id, attempt)
                session.add_all([
                    DatasetImportStagingRecord(
                        task_id=task_id,
                        record_type=record_type,
                        record_key=str(index),
                        ordinal=index,
                        repository_id=dataset_import._positive_int(row.get("repository_id")),
                        payload_json=json.dumps(row, ensure_ascii=False, separators=(",", ":")),
                        created_at=now,
                    )
                    for index, row in enumerate(batch, start=offset)
                ])
                processed += len(batch)
                job.phase = "staging"
                job.progress_kind = "records"
                job.processed_records = processed
                job.total_records = total_records
                job.progress_percent = min(90, int(processed * 90 / total_records)) if total_records else 90
                job.current_file = record_type
                job.message = f"正在暂存 {record_type}"
                job.updated_at = now
                job.lease_until = now + timedelta(seconds=lease_seconds)
                session.commit()


class _StagedRecords:
    """Load one staged record type or repository at a time."""

    def __init__(self, session: Session, task_id: str) -> None:
        self._session = session
        self._task_id = task_id

    def __getitem__(self, record_type: str) -> list[dict]:
        return self._load(record_type)

    def for_repository(self, record_type: str, repository_id: int) -> list[dict]:
        return self._load(record_type, repository_id)

    def _load(self, record_type: str, repository_id: int | None = None) -> list[dict]:
        statement = (
            select(DatasetImportStagingRecord.payload_json)
            .where(
                DatasetImportStagingRecord.task_id == self._task_id,
                DatasetImportStagingRecord.record_type == record_type,
            )
            .order_by(DatasetImportStagingRecord.ordinal)
        )
        if repository_id is not None:
            statement = statement.where(DatasetImportStagingRecord.repository_id == repository_id)
        values = []
        result = self._session.execute(statement).scalars().yield_per(STAGING_BATCH_SIZE)
        try:
            for payload_json in result:
                try:
                    value = json.loads(payload_json)
                except (TypeError, ValueError) as exc:
                    raise BundleError("暂存记录无法解析，请重试导入") from exc
                if not isinstance(value, dict):
                    raise BundleError("暂存记录格式无效，请重试导入")
                values.append(value)
        finally:
            result.close()
        return values


def _write_insight_archives(records, task_id: str, temp_root: Path, archive_day: date) -> dict[int, str]:
    repository_reader = getattr(records, "for_repository", None)
    archive_paths: dict[int, str] = {}
    for row in records["insights"]:
        repository_id = dataset_import._positive_int(row.get("repository_id"))
        if repository_id is None:
            raise BundleError("分析详情缺少仓库 ID")
        start = dataset_import.parse_github_datetime(row.get("window_start"))
        end = dataset_import.parse_github_datetime(row.get("window_end"))
        if start is None or end is None:
            raise BundleError("分析详情时间窗口无效")
        sources = row.get("sources") if isinstance(row.get("sources"), dict) else {}
        details = {}
        for module in dataset_import.MODULES:
            module_rows = (
                repository_reader(f"details/{module}", repository_id)
                if callable(repository_reader)
                else [item for item in records[f"details/{module}"] if dataset_import._positive_int(item.get("repository_id")) == repository_id]
            )
            details[module] = []
            for detail in module_rows:
                if dataset_import._positive_int(detail.get("repository_id")) != repository_id or not isinstance(detail.get("item"), dict):
                    raise BundleError("详情归档记录无效")
                details[module].append(detail["item"])
        payload = {module: {"pages": [details[module]]} for module in dataset_import.MODULES}
        payload["_meta"] = {
            "schema_version": 2,
            "sources": sources,
            "window_start": iso_z(start),
            "window_end": iso_z(end),
        }
        archive_paths[repository_id] = archive_json(repository_id, task_id, "activity", payload, root=temp_root, archive_date=archive_day)
    return archive_paths


def _save_archive_state(session_factory, task_id, worker_id, attempt, lease_seconds, temp_relative, archive_paths) -> None:
    with session_factory() as session:
        begin_immediate(session)
        job = _owned_job(session, task_id, worker_id, attempt)
        state = _json_object(job.staging_state_json)
        state["archive_temp_directory"] = temp_relative
        state["archive_paths"] = {str(key): value for key, value in archive_paths.items()}
        job.staging_state_json = json.dumps(state, ensure_ascii=False)
        job.phase = "finalizing"
        job.message = "正在校验导入结果"
        job.updated_at = utc_now()
        job.lease_until = job.updated_at + timedelta(seconds=lease_seconds)
        session.commit()


def _publish_archives(raw_root: Path, temp_root: Path, archive_paths: dict[int, str]) -> None:
    for relative in archive_paths.values():
        safe_relative = _safe_relative(relative)
        source = (temp_root / safe_relative).resolve()
        target = (raw_root / safe_relative).resolve()
        if not source.is_relative_to(temp_root.resolve()) or not target.is_relative_to(raw_root.resolve()):
            raise BundleError("详情归档路径不安全")
        if not source.is_file():
            raise BundleError("详情归档暂存文件缺失，请重试导入")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, target)


def fail_dataset_import_job(session_factory, task_id: str, worker_id: str, error: Exception) -> None:
    with session_factory() as session:
        job = session.get(DatasetImportJob, task_id)
        if job is None or job.status != "running" or job.lease_owner != worker_id:
            return
        if isinstance(error, AppError):
            code = error.code
            message = error.message
        elif isinstance(error, BundleError):
            code = "DATASET_BUNDLE_INVALID"
            message = str(error)
        else:
            code = "DATASET_IMPORT_FAILED"
            message = "精选数据导入失败，请检查 Worker 日志后重试"
        state = _json_object(job.staging_state_json)
        job.status = "failed"
        job.phase = None
        job.progress_percent = None
        job.progress_kind = "unknown"
        job.error_code = code
        job.error_message = message
        job.message = "导入失败，可重试"
        job.updated_at = utc_now()
        job.finished_at = job.updated_at
        job.heartbeat_at = job.updated_at
        job.lease_owner = None
        job.lease_until = None
        session.commit()

    cleanup_dataset_import_artifacts(task_id, state)


def cleanup_dataset_import_artifacts(task_id: str, state: dict) -> None:
    raw_root = get_settings().raw_data_path.resolve()
    archive_paths = state.get("archive_paths") if isinstance(state.get("archive_paths"), dict) else {}
    for relative in archive_paths.values():
        try:
            target = (raw_root / _safe_relative(str(relative))).resolve()
            if target.is_relative_to(raw_root) and target.is_file():
                target.unlink()
        except (OSError, ValueError):
            logger.warning("Could not remove failed dataset import archive task_id=%s", task_id)
    try:
        temp_root_value = _safe_relative(str(state.get("archive_temp_directory", f".dataset-import-staging/{task_id}")))
        temp_root = (raw_root / temp_root_value).resolve()
        if temp_root.is_relative_to(raw_root):
            shutil.rmtree(temp_root, ignore_errors=True)
    except ValueError:
        logger.warning("Could not remove failed dataset import staging directory task_id=%s", task_id)


def _update_job(session_factory, task_id, worker_id, attempt, lease_seconds, **values) -> None:
    with session_factory() as session:
        begin_immediate(session)
        job = _owned_job(session, task_id, worker_id, attempt)
        for key, value in values.items():
            setattr(job, key, value)
        now = utc_now()
        job.updated_at = now
        job.heartbeat_at = now
        job.lease_until = now + timedelta(seconds=lease_seconds)
        session.commit()


def _owned_job(session: Session, task_id: str, worker_id: str, attempt: int) -> DatasetImportJob:
    job = session.get(DatasetImportJob, task_id)
    now = utc_now()
    if (
        job is None
        or job.status != "running"
        or job.lease_owner != worker_id
        or job.attempt != attempt
        or job.lease_until is None
        or job.lease_until <= now
    ):
        raise AppError(409, "DATASET_IMPORT_TASK_STALE", "导入任务已失去执行权")
    return job


def _job_created_at(session_factory, task_id: str):
    with session_factory() as session:
        job = session.get(DatasetImportJob, task_id)
        if job is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "导入任务不存在")
        return job.created_at


def _safe_relative(value: str) -> Path:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts) or "\\" in value:
        raise ValueError("unsafe relative path")
    return Path(*path.parts)


def _json_object(value: str | None) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}

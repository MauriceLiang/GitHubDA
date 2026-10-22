"""Validate and import the built-in, sanitized featured dataset bundle."""

import gzip
import hashlib
import json
import logging
import re
import stat
import tempfile
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.config import PROJECT_ROOT
from backend.app.core.exceptions import AppError
from backend.app.persistence.db import begin_immediate
from backend.app.persistence.models import (
    ActivityWindow,
    AnalysisResult,
    Dataset,
    DatasetRepository,
    Repository,
    RepositoryActivityEvent,
    RepositoryInsightRun,
    RepositorySnapshot,
)
from backend.app.services.repositories import FEATURED_ID, LIBRARY_ID, repository_from_github


logger = logging.getLogger("repovantage.dataset_import")
BUNDLE_ROOT = (PROJECT_ROOT / "data" / "datasets" / "featured-v1").resolve()
BUNDLE_MAX_BYTES = 256 * 1024 * 1024
UNCOMPRESSED_MAX_BYTES = 1024 * 1024 * 1024
MAX_RECORDS = 1_000_000
MODULES = ("commits", "issues", "pulls", "releases")
DATA_FILES = (
    "repositories.jsonl.gz",
    "snapshots.jsonl.gz",
    "memberships.jsonl.gz",
    "analysis.jsonl.gz",
    "insights.jsonl.gz",
    "coverage.jsonl.gz",
    *(f"events/{module}.jsonl.gz" for module in MODULES),
    *(f"details/{module}.jsonl.gz" for module in MODULES),
)
REQUIRED_FILES = {"dataset.json", *DATA_FILES, "README.md", "DATA_NOTICE.md"}
SCHEMA_FILES = {"schemas/repository.schema.json", "schemas/event.schema.json", "schemas/coverage.schema.json"}
ALLOWED_FILES = REQUIRED_FILES | SCHEMA_FILES
HASH_LINE = re.compile(r"^([a-f0-9]{64})  (.+)$")
EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
CREDENTIAL_PATTERN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})", re.IGNORECASE)
MACHINE_PATH_PATTERN = re.compile(r"(?:/Users/[^\s\"<>]+|/private/var/[^\s\"<>]+|[A-Z]:\\Users\\[^\s\"<>]+)")


class BundleError(ValueError):
    """The bundle is missing, corrupt, unsafe, or not supported."""


@contextmanager
def _bundle_directory(source: Path) -> Iterator[Path]:
    source = source.expanduser().resolve()
    if source.is_dir():
        yield source
        return
    if not source.is_file() or not zipfile.is_zipfile(source):
        raise BundleError("数据包目录或 ZIP 不存在或格式无效")
    if source.stat().st_size > BUNDLE_MAX_BYTES:
        raise BundleError("精选数据包超过 256 MiB 限制")
    with tempfile.TemporaryDirectory(prefix="repovantage-bundle-") as temporary:
        root = Path(temporary)
        total_size = 0
        count = 0
        seen_names = set()
        try:
            with zipfile.ZipFile(source) as archive:
                for item in archive.infolist():
                    name = item.filename
                    path_name = name[:-1] if item.is_dir() and name.endswith("/") else name
                    parts = path_name.split("/")
                    if not path_name or name.startswith("/") or any(part in {"", ".", ".."} for part in parts) or "\\" in name or "\x00" in name or ":" in name:
                        raise BundleError("ZIP 包含不安全的文件路径")
                    if name in seen_names:
                        raise BundleError("ZIP 包含重复的文件路径")
                    seen_names.add(name)
                    mode = item.external_attr >> 16
                    file_type = stat.S_IFMT(mode)
                    if item.is_dir():
                        if file_type not in {0, stat.S_IFDIR}:
                            raise BundleError("ZIP 包含不允许的文件类型")
                        continue
                    count += 1
                    if count > 10_000:
                        raise BundleError("ZIP 文件数量超过限制")
                    if file_type not in {0, stat.S_IFREG}:
                        raise BundleError("ZIP 只允许包含普通文件")
                    total_size += item.file_size
                    if total_size > UNCOMPRESSED_MAX_BYTES or item.file_size > UNCOMPRESSED_MAX_BYTES:
                        raise BundleError("ZIP 解压大小超过限制")
                    target = root.joinpath(*parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    copied = 0
                    with archive.open(item) as src, target.open("wb") as dst:
                        while chunk := src.read(1024 * 1024):
                            copied += len(chunk)
                            if copied > item.file_size or copied > UNCOMPRESSED_MAX_BYTES:
                                raise BundleError("ZIP 实际解压大小超过声明或限制")
                            dst.write(chunk)
                    if copied != item.file_size:
                        raise BundleError("ZIP 文件实际大小与目录声明不一致")
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise BundleError("ZIP 数据包无法安全读取") from exc
        yield root


def verify_dataset_bundle(source: Path) -> dict[str, Any]:
    with _bundle_directory(source) as root:
        metadata, records, bundle_hash = _load_bundle(root)
        return {
            "available": True,
            "dataset_id": metadata["dataset_id"],
            "version": metadata["version"],
            "total_repositories": metadata["total_repositories"],
            "data_as_of": metadata["data_as_of"],
            "bundle_hash": bundle_hash,
            "record_counts": {name: len(rows) for name, rows in records.items()},
        }


def featured_status(session: Session) -> dict[str, Any]:
    imported = int(session.scalar(select(func.count()).select_from(DatasetRepository).where(DatasetRepository.dataset_id == FEATURED_ID)) or 0)
    status: dict[str, Any] = {
        "available": False,
        "dataset_id": FEATURED_ID,
        "version": None,
        "total_repositories": 0,
        "imported_repositories": imported,
        "data_as_of": None,
        "bundle_hash": None,
        "reason": None,
    }
    if not BUNDLE_ROOT.exists():
        status["reason"] = "内置精选数据包尚未生成。候选清单需先核验，并完成真实数据采集。"
        return status
    if not (BUNDLE_ROOT / "dataset.json").is_file() or not (BUNDLE_ROOT / "SHA256SUMS").is_file():
        status["reason"] = "内置精选数据包尚未生成。候选清单需先核验，并完成真实数据采集。"
        return status
    try:
        valid = verify_dataset_bundle(BUNDLE_ROOT)
    except (BundleError, OSError) as exc:
        status["reason"] = str(exc)
        return status
    status.update(valid)
    status["imported_repositories"] = imported
    status["reason"] = None
    return status


def import_featured_bundle(session: Session, source: Path | None = None) -> dict[str, Any]:
    source = BUNDLE_ROOT if source is None else source
    try:
        with _bundle_directory(source) as root:
            metadata, records, bundle_hash = _load_bundle(root)
            result = _import_records(session, metadata, records, bundle_hash)
    except BundleError as exc:
        raise AppError(409, "DATASET_BUNDLE_UNAVAILABLE", str(exc)) from exc
    logger.info(json.dumps({"event": "featured_dataset_imported", "dataset_id": FEATURED_ID, "version": metadata["version"], "bundle_hash": bundle_hash, **result}, separators=(",", ":"), sort_keys=True))
    return {"dataset_id": FEATURED_ID, "version": metadata["version"], "bundle_hash": bundle_hash, **result}


def featured_bundle_archive() -> tuple[Path, str]:
    archive = BUNDLE_ROOT.with_suffix(".zip")
    try:
        directory_status = verify_dataset_bundle(BUNDLE_ROOT)
        archive_status = verify_dataset_bundle(archive)
    except (BundleError, OSError) as exc:
        raise AppError(409, "DATASET_BUNDLE_UNAVAILABLE", "精选数据包 ZIP 缺失或校验失败，请重新导出") from exc
    if archive_status["bundle_hash"] != directory_status["bundle_hash"] or archive_status["version"] != directory_status["version"]:
        raise AppError(409, "DATASET_BUNDLE_UNAVAILABLE", "精选数据包 ZIP 与内置目录版本不一致，请重新导出")
    filename = f"repovantage-dataset-{directory_status['version']}.zip"
    return archive, filename


def dataset_coverage(session: Session, dataset_id: str) -> dict[str, Any]:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "数据集不存在")
    memberships = session.scalars(select(DatasetRepository).where(DatasetRepository.dataset_id == dataset_id).order_by(DatasetRepository.repository_id)).all()
    rows = []
    for membership in memberships:
        repo = session.get(Repository, membership.repository_id)
        window = session.scalar(select(ActivityWindow).where(ActivityWindow.repository_id == membership.repository_id).order_by(desc(ActivityWindow.collected_at)).limit(1))
        details = _json_object(window.details_json) if window else {}
        rows.append({
            "repository_id": membership.repository_id,
            "full_name": repo.full_name if repo else None,
            "coverage": window.coverage if window else "not_collected",
            "window_start": iso_z(window.window_start) if window else None,
            "window_end": iso_z(window.window_end) if window else None,
            "collected_at": iso_z(window.collected_at) if window else None,
            "modules": details.get("coverage_by_module", {}),
        })
    return {"dataset_id": dataset_id, "items": rows}


def _load_bundle(root: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], str]:
    root = root.resolve()
    manifest_path = root / "dataset.json"
    sums_path = root / "SHA256SUMS"
    if not manifest_path.is_file() or not sums_path.is_file():
        raise BundleError("数据包缺少 dataset.json 或 SHA256SUMS")
    if manifest_path.stat().st_size > 1_000_000 or sums_path.stat().st_size > 2_000_000:
        raise BundleError("数据包元信息超过大小限制")
    try:
        metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BundleError("dataset.json 无法解析") from exc
    if not isinstance(metadata, dict) or metadata.get("schema_version") != 1:
        raise BundleError("数据包 schema_version 不受支持")
    if metadata.get("dataset_id") != FEATURED_ID:
        raise BundleError("数据包 dataset_id 与内置精选集不匹配")
    version = metadata.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", version):
        raise BundleError("数据包版本号无效")
    total = metadata.get("total_repositories")
    if type(total) is not int or not 1 <= total <= 10_000:
        raise BundleError("total_repositories 无效")
    if parse_github_datetime(metadata.get("data_as_of")) is None:
        raise BundleError("data_as_of 必须是有效 ISO-8601 时间")
    sum_map = _read_checksums(root, sums_path)
    all_paths = list(root.rglob("*"))
    if any(path.is_symlink() for path in all_paths):
        raise BundleError("数据包不允许包含符号链接")
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).as_posix() != "SHA256SUMS"
    }
    if actual_files != ALLOWED_FILES or actual_files != set(sum_map):
        missing = sorted(ALLOWED_FILES - actual_files)
        extra = sorted(actual_files - ALLOWED_FILES)
        mismatch = missing or extra
        raise BundleError(f"数据包文件清单缺失或包含未声明文件: {', '.join(mismatch[:5])}")
    compressed_size = 0
    for relative, expected in sum_map.items():
        path = root / PurePosixPath(relative)
        target = path.resolve()
        if not target.is_relative_to(root) or not target.is_file() or path.is_symlink():
            raise BundleError("数据包包含不安全的文件路径")
        compressed_size += target.stat().st_size
        if compressed_size > BUNDLE_MAX_BYTES:
            raise BundleError("精选数据包超过 256 MiB 限制")
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise BundleError(f"SHA-256 校验失败: {relative}")
    bundle_hash = hashlib.sha256(sums_path.read_bytes()).hexdigest()

    records = {"repositories": _read_jsonl_gzip(root / "repositories.jsonl.gz")}
    repositories = records["repositories"]
    repository_ids = {_positive_int(row.get("repository_id")) for row in repositories}
    if None in repository_ids or len(repository_ids) != len(repositories) or len(repositories) != total:
        raise BundleError("repositories.jsonl.gz 成员数量或仓库 ID 无效")
    full_names = [row.get("full_name") for row in repositories]
    if any(not isinstance(value, str) or not re.fullmatch(r"[^/\s]{1,100}/[^/\s]{1,100}", value) for value in full_names) or len(set(full_names)) != len(full_names):
        raise BundleError("仓库 full_name 缺失或重复")

    for name in ("snapshots", "memberships", "analysis", "insights", "coverage"):
        records[name] = _read_jsonl_gzip(root / f"{name}.jsonl.gz")
    for module in MODULES:
        records[f"events/{module}"] = _read_jsonl_gzip(root / f"events/{module}.jsonl.gz")
        records[f"details/{module}"] = _read_jsonl_gzip(root / f"details/{module}.jsonl.gz")
    schemas = []
    for relative in SCHEMA_FILES:
        try:
            schema = json.loads((root / relative).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise BundleError(f"schema 文件无法解析: {relative}") from exc
        if (
            not isinstance(schema, dict)
            or schema.get("type") != "object"
            or not isinstance(schema.get("required"), list)
            or not isinstance(schema.get("properties"), dict)
        ):
            raise BundleError(f"schema 文件结构无效: {relative}")
        schemas.append(schema)
    if _contains_sensitive_data(metadata) or any(_contains_sensitive_data(schema) for schema in schemas) or any(
        _contains_sensitive_data(row) for rows in records.values() for row in rows
    ):
        raise BundleError("数据包包含邮箱、凭证或机器绝对路径")
    for relative in ("README.md", "DATA_NOTICE.md"):
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise BundleError(f"数据说明文件无法读取: {relative}") from exc
        if _contains_sensitive_data(text):
            raise BundleError("数据包说明包含邮箱、凭证或机器绝对路径")
    for name in ("snapshots", "memberships", "analysis", "insights", "coverage", *(f"events/{module}" for module in MODULES), *(f"details/{module}" for module in MODULES)):
        if any(_positive_int(row.get("repository_id")) not in repository_ids for row in records[name]):
            raise BundleError(f"{name} 包含数据包外的 repository_id")
    if len(records["memberships"]) != total or len({_positive_int(row.get("repository_id")) for row in records["memberships"]}) != total:
        raise BundleError("精选数据集成员关系必须与仓库列表一一对应")
    member_ids = [_positive_int(row.get("repository_id")) for row in records["memberships"]]
    if any(value is None for value in member_ids) or len(set(member_ids)) != len(member_ids):
        raise BundleError("精选数据集成员关系包含无效或重复仓库")
    if any(not isinstance(row.get("inclusion_reason"), str) or not row["inclusion_reason"].strip() for row in records["memberships"]):
        raise BundleError("精选数据集成员缺少人工纳入理由")
    if any(not isinstance(row.get("item"), dict) for module in MODULES for row in records[f"details/{module}"]):
        raise BundleError("详情文件中存在无效 item")
    for module in MODULES:
        event_ids = []
        expected_type = {"commits": "commit", "issues": "issue", "pulls": "pull_request", "releases": "release"}[module]
        for row in records[f"events/{module}"]:
            source_id = row.get("source_item_id")
            if row.get("event_type") != expected_type or not isinstance(source_id, str) or not source_id:
                raise BundleError(f"events/{module} 包含无效事件类型或 ID")
            event_ids.append((row["repository_id"], source_id))
        if len(event_ids) != len(set(event_ids)):
            raise BundleError(f"events/{module} 存在重复事件")
        if module in {"issues", "pulls"} and any("body" in row["item"] or "body_text" in row["item"] for row in records[f"details/{module}"]):
            raise BundleError(f"details/{module} 包含不允许分发的正文或邮箱字段")
    return metadata, records, bundle_hash


def _read_checksums(root: Path, sums_path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        lines = sums_path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise BundleError("SHA256SUMS 无法读取") from exc
    for line in lines:
        match = HASH_LINE.fullmatch(line)
        if not match:
            raise BundleError("SHA256SUMS 格式无效")
        digest, relative = match.groups()
        path = PurePosixPath(relative)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts) or "\\" in relative:
            raise BundleError("SHA256SUMS 包含不安全路径")
        if relative in result:
            raise BundleError("SHA256SUMS 存在重复路径")
        result[relative] = digest
    if not result or len(result) > 10_000:
        raise BundleError("SHA256SUMS 内容为空或过大")
    return result


def _read_jsonl_gzip(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.stat().st_size > BUNDLE_MAX_BYTES:
        raise BundleError(f"数据文件缺失或超过大小限制: {path.name}")
    rows = []
    uncompressed = 0
    try:
        with gzip.open(path, "rb") as stream:
            for line in stream:
                uncompressed += len(line)
                if uncompressed > UNCOMPRESSED_MAX_BYTES or len(line) > 8_000_000:
                    raise BundleError("JSONL 解压大小或单行长度超过限制")
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise BundleError(f"JSONL 必须逐行包含对象: {path.name}")
                rows.append(value)
                if len(rows) > MAX_RECORDS:
                    raise BundleError("数据包记录数量超过限制")
    except BundleError:
        raise
    except (OSError, EOFError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise BundleError(f"JSONL gzip 文件损坏: {path.name}") from exc
    return rows


def _import_records(session: Session, metadata: dict[str, Any], records: dict[str, list[dict[str, Any]]], bundle_hash: str) -> dict[str, int]:
    now = utc_now()
    source_task_id = f"bundle-{metadata['version']}-{bundle_hash[:12]}"
    begin_immediate(session)
    try:
        dataset = session.get(Dataset, FEATURED_ID)
        if dataset is not None:
            source_meta = _json_object(dataset.source_metadata_json)
            existing_hash = source_meta.get("bundle_hash")
            if existing_hash and existing_hash != bundle_hash:
                raise AppError(409, "DATASET_VERSION_CONFLICT", "featured-default 已导入其他数据包版本；请使用新的数据集版本")
            if dataset.type != "featured":
                raise AppError(409, "DATASET_VERSION_CONFLICT", "featured-default 已被其他数据集类型占用")
        if dataset is None:
            dataset = Dataset(dataset_id=FEATURED_ID, name="首页精选", type="featured", rules_version=metadata["version"], description="随项目分发的真实公开仓库精选数据")
            session.add(dataset)
            session.flush()
        library = session.get(Dataset, LIBRARY_ID)
        if library is None:
            library = Dataset(dataset_id=LIBRARY_ID, name="我的分析库", type="library", description="本地分析仓库")
            session.add(library)
            session.flush()
        dataset.rules_version = metadata["version"]
        dataset.frozen_at = parse_github_datetime(metadata["data_as_of"])
        dataset.source_metadata_json = json.dumps({"version": metadata["version"], "bundle_hash": bundle_hash, "data_as_of": metadata["data_as_of"], "schema_version": metadata["schema_version"]}, ensure_ascii=False)

        repo_rows = {_positive_int(row["repository_id"]): row for row in records["repositories"]}
        repository_objects: dict[int, Repository] = {}
        for repository_id, row in repo_rows.items():
            by_id = session.get(Repository, repository_id)
            by_name = session.scalar(select(Repository).where(Repository.full_name == row["full_name"]))
            if by_id and by_id.full_name.casefold() != row["full_name"].casefold() or by_name and by_name.repository_id != repository_id:
                raise AppError(409, "DATASET_REPOSITORY_CONFLICT", f"仓库身份与本地记录冲突: {row['full_name']}")
            incoming_seen = parse_github_datetime(row.get("last_seen_at")) or parse_github_datetime(metadata["data_as_of"]) or now
            repo = by_id or by_name
            if repo is None or incoming_seen >= repo.last_seen_at:
                repo = repository_from_github(session, _repository_payload(row))
                repo.first_seen_at = parse_github_datetime(row.get("first_seen_at")) or repo.first_seen_at
                repo.last_seen_at = incoming_seen
            repository_objects[repository_id] = repo
        session.flush()

        counts = {"imported_count": 0, "already_present_count": 0, "snapshot_count": 0, "event_count": 0, "warning_count": 0, "skipped_count": 0}
        for repository_id, row in repo_rows.items():
            for dataset_id in (FEATURED_ID, LIBRARY_ID):
                member = session.get(DatasetRepository, (dataset_id, repository_id))
                if member is None:
                    source_member = next(item for item in records["memberships"] if _positive_int(item["repository_id"]) == repository_id)
                    session.add(DatasetRepository(
                        dataset_id=dataset_id,
                        repository_id=repository_id,
                        added_at=parse_github_datetime(source_member.get("added_at")) or now,
                        selection_tier=source_member.get("selection_tier") if dataset_id == FEATURED_ID else None,
                        inclusion_reason=source_member.get("inclusion_reason") if dataset_id == FEATURED_ID else None,
                        selection_source="featured bundle v1" if dataset_id == FEATURED_ID else "featured bundle import",
                    ))
                    if dataset_id == FEATURED_ID:
                        counts["imported_count"] += 1
                elif dataset_id == FEATURED_ID:
                    counts["already_present_count"] += 1

        for row in records["snapshots"]:
            repository_id = _positive_int(row["repository_id"])
            collected_at = parse_github_datetime(row.get("collected_at"))
            if collected_at is None:
                raise BundleError("快照 collected_at 无效")
            latest = session.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_id == repository_id, RepositorySnapshot.valid.is_(True)).order_by(desc(RepositorySnapshot.collected_at), desc(RepositorySnapshot.id)).limit(1))
            if latest and latest.collected_at >= collected_at:
                counts["skipped_count"] += 1
                continue
            session.add(RepositorySnapshot(
                repository_id=repository_id,
                collected_at=collected_at,
                stars=_nonnegative_int(row.get("stars")),
                forks=_nonnegative_int(row.get("forks")),
                open_issues_and_pr_count=_nonnegative_int(row.get("open_issues_and_pr_count")),
                pushed_at=parse_github_datetime(row.get("pushed_at")),
                github_updated_at=parse_github_datetime(row.get("github_updated_at")),
                response_etag=row.get("response_etag") if isinstance(row.get("response_etag"), str) else None,
                source_http_status=row.get("source_http_status") if type(row.get("source_http_status")) is int else 200,
                source_archive_path=None,
                valid=True,
            ))
            counts["snapshot_count"] += 1

        _import_events(session, records, source_task_id, counts, now)
        _import_analysis(session, records["analysis"], counts)
        _import_coverage(session, records["coverage"], counts)
        _import_insights(session, records, source_task_id, counts, now)
        if len(records["analysis"]) < len(repo_rows) or len(records["insights"]) < len(repo_rows) or len(records["coverage"]) < len(repo_rows):
            counts["warning_count"] += 1
        session.commit()
        return counts
    except Exception:
        session.rollback()
        raise


def _import_events(session: Session, records, source_task_id: str, counts: dict[str, int], now) -> None:
    types = {"commits": "commit", "issues": "issue", "pulls": "pull_request", "releases": "release"}
    fields = ("event_at", "created_at", "closed_at", "merged_at", "published_at", "updated_at", "first_seen_at", "last_seen_at")
    for module in MODULES:
        for row in records[f"events/{module}"]:
            repository_id = _positive_int(row.get("repository_id"))
            item_id = row.get("source_item_id")
            if not isinstance(item_id, str) or not item_id or len(item_id) > 64 or row.get("event_type") != types[module]:
                raise BundleError(f"events/{module} 包含无效事件 ID 或类型")
            event = session.scalar(select(RepositoryActivityEvent).where(RepositoryActivityEvent.repository_id == repository_id, RepositoryActivityEvent.event_type == types[module], RepositoryActivityEvent.source_item_id == item_id).limit(1))
            incoming_last_seen = parse_github_datetime(row.get("last_seen_at")) or now
            if event and event.last_seen_at >= incoming_last_seen:
                counts["skipped_count"] += 1
                continue
            values = {name: parse_github_datetime(row.get(name)) for name in fields}
            values.update({
                "repository_id": repository_id,
                "event_type": types[module],
                "source_item_id": item_id,
                "author_key": row.get("author_key") if isinstance(row.get("author_key"), str) else None,
                "is_draft": row.get("is_draft") if type(row.get("is_draft")) is bool else None,
                "is_prerelease": row.get("is_prerelease") if type(row.get("is_prerelease")) is bool else None,
                "source_task_id": source_task_id,
            })
            if event:
                for key, value in values.items():
                    setattr(event, key, value)
            else:
                session.add(RepositoryActivityEvent(**values))
            counts["event_count"] += 1


def _import_analysis(session: Session, rows: list[dict], counts: dict[str, int]) -> None:
    for row in rows:
        repository_id = _positive_int(row.get("repository_id"))
        source_collected_at = parse_github_datetime(row.get("source_collected_at"))
        kind = row.get("analysis_kind")
        if source_collected_at is None or kind not in {"basic", "deep"} or not isinstance(row.get("metrics"), dict):
            raise BundleError("analysis.jsonl.gz 包含无效分析记录")
        existing = session.scalar(select(AnalysisResult).where(AnalysisResult.repository_id == repository_id, AnalysisResult.analysis_kind == kind, AnalysisResult.source_collected_at == source_collected_at).limit(1))
        latest = session.scalar(select(AnalysisResult).where(AnalysisResult.repository_id == repository_id, AnalysisResult.analysis_kind == kind).order_by(desc(AnalysisResult.source_collected_at)).limit(1))
        if existing or (latest and latest.source_collected_at > source_collected_at):
            counts["skipped_count"] += 1
            continue
        session.add(AnalysisResult(
            repository_id=repository_id,
            analysis_kind=kind,
            metric_version=str(row.get("metric_version") or "metrics-v1")[:50],
            window_start=parse_github_datetime(row.get("window_start")),
            window_end=parse_github_datetime(row.get("window_end")),
            source_collected_at=source_collected_at,
            calculated_at=parse_github_datetime(row.get("calculated_at")) or source_collected_at,
            coverage=row.get("coverage") if row.get("coverage") in {"complete", "partial"} else "partial",
            metrics_json=json.dumps(row["metrics"], ensure_ascii=False),
            limitations_json=json.dumps(row.get("limitations") if isinstance(row.get("limitations"), list) else [], ensure_ascii=False),
            valid_sample_size=_nonnegative_int(row.get("valid_sample_size")),
        ))


def _import_coverage(session: Session, rows: list[dict], counts: dict[str, int]) -> None:
    for row in rows:
        repository_id = _positive_int(row.get("repository_id"))
        collected_at = parse_github_datetime(row.get("collected_at"))
        start = parse_github_datetime(row.get("window_start"))
        end = parse_github_datetime(row.get("window_end"))
        if collected_at is None or start is None or end is None or start >= end:
            raise BundleError("coverage.jsonl.gz 包含无效时间窗口")
        existing = session.scalar(select(ActivityWindow).where(ActivityWindow.repository_id == repository_id, ActivityWindow.depth == "deep", ActivityWindow.window_start == start, ActivityWindow.window_end == end, ActivityWindow.collected_at == collected_at).limit(1))
        if existing:
            counts["skipped_count"] += 1
            continue
        latest = session.scalar(select(ActivityWindow).where(ActivityWindow.repository_id == repository_id).order_by(desc(ActivityWindow.collected_at)).limit(1))
        if latest and latest.collected_at > collected_at:
            counts["skipped_count"] += 1
            continue
        module_coverage = row.get("modules") if isinstance(row.get("modules"), dict) else {}
        session.add(ActivityWindow(
            repository_id=repository_id,
            depth="deep",
            window_start=start,
            window_end=end,
            commits_count=_nonnegative_int(row.get("commits_count")),
            issues_opened_count=_nonnegative_int(row.get("issues_opened_count")),
            issues_closed_count=_nonnegative_int(row.get("issues_closed_count")),
            pulls_opened_count=_nonnegative_int(row.get("pulls_opened_count")),
            pulls_merged_count=_nonnegative_int(row.get("pulls_merged_count")),
            releases_count=_nonnegative_int(row.get("releases_count")),
            coverage=row.get("coverage") if row.get("coverage") in {"complete", "partial"} else "partial",
            collected_at=collected_at,
            details_json=json.dumps({"coverage_by_module": module_coverage}, ensure_ascii=False),
            source_archive_path=None,
        ))


def _import_insights(session: Session, records, source_task_id: str, counts: dict[str, int], now) -> None:
    rows_by_repo: dict[int, dict] = {}
    details_by_repo: dict[int, dict[str, list[dict]]] = {}
    for row in records["insights"]:
        rows_by_repo[_positive_int(row["repository_id"])] = row
    for module in MODULES:
        for row in records[f"details/{module}"]:
            details_by_repo.setdefault(_positive_int(row["repository_id"]), {name: [] for name in MODULES})[module].append(row["item"])
    for repository_id, row in rows_by_repo.items():
        analyzed_at = parse_github_datetime(row.get("analyzed_at"))
        start = parse_github_datetime(row.get("window_start"))
        end = parse_github_datetime(row.get("window_end"))
        if analyzed_at is None or start is None or end is None or start >= end:
            raise BundleError("insights.jsonl.gz 包含无效分析窗口")
        fingerprint = hashlib.sha256(f"{FEATURED_ID}:{row.get('metric_version')}:{repository_id}:{analyzed_at.isoformat()}:{row.get('window_end')}".encode()).hexdigest()
        if session.get(RepositoryInsightRun, str(uuid.uuid5(uuid.NAMESPACE_URL, fingerprint))) or session.scalar(select(RepositoryInsightRun.run_id).where(RepositoryInsightRun.input_fingerprint == fingerprint).limit(1)):
            counts["skipped_count"] += 1
            continue
        details = details_by_repo.get(repository_id, {name: [] for name in MODULES})
        sources = row.get("sources") if isinstance(row.get("sources"), dict) else {}
        safe_archive = {module: {"pages": [details[module]]} for module in MODULES}
        safe_archive["_meta"] = {"schema_version": 2, "sources": sources, "window_start": iso_z(start), "window_end": iso_z(end)}
        from backend.app.pipeline.raw_archive import archive_json

        archive_path = archive_json(repository_id, source_task_id, "activity", safe_archive)
        run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, fingerprint))
        result_json = row.get("result") if isinstance(row.get("result"), dict) else {}
        result_json = dict(result_json)
        result_json.update({"repository_id": repository_id, "run_id": run_id, "analyzed_at": iso_z(analyzed_at), "source_task_ids": [source_task_id], "source_archive_paths": [archive_path], "origin": "featured_bundle_import", "sources": sources})
        module_coverage = row.get("module_coverage") if isinstance(row.get("module_coverage"), dict) else sources
        session.add(RepositoryInsightRun(
            run_id=run_id,
            input_fingerprint=fingerprint,
            repository_id=repository_id,
            metric_version=str(row.get("metric_version") or "insights-v1")[:50],
            window_start=start,
            window_end=end,
            analyzed_at=analyzed_at,
            source_task_ids_json=json.dumps([source_task_id]),
            source_archive_paths_json=json.dumps([archive_path]),
            module_coverage_json=json.dumps(module_coverage, ensure_ascii=False),
            status=row.get("status") if row.get("status") in {"ready", "partial", "failed"} else "partial",
            limitations_json=json.dumps(row.get("limitations") if isinstance(row.get("limitations"), list) else [], ensure_ascii=False),
            result_json=json.dumps(result_json, ensure_ascii=False),
        ))


def _repository_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("repository_id"),
        "full_name": row.get("full_name"),
        "html_url": row.get("html_url"),
        "description": row.get("description"),
        "language": row.get("language"),
        "topics": row.get("topics") if isinstance(row.get("topics"), list) else [],
        "license": {"spdx_id": row.get("license_spdx")} if row.get("license_spdx") else None,
        "created_at": row.get("created_at"),
        "pushed_at": row.get("pushed_at"),
        "updated_at": row.get("github_updated_at"),
        "archived": row.get("archived") is True,
        "fork": row.get("is_fork") is True,
        "private": False,
        "size": row.get("size_kb"),
    }


def _positive_int(value: Any) -> int | None:
    return value if type(value) is int and value > 0 else None


def _nonnegative_int(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _contains_email(value: Any) -> bool:
    if isinstance(value, dict):
        return any(str(key).casefold() in {"email", "email_address"} or _contains_email(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_email(item) for item in value)
    return isinstance(value, str) and EMAIL_PATTERN.search(value) is not None


def _contains_sensitive_data(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).casefold() in {"email", "email_address"} or _contains_sensitive_data(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_data(item) for item in value)
    if isinstance(value, str):
        return bool(EMAIL_PATTERN.search(value) or CREDENTIAL_PATTERN.search(value) or MACHINE_PATH_PATTERN.search(value))
    return False


def _json_object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}

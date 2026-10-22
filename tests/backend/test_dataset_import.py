import gzip
import hashlib
import json
import stat
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from backend.app.core.exceptions import AppError
from backend.app.persistence.models import CollectionTask, DatasetImportJob
from backend.app.services import dataset_import
from backend.app.services.dataset_import import BundleError, import_featured_bundle, verify_dataset_bundle
from backend.app.worker.dataset_import import execute_dataset_import_job, fail_dataset_import_job
from backend.app.worker.queue import claim_next_dataset_import_job


HEADERS = {"X-Internal-Api-Key": "test-internal-key"}


def _write_bundle(root: Path) -> Path:
    (root / "events").mkdir(parents=True)
    (root / "details").mkdir()
    files = {
        "repositories.jsonl.gz": [{
            "repository_id": 87654321,
            "full_name": "sample/featured",
            "html_url": "https://github.com/sample/featured",
            "description": "A real public example repository",
            "language": "Python",
            "topics": ["sample"],
            "license_spdx": "MIT",
            "created_at": "2020-01-01T00:00:00Z",
            "pushed_at": "2026-10-20T00:00:00Z",
            "github_updated_at": "2026-10-20T00:00:00Z",
            "archived": False,
            "is_fork": False,
            "size_kb": 12,
            "first_seen_at": "2026-10-20T00:00:00Z",
            "last_seen_at": "2026-10-20T00:00:00Z",
        }],
        "snapshots.jsonl.gz": [{
            "repository_id": 87654321,
            "collected_at": "2026-10-20T00:00:00Z",
            "stars": 12,
            "forks": 3,
            "open_issues_and_pr_count": 4,
            "pushed_at": "2026-10-19T00:00:00Z",
            "github_updated_at": "2026-10-20T00:00:00Z",
            "source_http_status": 200,
        }],
        "memberships.jsonl.gz": [{"repository_id": 87654321, "selection_tier": "featured", "inclusion_reason": "Reviewed demo candidate", "added_at": "2026-10-20T00:00:00Z"}],
        "analysis.jsonl.gz": [],
        "insights.jsonl.gz": [],
        "coverage.jsonl.gz": [],
    }
    for module in dataset_import.MODULES:
        files[f"events/{module}.jsonl.gz"] = []
        files[f"details/{module}.jsonl.gz"] = []
    for relative, rows in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped:
                zipped.write("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows).encode())
    (root / "README.md").write_text("Test bundle\n", encoding="utf-8")
    (root / "DATA_NOTICE.md").write_text("Test-only synthetic bundle, not for distribution.\n", encoding="utf-8")
    for relative in dataset_import.SCHEMA_FILES:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"type": "object", "required": [], "properties": {}}), encoding="utf-8")
    (root / "dataset.json").write_text(json.dumps({
        "schema_version": 1,
        "dataset_id": "featured-default",
        "version": "featured-v1.0.0-test",
        "total_repositories": 1,
        "data_as_of": "2026-10-20T00:00:00Z",
    }), encoding="utf-8")
    _refresh_checksums(root)
    return root


def _refresh_checksums(root: Path) -> None:
    entries = []
    for target in sorted(path for path in root.rglob("*") if path.is_file() and path.relative_to(root).as_posix() != "SHA256SUMS"):
        entries.append(f"{hashlib.sha256(target.read_bytes()).hexdigest()}  {target.relative_to(root).as_posix()}")
    (root / "SHA256SUMS").write_text("\n".join(entries) + "\n", encoding="ascii")


def _write_jsonl_gzip(path: Path, rows: list[dict]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped:
            zipped.write("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows).encode())


def _write_bundle_zip(root: Path) -> Path:
    archive_path = root.with_suffix(".zip")
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    return archive_path


def test_featured_bundle_verification_and_import_are_idempotent(backend_client, tmp_path, monkeypatch):
    _client, factory, _github = backend_client
    root = _write_bundle(tmp_path / "featured-v1")

    verified = verify_dataset_bundle(root)
    assert verified["available"] is True
    assert verified["total_repositories"] == 1

    monkeypatch.setattr("backend.app.pipeline.raw_archive.get_settings", lambda: type("Settings", (), {"raw_data_path": tmp_path / "raw"})())
    with factory() as session:
        first = import_featured_bundle(session, root)
    with factory() as session:
        second = import_featured_bundle(session, root)
        assert session.get(dataset_import.Repository, 87654321) is not None
        assert session.get(dataset_import.DatasetRepository, ("featured-default", 87654321)) is not None
        assert session.get(dataset_import.DatasetRepository, ("library-default", 87654321)) is not None

    assert first["imported_count"] == 1
    assert first["already_present_count"] == 0
    assert second["imported_count"] == 0
    assert second["already_present_count"] == 1
    assert first["snapshot_count"] == 1


def test_featured_import_does_not_replace_newer_local_repository_or_snapshot(backend_client, tmp_path, monkeypatch):
    _client, factory, _github = backend_client
    root = _write_bundle(tmp_path / "featured-v1")
    monkeypatch.setattr("backend.app.pipeline.raw_archive.get_settings", lambda: type("Settings", (), {"raw_data_path": tmp_path / "raw"})())
    with factory() as session:
        session.add(dataset_import.Repository(
            repository_id=87654321,
            full_name="sample/featured",
            html_url="https://github.com/sample/featured",
            description="newer local description",
            first_seen_at=datetime(2026, 10, 19),
            last_seen_at=datetime(2026, 10, 21),
        ))
        session.add(dataset_import.RepositorySnapshot(
            repository_id=87654321,
            collected_at=datetime(2026, 10, 21),
            stars=999,
            forks=99,
            open_issues_and_pr_count=9,
            source_http_status=200,
            valid=True,
        ))
        session.commit()

    with factory() as session:
        result = import_featured_bundle(session, root)
        repository = session.get(dataset_import.Repository, 87654321)
        snapshot = session.scalar(
            dataset_import.select(dataset_import.RepositorySnapshot)
            .where(dataset_import.RepositorySnapshot.repository_id == 87654321)
        )
        assert repository.description == "newer local description"
        assert snapshot.stars == 999

    assert result["snapshot_count"] == 0
    assert result["skipped_count"] == 1


def test_modified_checksum_rejects_bundle_before_database_mutation(backend_client, tmp_path):
    _client, factory, _github = backend_client
    root = _write_bundle(tmp_path / "featured-v1")
    with (root / "README.md").open("a", encoding="utf-8") as stream:
        stream.write("tampered\n")

    with factory() as session, pytest.raises(AppError, match="SHA-256 校验失败"):
        import_featured_bundle(session, root)
    with factory() as session:
        assert session.get(dataset_import.Repository, 87654321) is None


def test_featured_api_reports_missing_real_bundle_without_falling_back_to_github(backend_client, tmp_path, monkeypatch):
    client, _factory, _github = backend_client
    monkeypatch.setattr(dataset_import, "BUNDLE_ROOT", tmp_path / "missing-featured-bundle")
    result = client.get("/api/v1/datasets/featured/status", headers=HEADERS)
    assert result.status_code == 200
    assert result.json()["data"]["available"] is False
    assert "尚未生成" in result.json()["data"]["reason"]


def test_featured_status_does_not_parse_or_hash_all_bundle_records(backend_client, tmp_path, monkeypatch):
    client, _factory, _github = backend_client
    root = _write_bundle(tmp_path / "featured-v1")
    monkeypatch.setattr(dataset_import, "BUNDLE_ROOT", root)

    def unexpected_full_validation(*_args, **_kwargs):
        raise AssertionError("status must not decompress or fully validate the bundle")

    monkeypatch.setattr(dataset_import, "_load_bundle", unexpected_full_validation)
    response = client.get("/api/v1/datasets/featured/status", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["data"]["available"] is True
    assert response.json()["data"]["verification_status"] == "pending"


def test_featured_api_queues_local_bundle_and_worker_imports_without_github_requests(backend_client, tmp_path, monkeypatch):
    client, factory, github = backend_client
    root = _write_bundle(tmp_path / "featured-v1")
    monkeypatch.setattr(dataset_import, "BUNDLE_ROOT", root)

    def unexpected_github_request(*_args, **_kwargs):
        raise AssertionError("featured bundle import must not call GitHub")

    monkeypatch.setattr(github, "get_repository_by_id", unexpected_github_request)
    monkeypatch.setattr("backend.app.pipeline.raw_archive.get_settings", lambda: type("Settings", (), {"raw_data_path": tmp_path / "raw"})())
    monkeypatch.setattr("backend.app.worker.dataset_import.get_settings", lambda: type("Settings", (), {"raw_data_path": tmp_path / "raw"})())
    response = client.post("/api/v1/datasets/featured/import", headers=HEADERS)

    assert response.status_code == 202
    queued = response.json()["data"]
    assert queued["task_id"]
    assert queued["status"] == "queued"
    duplicate = client.post("/api/v1/datasets/featured/import", headers=HEADERS).json()["data"]
    assert duplicate["task_id"] == queued["task_id"]

    task = client.get(f"/api/v1/tasks/{queued['task_id']}", headers=HEADERS).json()["data"]
    assert task["task_type"] == "dataset_import"
    assert task["repository_id"] is None
    assert task["status"] == "queued"
    assert task["display_name"] == "精选仓库数据集"
    task_list = client.get("/api/v1/tasks?task_type=dataset_import&per_page=100", headers=HEADERS).json()
    assert task_list["meta"]["pagination"]["total"] == 1
    assert task_list["data"]["items"][0]["task_id"] == queued["task_id"]

    with factory() as session:
        claimed = claim_next_dataset_import_job(session, "dataset-worker", 60)
    assert claimed and claimed.task_id == queued["task_id"]
    execute_dataset_import_job(factory, claimed.task_id, "dataset-worker", 60)

    task = client.get(f"/api/v1/tasks/{queued['task_id']}", headers=HEADERS).json()["data"]
    assert task["status"] == "succeeded"
    assert task["progress_percent"] == 100
    assert task["result"]["imported_count"] == 1
    assert task["result"]["snapshot_count"] == 1
    status = client.get("/api/v1/datasets/featured/status", headers=HEADERS)
    assert status.status_code == 200
    assert status.json()["data"]["imported_repositories"] == 1
    assert status.json()["data"]["already_current"] is True
    already_current = client.post("/api/v1/datasets/featured/import", headers=HEADERS)
    assert already_current.status_code == 200
    assert already_current.json()["data"]["already_current"] is True


def test_dataset_import_failure_rolls_back_business_rows_and_can_be_retried(backend_client, tmp_path, monkeypatch):
    client, factory, _github = backend_client
    root = _write_bundle(tmp_path / "featured-v1")
    monkeypatch.setattr(dataset_import, "BUNDLE_ROOT", root)
    monkeypatch.setattr("backend.app.pipeline.raw_archive.get_settings", lambda: type("Settings", (), {"raw_data_path": tmp_path / "raw"})())
    monkeypatch.setattr("backend.app.worker.dataset_import.get_settings", lambda: type("Settings", (), {"raw_data_path": tmp_path / "raw"})())
    with factory() as session:
        session.add(dataset_import.Repository(
            repository_id=87654321,
            full_name="conflict/repository",
            html_url="https://github.com/conflict/repository",
            first_seen_at=datetime(2026, 10, 20),
            last_seen_at=datetime(2026, 10, 20),
        ))
        session.commit()

    queued = client.post("/api/v1/datasets/featured/import", headers=HEADERS).json()["data"]
    with factory() as session:
        claimed = claim_next_dataset_import_job(session, "dataset-worker", 60)
    with pytest.raises(AppError, match="仓库身份与本地记录冲突"):
        execute_dataset_import_job(factory, claimed.task_id, "dataset-worker", 60)
    fail_dataset_import_job(factory, claimed.task_id, "dataset-worker", AppError(409, "DATASET_REPOSITORY_CONFLICT", "仓库身份与本地记录冲突"))

    with factory() as session:
        failed = session.get(DatasetImportJob, queued["task_id"])
        assert failed.status == "failed"
        assert failed.error_code == "DATASET_REPOSITORY_CONFLICT"
        featured = session.get(dataset_import.Dataset, dataset_import.FEATURED_ID)
        assert featured is not None and featured.source_metadata_json is None
        assert session.scalar(dataset_import.select(dataset_import.func.count()).select_from(dataset_import.DatasetRepository).where(dataset_import.DatasetRepository.dataset_id == dataset_import.FEATURED_ID)) == 0
        assert session.scalar(dataset_import.select(dataset_import.func.count()).select_from(dataset_import.DatasetImportStagingRecord).where(dataset_import.DatasetImportStagingRecord.task_id == queued["task_id"])) > 0

    retry = client.post(f"/api/v1/tasks/{queued['task_id']}/retry", headers={**HEADERS, "Idempotency-Key": "retry-featured-once"})
    assert retry.status_code == 202
    retry_task_id = retry.json()["data"]["task_id"]
    with factory() as session:
        assert session.get(DatasetImportJob, queued["task_id"]).status == "failed"
        retried = session.get(DatasetImportJob, retry_task_id)
        assert retried.status == "queued"
        assert retried.retry_of == queued["task_id"]
        assert retried.processed_records > 0
        assert session.scalar(dataset_import.select(dataset_import.func.count()).select_from(dataset_import.DatasetImportStagingRecord).where(dataset_import.DatasetImportStagingRecord.task_id == retry_task_id)) > 0


def test_dataset_import_cleans_published_archives_after_merge_failure(backend_client, tmp_path, monkeypatch):
    client, factory, _github = backend_client
    root = _write_bundle(tmp_path / "featured-v1")
    _write_jsonl_gzip(root / "insights.jsonl.gz", [{
        "repository_id": 87654321,
        "metric_version": "insights-v1",
        "analyzed_at": "2026-10-20T00:00:00Z",
        "window_start": "2026-07-22T00:00:00Z",
        "window_end": "2026-10-20T00:00:00Z",
        "sources": {},
        "result": {},
        "status": "ready",
        "limitations": [],
    }])
    _refresh_checksums(root)
    monkeypatch.setattr(dataset_import, "BUNDLE_ROOT", root)
    raw_root = tmp_path / "raw"
    settings = lambda: type("Settings", (), {"raw_data_path": raw_root})()
    monkeypatch.setattr("backend.app.pipeline.raw_archive.get_settings", settings)
    monkeypatch.setattr("backend.app.worker.dataset_import.get_settings", settings)

    task_id = client.post("/api/v1/datasets/featured/import", headers=HEADERS).json()["data"]["task_id"]
    with factory() as session:
        claimed = claim_next_dataset_import_job(session, "dataset-worker", 60)
    monkeypatch.setattr(dataset_import, "_import_records", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("simulated merge failure")))
    with pytest.raises(RuntimeError, match="simulated merge failure"):
        execute_dataset_import_job(factory, task_id, "dataset-worker", 60)
    fail_dataset_import_job(factory, task_id, "dataset-worker", RuntimeError("simulated merge failure"))

    with factory() as session:
        job = session.get(DatasetImportJob, task_id)
        state = json.loads(job.staging_state_json)
        archive_paths = list(state["archive_paths"].values())
        assert job.status == "failed"
    assert archive_paths
    assert all(not (raw_root / path).exists() for path in archive_paths)
    assert not (raw_root / ".dataset-import-staging" / task_id).exists()


def test_tasks_merge_pagination_and_filters_across_task_types(backend_client):
    client, factory, _github = backend_client
    added = client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS).json()["data"]
    with factory() as session:
        session.add(CollectionTask(
            task_id="collection-older",
            repository_id=added["repository_id"],
            depth="basic",
            status="queued",
            created_at=datetime(2026, 10, 20, 10),
        ))
        session.add(DatasetImportJob(
            task_id="dataset-newer",
            dataset_id=dataset_import.FEATURED_ID,
            bundle_version="featured-test",
            bundle_hash="b" * 64,
            status="queued",
            phase="validating",
            progress_kind="indeterminate",
            created_at=datetime(2026, 10, 20, 11),
            updated_at=datetime(2026, 10, 20, 11),
        ))
        session.commit()

    first_page = client.get("/api/v1/tasks?page=1&per_page=1", headers=HEADERS).json()
    assert first_page["meta"]["pagination"]["total"] == 2
    assert first_page["meta"]["pagination"]["has_next"] is True
    assert first_page["data"]["items"][0]["task_type"] == "dataset_import"
    second_page = client.get("/api/v1/tasks?page=2&per_page=1", headers=HEADERS).json()
    assert second_page["data"]["items"][0]["task_type"] == "repository_collection"
    by_repository = client.get(f"/api/v1/tasks?repository_id={added['repository_id']}", headers=HEADERS).json()
    assert by_repository["meta"]["pagination"]["total"] == 1
    by_type = client.get("/api/v1/tasks?task_type=dataset_import", headers=HEADERS).json()
    assert by_type["meta"]["pagination"]["total"] == 1


def test_featured_api_exports_verified_local_zip_without_github_requests(backend_client, tmp_path, monkeypatch):
    client, _factory, github = backend_client
    root = _write_bundle(tmp_path / "featured-v1")
    archive_path = _write_bundle_zip(root)
    monkeypatch.setattr(dataset_import, "BUNDLE_ROOT", root)

    def unexpected_github_request(*_args, **_kwargs):
        raise AssertionError("featured bundle export must not call GitHub")

    monkeypatch.setattr(github, "get_repository_by_id", unexpected_github_request)
    response = client.get("/api/v1/datasets/featured/export", headers=HEADERS)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "repovantage-dataset-featured-v1.0.0-test.zip" in response.headers["content-disposition"]
    downloaded = tmp_path / "downloaded.zip"
    downloaded.write_bytes(response.content)
    assert verify_dataset_bundle(downloaded)["bundle_hash"] == verify_dataset_bundle(root)["bundle_hash"]
    assert archive_path.exists()


def test_featured_api_rejects_stale_zip_export(backend_client, tmp_path, monkeypatch):
    client, _factory, _github = backend_client
    root = _write_bundle(tmp_path / "featured-v1")
    _write_bundle_zip(root)
    (root / "README.md").write_text("Updated directory without a regenerated ZIP\n", encoding="utf-8")
    _refresh_checksums(root)
    monkeypatch.setattr(dataset_import, "BUNDLE_ROOT", root)

    response = client.get("/api/v1/datasets/featured/export", headers=HEADERS)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DATASET_BUNDLE_UNAVAILABLE"


def test_browser_gateway_forwards_featured_bundle_download(backend_client, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    client, _factory, _github = backend_client
    root = _write_bundle(tmp_path / "featured-v1")
    _write_bundle_zip(root)
    monkeypatch.setattr(dataset_import, "BUNDLE_ROOT", root)
    headers = {"X-GDA-Request": "browser", "Origin": "http://127.0.0.1"}

    with TestClient(client.app, base_url="http://127.0.0.1", client=("127.0.0.1", 55002)) as browser_client:
        bootstrap = browser_client.get("/api/browser/session", headers=headers)
        response = browser_client.get("/api/browser/v1/datasets/featured/export", headers=headers)

    assert bootstrap.status_code == 200
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    downloaded = tmp_path / "browser-download.zip"
    downloaded.write_bytes(response.content)
    assert verify_dataset_bundle(downloaded)["available"] is True


def test_bundle_rejects_extra_files_even_when_checksum_matches(tmp_path):
    root = _write_bundle(tmp_path / "featured-v1")
    (root / ".env").write_text("UNSAFE=value\n", encoding="utf-8")
    _refresh_checksums(root)

    with pytest.raises(BundleError, match="未声明文件"):
        verify_dataset_bundle(root)


def test_bundle_rejects_sensitive_text_in_release_details(tmp_path):
    root = _write_bundle(tmp_path / "featured-v1")
    _write_jsonl_gzip(root / "details/releases.jsonl.gz", [{
        "repository_id": 87654321,
        "item": {"body": "Contact maintainer@example.com"},
    }])
    _refresh_checksums(root)

    with pytest.raises(BundleError, match="邮箱、凭证或机器绝对路径"):
        verify_dataset_bundle(root)


def test_bundle_rejects_sensitive_metadata_even_with_valid_checksum(tmp_path):
    root = _write_bundle(tmp_path / "featured-v1")
    metadata_path = root / "dataset.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["maintainer"] = "maintainer@example.com"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    _refresh_checksums(root)

    with pytest.raises(BundleError, match="邮箱、凭证或机器绝对路径"):
        verify_dataset_bundle(root)


@pytest.mark.parametrize("entry_name", ["../escape.txt", "nested/../escape.txt", "nested//file.txt", "nested/./file.txt"])
def test_bundle_zip_rejects_unsafe_paths(tmp_path, entry_name):
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(entry_name, "not safe")

    with pytest.raises(BundleError, match="不安全的文件路径"):
        verify_dataset_bundle(archive_path)


def test_bundle_zip_rejects_symlinks(tmp_path):
    archive_path = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, "target")

    with pytest.raises(BundleError, match="普通文件"):
        verify_dataset_bundle(archive_path)


def test_bundle_zip_rejects_duplicate_paths(tmp_path):
    archive_path = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("README.md", "first")
        archive.writestr("README.md", "second")

    with pytest.raises(BundleError, match="重复的文件路径"):
        verify_dataset_bundle(archive_path)

from datetime import timedelta

from sqlalchemy import func, select

from backend.app.core.clock import utc_now
from backend.app.persistence.models import (
    ActivityWindow,
    AnalysisResult,
    CollectionCheckpoint,
    CollectionLog,
    CollectionTask,
    Dataset,
    DatasetRepository,
    DatasetImportJob,
    Repository,
    RepositoryActivityEvent,
    RepositoryInsightRun,
    RepositorySnapshot,
    TaskModuleProgress,
)
from backend.app.pipeline import collection_archive
from backend.app.services.repositories import LIBRARY_ID
from backend.app.services import repository_data


HEADERS = {"X-Internal-Api-Key": "test-internal-key"}


def _add_repository(client, full_name: str) -> None:
    response = client.post(
        "/api/v1/library/repositories",
        json={"full_name": full_name, "auto_analyze": False},
        headers=HEADERS,
    )
    assert response.status_code == 201


def _count(session, model, repository_id: int) -> int:
    return int(session.scalar(select(func.count()).select_from(model).where(model.repository_id == repository_id)) or 0)


def test_clear_repository_data_keeps_library_entry_by_default(backend_client, tmp_path, monkeypatch):
    client, factory, _github = backend_client
    _add_repository(client, "example/project")
    with factory() as session:
        session.add(RepositorySnapshot(repository_id=123, collected_at=utc_now(), stars=20, forks=3, source_http_status=200))
        session.commit()

    raw_root = tmp_path / "raw"
    page_root = tmp_path / "collected" / "github"
    raw_root.mkdir()
    page_root.mkdir(parents=True)
    monkeypatch.setattr(repository_data, "get_settings", lambda: type("Settings", (), {"raw_data_path": raw_root})())
    monkeypatch.setattr(collection_archive, "COLLECTED_ROOT", page_root)

    response = client.post("/api/v1/repositories/data/clear", json={"repository_ids": [123]}, headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["data"]["repositories"][0]["removed_from_library"] is False
    assert response.json()["data"]["repositories"][0]["removed_from_featured"] is False
    with factory() as session:
        assert session.get(DatasetRepository, (LIBRARY_ID, 123)) is not None
        assert _count(session, RepositorySnapshot, 123) == 0


def test_clear_selected_repository_data_removes_library_entries_and_keeps_other_memberships(backend_client, tmp_path, monkeypatch):
    client, factory, _github = backend_client
    _add_repository(client, "example/project")
    with factory() as session:
        session.add_all([
            Repository(repository_id=456, full_name="example/other", html_url="https://github.com/example/other"),
            Repository(repository_id=789, full_name="example/untouched", html_url="https://github.com/example/untouched"),
        ])
        session.flush()
        session.add_all([
            DatasetRepository(dataset_id=LIBRARY_ID, repository_id=456),
            DatasetRepository(dataset_id=LIBRARY_ID, repository_id=789),
        ])
        session.add(Dataset(dataset_id="research-test", name="Research test", type="research"))
        session.flush()
        session.add(DatasetRepository(dataset_id="research-test", repository_id=123))
        now = utc_now()
        session.add_all([
            RepositorySnapshot(repository_id=123, collected_at=now, stars=20, forks=3, source_http_status=200),
            RepositorySnapshot(repository_id=456, collected_at=now, stars=30, forks=4, source_http_status=200),
            RepositorySnapshot(repository_id=789, collected_at=now, stars=40, forks=5, source_http_status=200),
            RepositoryActivityEvent(
                repository_id=123,
                event_type="issue",
                source_item_id="issue-1",
                first_seen_at=now,
                last_seen_at=now,
                source_task_id="fixture",
            ),
            ActivityWindow(
                repository_id=123,
                depth="deep",
                window_start=now - timedelta(days=7),
                window_end=now,
                coverage="complete",
                collected_at=now,
            ),
            AnalysisResult(
                repository_id=123,
                analysis_kind="basic",
                metric_version="metrics-v1",
                source_collected_at=now,
                calculated_at=now,
                coverage="complete",
                metrics_json="{}",
            ),
            RepositoryInsightRun(
                run_id="11111111-1111-4111-8111-111111111111",
                input_fingerprint="a" * 64,
                repository_id=123,
                metric_version="insights-v1",
                window_start=now - timedelta(days=7),
                window_end=now,
                analyzed_at=now,
                source_task_ids_json="[]",
                source_archive_paths_json="[]",
                module_coverage_json="{}",
                status="complete",
                limitations_json="[]",
                result_json="{}",
            ),
            CollectionCheckpoint(
                repository_id=123,
                module="issues",
                scope_fingerprint="b" * 64,
                window_start=now - timedelta(days=7),
                window_end=now,
            ),
            CollectionLog(repository_id=123, request_id="request-1", event_type="collection_completed"),
            CollectionTask(
                task_id="22222222-2222-4222-8222-222222222222",
                repository_id=123,
                depth="basic",
                status="succeeded",
                created_at=now,
                finished_at=now,
            ),
            TaskModuleProgress(
                task_id="22222222-2222-4222-8222-222222222222",
                module="profile",
                status="succeeded",
                coverage="complete",
                attempt=1,
            ),
        ])
        session.commit()

    raw_root = tmp_path / "raw"
    page_root = tmp_path / "collected" / "github"
    raw_directory = raw_root / "123"
    page_directory = page_root / "123"
    other_raw_directory = raw_root / "456"
    other_page_directory = page_root / "456"
    for directory in (raw_directory, page_directory, other_raw_directory, other_page_directory):
        directory.mkdir(parents=True)
    (raw_directory / "snapshot.json.gz").write_bytes(b"archive")
    (page_directory / "page.json.gz").write_bytes(b"page")
    monkeypatch.setattr(repository_data, "get_settings", lambda: type("Settings", (), {"raw_data_path": raw_root})())
    monkeypatch.setattr(collection_archive, "COLLECTED_ROOT", page_root)

    response = client.post(
        "/api/v1/repositories/data/clear",
        json={"repository_ids": [123, 456], "remove_from_library": True},
        headers=HEADERS,
    )

    assert response.status_code == 200
    cleared = response.json()["data"]["repositories"]
    assert cleared[0] == {
        "repository_id": 123,
        "removed_from_library": True,
        "removed_from_featured": False,
        "snapshots": 1,
        "activity_events": 1,
        "activity_windows": 1,
        "analysis_results": 1,
        "insight_runs": 1,
        "checkpoints": 1,
        "collection_logs": 1,
        "raw_archive_directory_removed": True,
        "collection_archive_directory_removed": True,
    }
    assert cleared[1]["repository_id"] == 456
    assert cleared[1]["removed_from_library"] is True
    assert cleared[1]["removed_from_featured"] is False
    assert cleared[1]["snapshots"] == 1
    assert not raw_directory.exists() and not page_directory.exists()
    assert not other_raw_directory.exists() and not other_page_directory.exists()
    with factory() as session:
        assert session.get(Repository, 123) is not None
        assert session.get(Repository, 456) is not None
        assert session.get(Repository, 789) is not None
        assert session.get(DatasetRepository, (LIBRARY_ID, 123)) is None
        assert session.get(DatasetRepository, (LIBRARY_ID, 456)) is None
        assert session.get(DatasetRepository, ("research-test", 123)) is not None
        assert _count(session, RepositorySnapshot, 123) == 0
        assert _count(session, RepositoryActivityEvent, 123) == 0
        assert _count(session, ActivityWindow, 123) == 0
        assert _count(session, AnalysisResult, 123) == 0
        assert _count(session, RepositoryInsightRun, 123) == 0
        assert _count(session, CollectionCheckpoint, 123) == 0
        assert _count(session, CollectionLog, 123) == 0
        assert _count(session, CollectionTask, 123) == 1
        assert session.scalar(select(func.count()).select_from(TaskModuleProgress).where(TaskModuleProgress.task_id == "22222222-2222-4222-8222-222222222222")) == 1
        assert _count(session, RepositorySnapshot, 456) == 0
        assert _count(session, RepositorySnapshot, 789) == 1
    detail = client.get("/api/v1/repositories/123", headers=HEADERS).json()["data"]
    assert detail["repository"]["data_status"] == "missing"
    assert detail["repository"]["datasets"] == ["research-test"]
    library = client.get("/api/v1/library/repositories?per_page=100", headers=HEADERS).json()["data"]["items"]
    assert [repo["full_name"] for repo in library] == ["example/untouched"]


def test_clear_repository_data_rejects_active_collection_without_deleting(backend_client):
    client, factory, _github = backend_client
    _add_repository(client, "example/project")
    now = utc_now()
    with factory() as session:
        session.add(RepositorySnapshot(repository_id=123, collected_at=now, stars=20, forks=3, source_http_status=200))
        session.add(CollectionTask(task_id="33333333-3333-4333-8333-333333333333", repository_id=123, depth="basic", status="running", created_at=now))
        session.commit()

    response = client.post("/api/v1/repositories/data/clear", json={"repository_ids": [123]}, headers=HEADERS)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICTING_OPERATION"
    with factory() as session:
        assert _count(session, RepositorySnapshot, 123) == 1


def test_clear_repository_data_rejects_active_featured_import(backend_client):
    client, factory, _github = backend_client
    _add_repository(client, "example/project")
    now = utc_now()
    with factory() as session:
        session.add(RepositorySnapshot(repository_id=123, collected_at=now, stars=20, forks=3, source_http_status=200))
        session.add(DatasetImportJob(
            task_id="44444444-4444-4444-8444-444444444444",
            dataset_id="featured-test",
            bundle_version="v1",
            bundle_hash="c" * 64,
            status="running",
        ))
        session.commit()

    response = client.post("/api/v1/repositories/data/clear", json={"repository_ids": [123]}, headers=HEADERS)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICTING_OPERATION"
    with factory() as session:
        assert _count(session, RepositorySnapshot, 123) == 1


def test_clear_repository_data_validates_all_ids_before_deleting_any(backend_client):
    client, factory, _github = backend_client
    _add_repository(client, "example/project")
    now = utc_now()
    with factory() as session:
        session.add(RepositorySnapshot(repository_id=123, collected_at=now, stars=20, forks=3, source_http_status=200))
        session.commit()

    response = client.post("/api/v1/repositories/data/clear", json={"repository_ids": [123, 999]}, headers=HEADERS)

    assert response.status_code == 404
    with factory() as session:
        assert _count(session, RepositorySnapshot, 123) == 1

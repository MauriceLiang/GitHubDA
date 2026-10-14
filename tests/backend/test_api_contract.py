import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from backend.app.core.clock import utc_now
from backend.app.persistence.db import Base
from backend.app.persistence.models import AnalysisResult, CollectionTask, Dataset, DatasetRepository, RepositorySnapshot
from backend.app.services.repositories import LIBRARY_ID
from backend.app.worker.executor import execute_task
from backend.app.worker.queue import claim_next_task


HEADERS = {"X-Internal-Api-Key": "test-internal-key"}


def test_health_and_key_protection(backend_client):
    client, _factory, _github = backend_client
    assert client.get("/healthz").json() == {"status": "ok"}
    denied = client.get("/api/v1/datasets")
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "UNAUTHORIZED_CLIENT"
    allowed = client.get("/api/v1/datasets", headers=HEADERS)
    assert allowed.status_code == 200
    assert "meta" in allowed.json()
    assert set(allowed.json()["meta"]) == {"request_id", "generated_at"}
    assert allowed.headers["x-request-id"] == allowed.json()["meta"]["request_id"]


def test_missing_internal_api_key_configuration_returns_503(backend_client, monkeypatch):
    client, _factory, _github = backend_client
    monkeypatch.setattr("backend.app.api.dependencies.get_settings", lambda: type("Settings", (), {"internal_api_key": None})())
    assert client.get("/healthz").status_code == 200
    response = client.get("/api/v1/datasets", headers=HEADERS)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "BACKEND_UNAVAILABLE"


def test_api_startup_seeds_all_default_dataset_types(tmp_path, monkeypatch):
    from backend.app import main

    engine = create_engine(f"sqlite:///{tmp_path / 'startup.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)

    with TestClient(main.app):
        pass
    with factory() as session:
        types = {dataset.type for dataset in session.query(Dataset).all()}
    assert types == {"research", "library", "featured"}
    engine.dispose()


def test_api_startup_reports_migration_when_schema_is_missing(tmp_path, monkeypatch):
    from backend.app import main

    engine = create_engine(f"sqlite:///{tmp_path / 'unmigrated.db'}")
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(main, "SessionLocal", factory)

    with pytest.raises(OperationalError):
        with TestClient(main.app):
            pass
    engine.dispose()


def test_add_is_idempotent_and_reuses_queued_task(backend_client):
    client, factory, _github = backend_client
    body = {"full_name": "example/project", "auto_analyze": True, "depth": "basic"}
    first = client.post("/api/v1/library/repositories", json=body, headers=HEADERS)
    second = client.post("/api/v1/library/repositories", json=body, headers=HEADERS)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["data"]["task_id"] == second.json()["data"]["task_id"]
    queued = client.get("/api/v1/tasks?status=queued", headers=HEADERS)
    assert queued.status_code == 200
    assert queued.json()["data"]["items"][0]["attempt"] == 0
    with factory() as session:
        memberships = session.scalar(select(func.count()).select_from(DatasetRepository).where(DatasetRepository.dataset_id == LIBRARY_ID))
        tasks = session.scalar(select(func.count()).select_from(CollectionTask))
    assert memberships == 1
    assert tasks == 1


def test_search_add_worker_analysis_flow_uses_real_persisted_snapshot(backend_client, monkeypatch):
    client, factory, github = backend_client
    monkeypatch.setattr("backend.app.worker.executor.archive_json", lambda *_args, **_kwargs: "123/2026-10-13/task/repository.json.gz")
    search = client.get("/api/v1/github/search?q=project", headers=HEADERS)
    assert search.status_code == 200
    assert search.json()["data"]["items"][0]["repository_id"] == 123
    added = client.post("/api/v1/library/repositories", json={"full_name": "example/project"}, headers=HEADERS)
    assert added.status_code == 201
    task_id = added.json()["data"]["task_id"]
    with factory() as session:
        task = claim_next_task(session, "test-worker", 60)
    assert task and task.task_id == task_id
    running = client.get(f"/api/v1/tasks/{task_id}", headers=HEADERS)
    assert running.json()["data"]["attempt"] == 1
    execute_task(factory, task_id, github)
    analysis = client.get("/api/v1/repositories/123/analysis", headers=HEADERS)
    detail = client.get("/api/v1/repositories/123", headers=HEADERS)
    assert analysis.status_code == 200
    assert analysis.json()["data"]["analysis_status"] == "completed"
    assert analysis.json()["data"]["metrics"]["stars"] == 20
    assert detail.json()["data"]["repository"]["data_status"] == "fresh"
    assert detail.json()["data"]["source_metadata"]["sample_size"] == 1


def test_search_validation_uses_contract_error_envelope(backend_client):
    client, _factory, _github = backend_client
    response = client.get("/api/v1/github/search?q=repo%3Aowner/name", headers=HEADERS)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"]["fields"][0]["field"] == "q"


def test_csv_export_escapes_untrusted_text(backend_client):
    client, _factory, github = backend_client
    github.repository["description"] = "=HYPERLINK(\"https://example.invalid\")"
    response = client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS)
    assert response.status_code == 201
    exported = client.get("/api/v1/exports/repositories.csv?scope=library", headers=HEADERS)
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv; charset=utf-8")
    assert b"'=HYPERLINK" in exported.content


def test_delete_only_removes_library_membership(backend_client):
    client, factory, _github = backend_client
    added = client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS)
    assert added.status_code == 201
    deleted = client.delete("/api/v1/library/repositories/123", headers=HEADERS)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get("/api/v1/repositories/123", headers=HEADERS).status_code == 200
    with factory() as session:
        assert session.get(DatasetRepository, (LIBRARY_ID, 123)) is None


def test_retry_creates_one_new_historical_task_per_idempotency_key(backend_client):
    client, factory, _github = backend_client
    added = client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS)
    assert added.status_code == 201
    original_id = "11111111-1111-4111-8111-222222222222"
    with factory() as session:
        session.add(CollectionTask(task_id=original_id, repository_id=123, depth="basic", status="failed", created_at=utc_now(), finished_at=utc_now(), error_code="GITHUB_TIMEOUT", error_message="timeout"))
        session.commit()
    headers = {**HEADERS, "Idempotency-Key": "retry-once"}
    first = client.post(f"/api/v1/tasks/{original_id}/retry", json={}, headers=headers)
    second = client.post(f"/api/v1/tasks/{original_id}/retry", json={}, headers=headers)
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["data"]["task_id"] == second.json()["data"]["task_id"]
    assert first.json()["data"]["retry_of"] == original_id
    retried = client.get(f"/api/v1/tasks/{first.json()['data']['task_id']}", headers=HEADERS)
    assert retried.json()["data"]["attempt"] == 0
    with factory() as session:
        count = session.scalar(select(func.count()).select_from(CollectionTask))
    assert count == 2


@pytest.mark.parametrize("cached_status", ["succeeded", "partial"])
def test_refresh_reuses_fresh_snapshot_unless_forced(backend_client, cached_status):
    client, factory, _github = backend_client
    added = client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS)
    assert added.status_code == 201
    task_id = "11111111-1111-4111-8111-333333333333"
    collected_at = utc_now()
    with factory() as session:
        session.add(RepositorySnapshot(repository_id=123, collected_at=collected_at, stars=20, forks=3, open_issues_and_pr_count=4, source_http_status=200, valid=True))
        session.add(AnalysisResult(repository_id=123, analysis_kind="basic", metric_version="metrics-v1", source_collected_at=collected_at, calculated_at=collected_at, coverage="partial" if cached_status == "partial" else "complete", metrics_json='{"stars":20,"forks":3}', limitations_json="[]", valid_sample_size=1))
        session.add(CollectionTask(task_id=task_id, repository_id=123, depth="basic", status=cached_status, created_at=collected_at, started_at=collected_at, finished_at=collected_at))
        session.commit()
    cached = client.post("/api/v1/repositories/123/refresh", json={"depth": "basic", "force": False}, headers=HEADERS)
    forced = client.post("/api/v1/repositories/123/refresh", json={"depth": "basic", "force": True}, headers=HEADERS)
    assert cached.status_code == forced.status_code == 202
    assert cached.json()["data"] == {"task_id": task_id, "reused": True, "status": cached_status}
    assert forced.json()["data"]["task_id"] != task_id
    assert forced.json()["data"]["reused"] is False
    duplicate_forced = client.post("/api/v1/repositories/123/refresh", json={"depth": "basic", "force": True}, headers=HEADERS)
    assert duplicate_forced.json()["data"]["task_id"] == forced.json()["data"]["task_id"]
    assert duplicate_forced.json()["data"]["reused"] is True


def test_idempotency_key_cannot_be_reused_for_a_different_operation(backend_client):
    client, _factory, _github = backend_client
    headers = {**HEADERS, "Idempotency-Key": "one-key-two-operations"}
    added = client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=headers)
    assert added.status_code == 201
    refresh = client.post("/api/v1/repositories/123/refresh", json={"depth": "basic"}, headers=headers)
    assert refresh.status_code == 409
    assert refresh.json()["error"]["code"] == "CONFLICTING_OPERATION"


def test_empty_dataset_and_research_responses_preserve_nullable_contract(backend_client):
    client, _factory, _github = backend_client
    datasets = client.get("/api/v1/datasets", headers=HEADERS)
    assert datasets.status_code == 200
    assert {item["type"] for item in datasets.json()["data"]["items"]} == {"research", "library", "featured"}

    library = client.get("/api/v1/overview?scope=library", headers=HEADERS)
    research = client.get("/api/v1/overview?scope=research&dataset_id=research-2026-v1", headers=HEADERS)
    statistics = client.get("/api/v1/research/statistics?dataset_id=research-2026-v1", headers=HEADERS)
    quality = client.get("/api/v1/research/data-quality?dataset_id=research-2026-v1", headers=HEADERS)
    assert library.status_code == research.status_code == statistics.status_code == quality.status_code == 200
    assert library.json()["data"]["source_metadata"]["collected_at"] is None
    assert research.json()["data"]["source_metadata"]["collected_at"] is None
    assert research.json()["data"]["source_metadata"]["sample_size"] == 0
    assert statistics.json()["data"]["valid_sample_size"] == 0
    assert statistics.json()["data"]["source_metadata"]["collected_at"] is None
    assert quality.json()["data"]["records_total"] == 0
    assert all(item["rate"] is None for item in quality.json()["data"]["missing_fields"])

    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert schemas["SourceMetadata"]["properties"]["collected_at"]["anyOf"][-1] == {"type": "null"}
    assert schemas["MissingFieldResponse"]["properties"]["rate"]["anyOf"][-1] == {"type": "null"}


def test_all_v1_routes_are_present_in_openapi():
    from backend.app.main import app

    paths = app.openapi()["paths"]
    expected = {
        "/healthz", "/api/v1/system/status", "/api/v1/github/search", "/api/v1/github/resolve",
        "/api/v1/library/repositories", "/api/v1/library/repositories/{repository_id}",
        "/api/v1/repositories/{repository_id}", "/api/v1/repositories/{repository_id}/refresh",
        "/api/v1/repositories/{repository_id}/analysis", "/api/v1/repositories/{repository_id}/series",
        "/api/v1/tasks", "/api/v1/tasks/{task_id}", "/api/v1/tasks/{task_id}/retry", "/api/v1/datasets",
        "/api/v1/overview", "/api/v1/research/statistics", "/api/v1/research/data-quality",
        "/api/v1/comparisons", "/api/v1/exports/repositories.csv",
    }
    assert expected <= set(paths)
    assert paths["/api/v1/github/search"]["get"]["responses"]["422"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ErrorResponse"

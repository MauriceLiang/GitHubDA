from uuid import uuid4

from backend.app.core.config import Settings
from backend.app.persistence.models import ApplicationSetting, CollectionTask, Repository, TaskModuleProgress
from backend.app.worker.queue import claim_next_task


HEADERS = {"X-Internal-Api-Key": "test-internal-key"}


def test_collection_page_setting_defaults_persists_and_validates(backend_client):
    client, _factory, _github = backend_client

    assert Settings(_env_file=None).github_max_pages == 10
    fallback = client.get("/api/v1/settings", headers=HEADERS)
    assert fallback.status_code == 200
    assert fallback.json()["data"]["github_max_pages"] == 10

    saved = client.post("/api/v1/settings", json={"github_max_pages": 37}, headers=HEADERS)
    assert saved.status_code == 200
    assert saved.json()["data"]["github_max_pages"] == 37
    assert client.get("/api/v1/settings", headers=HEADERS).json()["data"]["github_max_pages"] == 37

    for value in (0, 101):
        invalid = client.post("/api/v1/settings", json={"github_max_pages": value}, headers=HEADERS)
        assert invalid.status_code == 422

    for value in (1, 100):
        boundary = client.post("/api/v1/settings", json={"github_max_pages": value}, headers=HEADERS)
        assert boundary.status_code == 200
        assert boundary.json()["data"]["github_max_pages"] == value


def test_saved_page_limit_is_snapshotted_into_new_deep_task(backend_client):
    client, factory, _github = backend_client
    task_id = str(uuid4())
    repository_id = 778899
    with factory() as session:
        session.add(ApplicationSetting(setting_key="github_max_pages", setting_value="37"))
        session.add(Repository(
            repository_id=repository_id,
            full_name="example/page-cap",
            html_url="https://github.com/example/page-cap",
        ))
        session.flush()
        session.add(CollectionTask(
            task_id=task_id,
            repository_id=repository_id,
            depth="deep",
            status="queued",
        ))
        session.commit()

    with factory() as session:
        task = claim_next_task(session, "page-cap-worker", 60)
        assert task and task.task_id == task_id

    detail = client.get(f"/api/v1/tasks/{task_id}", headers=HEADERS)
    assert detail.status_code == 200
    modules = {item["name"]: item for item in detail.json()["data"]["modules"]}
    assert modules["profile"]["page_cap"] == 1
    assert {modules[name]["page_cap"] for name in ("commits", "issues", "pulls", "releases")} == {37}

    with factory() as session:
        commits = session.get(TaskModuleProgress, (task_id, "commits"))
        assert commits.page_cap == 37


def test_browser_settings_endpoint_supports_session_protected_save(backend_client):
    _legacy_client, _factory, _github = backend_client
    from fastapi.testclient import TestClient

    from backend.app.main import app

    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 55002)) as client:
        origin = "http://127.0.0.1"
        headers = {"X-GDA-Request": "browser", "Origin": origin}
        bootstrap = client.get("/api/browser/session", headers=headers)
        assert bootstrap.status_code == 200
        headers["X-CSRF-Token"] = bootstrap.json()["csrf_token"]

        current = client.get("/api/browser/v1/settings", headers=headers)
        assert current.status_code == 200
        saved = client.post(
            "/api/browser/v1/settings",
            headers=headers,
            json={"github_max_pages": 23},
        )

    assert saved.status_code == 200
    assert saved.json()["data"]["github_max_pages"] == 23

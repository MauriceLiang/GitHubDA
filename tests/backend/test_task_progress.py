from datetime import timedelta
import json
from uuid import uuid4

import pytest

from backend.app.core.clock import utc_now
from backend.app.persistence.models import CollectionTask, TaskModuleProgress
from backend.app.schemas.tasks import TaskResponse
from backend.app.worker.progress import StaleTaskAttempt, TaskProgressReporter
from backend.app.worker.queue import claim_next_task


HEADERS = {"X-Internal-Api-Key": "test-internal-key"}


def _queued_deep_task(client, factory):
    added = client.post(
        "/api/v1/library/repositories",
        json={"full_name": "example/project", "auto_analyze": False},
        headers=HEADERS,
    )
    task_id = str(uuid4())
    with factory() as session:
        session.add(CollectionTask(task_id=task_id, repository_id=added.json()["data"]["repository_id"], depth="deep", status="queued"))
        session.commit()
    with factory() as session:
        task = claim_next_task(session, "progress-worker", 60)
        assert task and task.task_id == task_id
    return task_id


def test_task_detail_persists_module_progress_and_legacy_fields(backend_client):
    client, factory, _github = backend_client
    task_id = _queued_deep_task(client, factory)
    response = client.get(f"/api/v1/tasks/{task_id}", headers=HEADERS)
    assert response.status_code == 200
    task = response.json()["data"]
    assert task["status"] == "running"
    assert task["progress_kind"] == "stages"
    assert task["progress_percent"] == 0
    assert task["current_module"] == "profile"
    assert [module["name"] for module in task["modules"]] == ["profile", "commits", "issues", "pulls", "releases"]
    assert all(module["status"] == "pending" for module in task["modules"])
    assert task["eta_seconds"] is None

    reporter = TaskProgressReporter(factory, task_id, 1, "progress-worker")
    reporter.begin_module("profile", page_cap=1)
    reporter.page_fetched("profile", pages_fetched=1, observed_items=1)
    profile = client.get(f"/api/v1/tasks/{task_id}", headers=HEADERS).json()["data"]
    assert profile["current_module"] == "profile"
    assert profile["modules"][0]["status"] == "running"
    assert profile["modules"][0]["pages_fetched"] == 1
    assert profile["modules"][0]["observed_items"] == 1
    assert profile["progress_updated_at"] is not None
    assert profile["elapsed_seconds"] >= 0

    reporter.finish_module("profile", status="complete", coverage="complete", elapsed_seconds=0.1)
    reporter.begin_module("issues", page_cap=10)
    reporter.page_fetched("issues", pages_fetched=1, observed_items=20)
    reporter.page_fetched("issues", pages_fetched=2, observed_items=40)
    issues = client.get(f"/api/v1/tasks/{task_id}", headers=HEADERS).json()["data"]
    assert issues["current_module"] == "issues"
    assert issues["progress_percent"] == 12
    assert issues["modules"][2]["status"] == "running"
    assert issues["modules"][2]["pages_fetched"] == 2
    assert issues["modules"][2]["observed_items"] == 40
    assert issues["modules"][2]["page_cap"] == 10

    task_list = client.get("/api/v1/tasks", headers=HEADERS).json()["data"]["items"][0]
    assert task_list["progress_percent"] == 12
    assert len(task_list["modules"]) == 5
    assert task_list["modules"][2]["pages_fetched"] == 2

    old_task = TaskResponse.model_validate({
        "task_id": task_id,
        "repository_id": 123,
        "type": "collect_repository",
        "depth": "deep",
        "status": "queued",
        "phase": None,
        "progress_percent": None,
        "message": None,
        "attempt": 0,
        "created_at": "2026-10-14T00:00:00Z",
        "started_at": None,
        "finished_at": None,
        "error": None,
    })
    assert old_task.progress_kind == "unknown"
    assert old_task.modules == []
    assert old_task.eta_seconds is None


def test_task_list_includes_saved_window_and_resume_state(backend_client):
    client, factory, _github = backend_client
    added = client.post(
        "/api/v1/library/repositories",
        json={"full_name": "example/project", "auto_analyze": False},
        headers=HEADERS,
    )
    task_id = str(uuid4())
    start = "2026-07-24T00:00:00Z"
    end = "2026-10-22T00:00:00Z"
    resume_after = utc_now() + timedelta(minutes=10)
    with factory() as session:
        session.add(CollectionTask(
            task_id=task_id,
            repository_id=added.json()["data"]["repository_id"],
            depth="deep",
            scope_kind="window",
            scope_json=json.dumps({"window_start": start, "window_end": end}),
            status="queued",
            resume_after=resume_after,
        ))
        session.commit()

    task = client.get("/api/v1/tasks", headers=HEADERS).json()["data"]["items"][0]
    assert task["scope_kind"] == "window"
    assert task["window_start"] == start
    assert task["window_end"] == end
    assert task["resume_after"] is not None


def test_late_progress_from_expired_attempt_cannot_update_reclaimed_task(backend_client):
    client, factory, _github = backend_client
    task_id = _queued_deep_task(client, factory)
    old_reporter = TaskProgressReporter(factory, task_id, 1, "progress-worker")
    old_reporter.begin_module("profile", page_cap=1)

    with factory() as session:
        task = session.get(CollectionTask, task_id)
        task.lease_until = utc_now() - timedelta(seconds=1)
        session.commit()
    with factory() as session:
        reclaimed = claim_next_task(session, "replacement-worker", 60)
        assert reclaimed and reclaimed.task_id == task_id and reclaimed.attempt == 2

    with pytest.raises(StaleTaskAttempt):
        old_reporter.page_fetched("profile", pages_fetched=1, observed_items=1)

    current = client.get(f"/api/v1/tasks/{task_id}", headers=HEADERS).json()["data"]
    assert current["attempt"] == 2
    assert current["progress_percent"] == 0
    assert all(module["status"] == "pending" for module in current["modules"])
    assert current["modules"][0]["pages_fetched"] == 0


def test_task_module_state_does_not_allow_terminal_module_to_restart(backend_client):
    client, factory, _github = backend_client
    task_id = _queued_deep_task(client, factory)
    reporter = TaskProgressReporter(factory, task_id, 1, "progress-worker")
    reporter.begin_module("profile", page_cap=1)
    reporter.finish_module("profile", status="complete", coverage="complete", elapsed_seconds=0.1)

    with pytest.raises(ValueError, match="terminal"):
        reporter.begin_module("profile", page_cap=1)

    with factory() as session:
        progress = session.get(TaskModuleProgress, (task_id, "profile"))
        assert progress.status == "complete"

import json
from datetime import datetime

from sqlalchemy import select

from backend.app.persistence.models import CollectionTask, Repository
from scripts.queue_history_pilot import PILOT_REPOSITORIES, queue_history_pilot


def test_history_pilot_defaults_to_preview_and_queues_only_local_repositories(backend_client):
    client, factory, _github = backend_client
    with factory() as session:
        session.add(Repository(
            repository_id=456,
            full_name=PILOT_REPOSITORIES[0],
            html_url=f"https://github.com/{PILOT_REPOSITORIES[0]}",
            created_at=datetime(2010, 1, 1),
        ))
        session.commit()

    with factory() as session:
        preview = queue_history_pilot(session, now=datetime(2026, 10, 22), queue=False)
        assert session.scalar(select(CollectionTask.task_id)) is None
    assert preview[0]["status"] == "would_queue"
    assert preview[0]["window_start"] == "2010-01-01T00:00:00Z"
    assert all(item["status"] == "missing_local_repository" for item in preview[1:])

    with factory() as session:
        queued = queue_history_pilot(session, now=datetime(2026, 10, 22), queue=True)
        task = session.scalar(select(CollectionTask).where(CollectionTask.repository_id == 456))
        scope = json.loads(task.scope_json)
    assert queued[0]["status"] == "queued"
    assert task.scope_kind == "backfill"
    assert scope["start_basis"] == "github_repository_created_at"
    assert scope["pilot"] is True
    response = client.get("/api/v1/tasks", headers={"X-Internal-Api-Key": "test-internal-key"})
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["scope_kind"] == "backfill"

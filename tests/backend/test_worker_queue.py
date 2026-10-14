from datetime import timedelta

from backend.app.core.clock import utc_now
from backend.app.persistence.models import CollectionTask
from backend.app.worker.queue import claim_next_task


HEADERS = {"X-Internal-Api-Key": "test-internal-key"}


def test_expired_worker_lease_requeues_and_reclaims_until_attempt_limit(backend_client):
    client, factory, _github = backend_client
    added = client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS)
    task_id = "11111111-2222-4333-8444-555555555555"
    with factory() as session:
        session.add(CollectionTask(task_id=task_id, repository_id=added.json()["data"]["repository_id"], depth="basic", status="queued", created_at=utc_now()))
        session.commit()

    with factory() as session:
        first = claim_next_task(session, "worker-one", 30)
        assert first and first.task_id == task_id and first.attempt == 1
        first.lease_until = utc_now() - timedelta(seconds=1)
        session.commit()

    with factory() as session:
        recovered = claim_next_task(session, "worker-two", 30)
        assert recovered and recovered.task_id == task_id
        assert recovered.status == "running" and recovered.attempt == 2
        assert recovered.lease_owner == "worker-two"
        recovered.lease_until = utc_now() - timedelta(seconds=1)
        session.commit()

    with factory() as session:
        final_attempt = claim_next_task(session, "worker-three", 30)
        assert final_attempt and final_attempt.task_id == task_id and final_attempt.attempt == 3
        final_attempt.lease_until = utc_now() - timedelta(seconds=1)
        session.commit()

    with factory() as session:
        assert claim_next_task(session, "worker-four", 30) is None
        failed = session.get(CollectionTask, task_id)
        assert failed.status == "failed"
        assert failed.error_code == "WORKER_LEASE_EXPIRED"
        assert failed.attempt == 3

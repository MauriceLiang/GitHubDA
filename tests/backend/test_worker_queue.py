from datetime import timedelta

import httpx

from backend.app.core.clock import utc_now
from backend.app.integrations.github.client import GITHUB_API
from backend.app.persistence.models import ApiRateLimitState, CollectionTask, DatasetImportJob
from backend.app.worker.queue import claim_next_dataset_import_job, claim_next_task
from backend.app.worker.main import _persist_rate_limit_state


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


def test_persisted_github_quota_pause_prevents_claiming_any_repository_task(backend_client):
    client, factory, _github = backend_client
    added = client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS)
    task_id = "11111111-2222-4333-8444-555555555556"
    with factory() as session:
        session.add(CollectionTask(task_id=task_id, repository_id=added.json()["data"]["repository_id"], depth="deep", status="queued", created_at=utc_now()))
        session.add(ApiRateLimitState(resource="core", remaining=0, reset_at=utc_now() + timedelta(minutes=5), observed_at=utc_now()))
        session.commit()

    with factory() as session:
        assert claim_next_task(session, "quota-worker", 30) is None
        task = session.get(CollectionTask, task_id)
        assert task.status == "queued"
        quota = session.get(ApiRateLimitState, "core")
        quota.remaining = 1
        quota.retry_after = utc_now() - timedelta(seconds=1)
        session.commit()

    with factory() as session:
        claimed = claim_next_task(session, "quota-worker", 30)
        assert claimed and claimed.task_id == task_id


def test_secondary_rate_limit_without_retry_after_sets_global_minute_pause(backend_client):
    client, factory, _github = backend_client
    added = client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS)
    task_id = "11111111-2222-4333-8444-555555555557"
    with factory() as session:
        session.add(CollectionTask(task_id=task_id, repository_id=added.json()["data"]["repository_id"], depth="basic", status="queued", created_at=utc_now()))
        session.commit()

    _persist_rate_limit_state(httpx.Response(403, json={"message": "You have exceeded a secondary rate limit."}, request=httpx.Request("GET", f"{GITHUB_API}/repos/example/project")))

    with factory() as session:
        quota = session.get(ApiRateLimitState, "core")
        assert quota is not None
        assert quota.retry_after is not None
        assert timedelta(seconds=55) <= quota.retry_after - utc_now() <= timedelta(seconds=60)
        assert claim_next_task(session, "secondary-quota-worker", 30) is None


def test_backfill_queue_yields_to_normal_collection_tasks(backend_client):
    client, factory, _github = backend_client
    added = client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS)
    repository_id = added.json()["data"]["repository_id"]
    now = utc_now()
    with factory() as session:
        session.add(CollectionTask(
            task_id="history-backfill-task",
            repository_id=repository_id,
            depth="deep",
            scope_kind="backfill",
            scope_json='{"window_start":"2020-01-01T00:00:00Z","window_end":"2026-10-22T00:00:00Z"}',
            status="queued",
            created_at=now - timedelta(minutes=5),
        ))
        session.add(CollectionTask(
            task_id="interactive-window-task",
            repository_id=repository_id,
            depth="deep",
            scope_kind="window",
            scope_json='{"window_start":"2026-07-24T00:00:00Z","window_end":"2026-10-22T00:00:00Z"}',
            status="queued",
            created_at=now,
        ))
        session.commit()

    with factory() as session:
        claimed = claim_next_task(session, "priority-worker", 30)
    assert claimed and claimed.task_id == "interactive-window-task"


def test_refresh_freezes_selected_window_and_only_reuses_matching_scope(backend_client):
    client, _factory, _github = backend_client
    added = client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS)
    repository_id = added.json()["data"]["repository_id"]

    def refresh(scope_kind, window_days, key):
        return client.post(
            f"/api/v1/repositories/{repository_id}/refresh",
            json={"depth": "deep", "scope_kind": scope_kind, "window_days": window_days},
            headers={**HEADERS, "Idempotency-Key": key},
        )

    first = refresh("quick", 30, "quick-30-first")
    assert first.status_code == 202, first.text
    first_id = first.json()["data"]["task_id"]
    repeated = refresh("quick", 30, "quick-30-repeat")
    assert repeated.status_code == 202 and repeated.json()["data"]["task_id"] == first_id
    assert repeated.json()["data"]["reused"] is True
    different_window = refresh("quick", 180, "quick-180")
    assert different_window.status_code == 202, different_window.text
    second_id = different_window.json()["data"]["task_id"]
    assert second_id != first_id
    different_mode = refresh("window", 180, "window-180")
    assert different_mode.status_code == 202, different_mode.text
    third_id = different_mode.json()["data"]["task_id"]
    assert third_id not in {first_id, second_id}

    tasks = client.get(f"/api/v1/tasks?repository_id={repository_id}&per_page=100", headers=HEADERS).json()["data"]["items"]
    by_id = {task["task_id"]: task for task in tasks}
    assert by_id[first_id]["window_days"] == 30
    assert by_id[second_id]["window_days"] == 180
    assert by_id[third_id]["scope_kind"] == "window"
    assert by_id[third_id]["window_days"] == 180
    for task, days in ((by_id[first_id], 30), (by_id[second_id], 180), (by_id[third_id], 180)):
        from datetime import datetime
        start = datetime.fromisoformat(task["window_start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(task["window_end"].replace("Z", "+00:00"))
        assert (end - start).days == days
    invalid = client.post(
        f"/api/v1/repositories/{repository_id}/refresh",
        json={"depth": "deep", "scope_kind": "quick", "window_days": 60},
        headers={**HEADERS, "Idempotency-Key": "invalid-window"},
    )
    assert invalid.status_code == 422


def test_dataset_import_worker_ignores_github_quota_and_recovers_expired_lease(backend_client):
    client, factory, _github = backend_client
    added = client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS).json()["data"]
    now = utc_now()
    with factory() as session:
        session.add(DatasetImportJob(
            task_id="dataset-import-lease",
            dataset_id="featured-default",
            bundle_version="featured-test",
            bundle_hash="c" * 64,
            status="queued",
            phase="validating",
            progress_kind="indeterminate",
            created_at=now,
            updated_at=now,
        ))
        session.add(CollectionTask(
            task_id="collection-waits-for-dataset-import",
            repository_id=added["repository_id"],
            depth="basic",
            status="queued",
            created_at=now,
        ))
        session.add(ApiRateLimitState(resource="core", remaining=0, reset_at=now + timedelta(minutes=5), observed_at=now))
        session.commit()

    with factory() as session:
        first = claim_next_dataset_import_job(session, "dataset-worker-one", 30)
        assert first and first.task_id == "dataset-import-lease"
        assert first.attempt == 1
        first.lease_until = utc_now() - timedelta(seconds=1)
        session.commit()

    with factory() as session:
        recovered = claim_next_dataset_import_job(session, "dataset-worker-two", 30)
        assert recovered and recovered.task_id == "dataset-import-lease"
        assert recovered.attempt == 2
        assert recovered.status == "running"
        assert recovered.lease_owner == "dataset-worker-two"
        quota = session.get(ApiRateLimitState, "core")
        quota.remaining = 1
        quota.retry_after = utc_now() - timedelta(seconds=1)
        session.commit()
        assert claim_next_task(session, "repository-worker", 30) is None

import json
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.app.core.clock import iso_z, utc_now
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import PageObservation, PaginatedResult
from backend.app.persistence.models import ActivityWindow, AnalysisResult, CollectionLog, CollectionTask, RepositorySnapshot, TaskModuleProgress
from backend.app.pipeline.raw_archive import archive_json
from backend.app.services.repositories import latest_analysis
from backend.app.worker.executor import execute_task
from backend.app.worker.queue import claim_next_task


HEADERS = {"X-Internal-Api-Key": "test-internal-key"}
OLD_ETAG = '"previous-profile"'


class WorkerGitHub:
    def __init__(self, repository, *, conditional_304=False, unconditional_304=False, fail_module=None):
        self.repository = repository
        self.conditional_304 = conditional_304
        self.unconditional_304 = unconditional_304
        self.fail_module = fail_module
        self.profile_etags = []
        self.deep_calls = []
        self.max_pages = 10
        event_time = iso_z(utc_now() - timedelta(days=1))
        self.records = {
            "commits": [{"sha": "a" * 40, "commit": {"committer": {"date": event_time}}}],
            "issues": [{"id": 1, "created_at": event_time, "closed_at": event_time}],
            "pulls": [{"id": 2, "created_at": event_time, "merged_at": event_time}],
            "releases": [{"id": 3, "published_at": event_time}],
        }

    def get_repository_by_id(self, _repository_id, etag=None):
        self.profile_etags.append(etag)
        if self.unconditional_304 or (self.conditional_304 and etag):
            return None, 304, etag
        return self.repository, 200, '"fresh-profile"'

    def _list(self, module):
        self.deep_calls.append(module)
        if self.fail_module == module:
            raise AppError(504, "GITHUB_TIMEOUT", f"{module} timed out")
        return self.records[module], True, ["[]"]

    def _list_detailed(self, module, on_page=None):
        rows, complete, pages = self._list(module)
        if on_page:
            for index in range(len(pages)):
                on_page(PageObservation(
                    page_index=index + 1,
                    pages_fetched=index + 1,
                    observed_items=len(rows),
                    page_cap=self.max_pages,
                    has_next=not complete and index == len(pages) - 1,
                    duration_ms=0.1,
                ))
        return PaginatedResult(
            items=rows,
            raw_pages=pages,
            complete=complete,
            pages_fetched=len(pages),
            observed_items=len(rows),
            has_next=not complete,
            http_calls=len(pages),
            duration_ms=0.1,
        )

    def list_commits(self, *_args):
        return self._list("commits")

    def list_issues(self, *_args):
        return self._list("issues")

    def list_pulls(self, *_args):
        return self._list("pulls")

    def list_releases(self, *_args):
        return self._list("releases")

    def list_commits_detailed(self, _full_name, _since, _until, *, on_page=None):
        return self._list_detailed("commits", on_page)

    def list_issues_detailed(self, _full_name, _since, _state="all", *, on_page=None):
        return self._list_detailed("issues", on_page)

    def list_pulls_detailed(self, _full_name, _state="closed", *, on_page=None):
        return self._list_detailed("pulls", on_page)

    def list_releases_detailed(self, _full_name, *, on_page=None):
        return self._list_detailed("releases", on_page)


def _create_repository(client):
    response = client.post(
        "/api/v1/library/repositories",
        json={"full_name": "example/project", "auto_analyze": False},
        headers=HEADERS,
    )
    assert response.status_code == 201


def _queue_task(factory, depth, *, with_snapshot=False, with_basic_analysis=False):
    task_id = str(uuid4())
    collected_at = utc_now() - timedelta(hours=1)
    with factory() as session:
        if with_snapshot:
            session.add(RepositorySnapshot(
                repository_id=123,
                collected_at=collected_at,
                stars=20,
                forks=3,
                open_issues_and_pr_count=4,
                response_etag=OLD_ETAG,
                source_http_status=200,
                valid=True,
            ))
        if with_basic_analysis:
            session.add(AnalysisResult(
                repository_id=123,
                analysis_kind="basic",
                metric_version="metrics-v1",
                source_collected_at=collected_at,
                calculated_at=collected_at,
                coverage="complete",
                metrics_json='{"stars":20,"forks":3,"age_days":10,"days_since_push":1}',
                limitations_json="[]",
                valid_sample_size=1,
            ))
        session.add(CollectionTask(task_id=task_id, repository_id=123, depth=depth, status="queued", created_at=utc_now()))
        session.commit()
    with factory() as session:
        claimed = claim_next_task(session, "test-worker", 60)
        assert claimed and claimed.task_id == task_id and claimed.attempt == 1
    return task_id


def _patch_archives(monkeypatch):
    monkeypatch.setattr("backend.app.worker.executor.archive_json", lambda *_args, **_kwargs: "test/archive.json.gz")


def test_basic_304_reuses_only_a_matching_basic_result_without_new_observation(backend_client, monkeypatch):
    client, factory, default_github = backend_client
    _create_repository(client)
    task_id = _queue_task(factory, "basic", with_snapshot=True, with_basic_analysis=True)
    _patch_archives(monkeypatch)
    github = WorkerGitHub(default_github.repository, conditional_304=True)

    execute_task(factory, task_id, github)

    with factory() as session:
        task = session.get(CollectionTask, task_id)
        snapshots = session.scalar(select(func.count()).select_from(RepositorySnapshot).where(RepositorySnapshot.repository_id == 123))
        analyses = session.scalar(select(func.count()).select_from(AnalysisResult).where(AnalysisResult.repository_id == 123))
        log = session.scalar(select(CollectionLog).where(CollectionLog.task_id == task_id))
    assert github.profile_etags == [OLD_ETAG]
    assert task.status == "succeeded"
    assert snapshots == analyses == 1
    assert log.http_status == 304


def test_basic_without_current_analysis_does_not_send_etag_and_rebuilds(backend_client, monkeypatch):
    client, factory, default_github = backend_client
    _create_repository(client)
    task_id = _queue_task(factory, "basic", with_snapshot=True)
    _patch_archives(monkeypatch)
    github = WorkerGitHub(default_github.repository)

    execute_task(factory, task_id, github)

    with factory() as session:
        task = session.get(CollectionTask, task_id)
        snapshots = session.scalar(select(func.count()).select_from(RepositorySnapshot).where(RepositorySnapshot.repository_id == 123))
        analysis = latest_analysis(session, 123, "basic")
    assert github.profile_etags == [None]
    assert task.status == "succeeded"
    assert snapshots == 2
    assert analysis is not None


def test_unexpected_304_without_reusable_basic_result_fails_honestly(backend_client, monkeypatch):
    client, factory, default_github = backend_client
    _create_repository(client)
    task_id = _queue_task(factory, "basic", with_snapshot=True)
    _patch_archives(monkeypatch)
    github = WorkerGitHub(default_github.repository, unconditional_304=True)

    execute_task(factory, task_id, github)

    with factory() as session:
        task = session.get(CollectionTask, task_id)
        analyses = session.scalar(select(func.count()).select_from(AnalysisResult).where(AnalysisResult.repository_id == 123))
    assert github.profile_etags == [None]
    assert task.status == "failed"
    assert task.error_code == "GITHUB_UPSTREAM_ERROR"
    assert analyses == 0


def test_deep_task_ignores_etag_and_persists_basic_and_deep_at_same_snapshot(backend_client, monkeypatch):
    client, factory, default_github = backend_client
    _create_repository(client)
    task_id = _queue_task(factory, "deep", with_snapshot=True, with_basic_analysis=True)
    _patch_archives(monkeypatch)
    github = WorkerGitHub(default_github.repository, conditional_304=True)

    execute_task(factory, task_id, github)

    with factory() as session:
        task = session.get(CollectionTask, task_id)
        snapshot = session.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_id == 123).order_by(RepositorySnapshot.id.desc()))
        basic = latest_analysis(session, 123, "basic")
        deep = latest_analysis(session, 123, "deep")
        modules = session.scalars(select(TaskModuleProgress).where(TaskModuleProgress.task_id == task_id).order_by(TaskModuleProgress.module)).all()
    assert github.profile_etags == [None]
    assert github.deep_calls == ["commits", "issues", "pulls", "releases"]
    assert task.status == "succeeded"
    assert task.progress_kind == "stages"
    assert task.progress_percent == 100
    assert task.current_module is None
    assert [item.status for item in modules] == ["complete"] * 5
    assert basic.source_collected_at == deep.source_collected_at == snapshot.collected_at
    assert basic.window_start is basic.window_end is None
    assert json.loads(basic.metrics_json)["commits_90d"] is None
    assert json.loads(deep.metrics_json)["commits_90d"] == 1


def test_deep_partial_coverage_keeps_basic_profile_complete(backend_client, monkeypatch):
    client, factory, default_github = backend_client
    _create_repository(client)
    task_id = _queue_task(factory, "deep")
    archived = {}

    def capture_archive(_repository_id, _task_id, kind, value):
        if kind == "deep_responses":
            archived.update(value)
        return f"test/{kind}.json.gz"

    monkeypatch.setattr("backend.app.worker.executor.archive_json", capture_archive)
    github = WorkerGitHub(default_github.repository, fail_module="commits")

    execute_task(factory, task_id, github)

    with factory() as session:
        task = session.get(CollectionTask, task_id)
        basic = latest_analysis(session, 123, "basic")
        deep = latest_analysis(session, 123, "deep")
    assert task.status == "partial"
    assert basic.coverage == "complete"
    assert json.loads(deep.metrics_json)["commits_90d"] is None
    assert deep.coverage == "partial"
    assert archived["commits"]["error"] == "GITHUB_TIMEOUT"


def test_deep_activity_archive_failure_keeps_collected_snapshot(backend_client, monkeypatch):
    client, factory, default_github = backend_client
    _create_repository(client)
    task_id = _queue_task(factory, "deep")

    def archive(_repository_id, _task_id, kind, _value):
        if kind == "activity":
            raise OSError("disk full")
        return f"test/{kind}.json.gz"

    monkeypatch.setattr("backend.app.worker.executor.archive_json", archive)
    execute_task(factory, task_id, WorkerGitHub(default_github.repository))

    with factory() as session:
        task = session.get(CollectionTask, task_id)
        snapshot = session.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_id == 123))
        activity = session.scalar(select(ActivityWindow).where(ActivityWindow.repository_id == 123))
        archive_error = session.scalar(select(CollectionLog).where(CollectionLog.task_id == task_id, CollectionLog.event_type == "archive_failed"))
    assert task.status == "succeeded"
    assert snapshot is not None
    assert activity is not None and activity.source_archive_path is None
    assert archive_error is not None


def test_raw_archive_rejects_paths_outside_configured_root(tmp_path, monkeypatch):
    root = tmp_path / "raw"
    root.mkdir()
    monkeypatch.setattr("backend.app.pipeline.raw_archive.get_settings", lambda: type("Settings", (), {"raw_data_path": root})())

    with pytest.raises(ValueError, match="escapes configured raw data directory"):
        archive_json(123, "task-id", "../../../../outside", {"data": "value"})
    assert not (tmp_path / "outside.json.gz").exists()

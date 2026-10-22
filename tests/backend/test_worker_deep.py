import json
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.app.core.clock import iso_z, utc_now
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import PageObservation, PaginatedResult
from backend.app.persistence.models import ActivityWindow, AnalysisResult, CollectionCheckpoint, CollectionLog, CollectionTask, RepositoryActivityEvent, RepositoryInsightRun, RepositorySnapshot, TaskModuleProgress
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
        self.deep_queries = []
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

    def _list_detailed(self, module, on_page=None, **options):
        rows, complete, pages = self._list(module)
        page_offset = options.get("page_offset", 0)
        records_offset = options.get("records_offset", 0)
        stop_after_page = options.get("stop_after_page")
        if on_page:
            for index in range(len(pages)):
                has_next = not complete and index == len(pages) - 1
                if stop_after_page and stop_after_page(rows):
                    has_next = False
                    complete = True
                on_page(PageObservation(
                    page_index=page_offset + index + 1,
                    pages_fetched=page_offset + index + 1,
                    observed_items=records_offset + len(rows),
                    page_cap=self.max_pages,
                    has_next=has_next,
                    duration_ms=0.1,
                    records=rows,
                    raw_body=json.dumps(rows),
                    request_url="https://api.github.com/repos/example/project/commits?per_page=100",
                    next_url="https://api.github.com/repos/example/project/commits?page=2" if has_next else None,
                    http_status=200,
                ))
        return PaginatedResult(
            items=[] if not options.get("collect_items", True) else rows,
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

    def list_commits_detailed(self, _full_name, since, until, *, on_page=None, **options):
        self.deep_queries.append(("commits", since, until))
        return self._list_detailed("commits", on_page, **options)

    def list_issues_detailed(self, _full_name, since, _state="all", *, on_page=None, **options):
        self.deep_queries.append(("issues", since, None))
        return self._list_detailed("issues", on_page, **options)

    def list_pulls_detailed(self, _full_name, _state="closed", *, on_page=None, **options):
        return self._list_detailed("pulls", on_page, **options)

    def list_releases_detailed(self, _full_name, *, on_page=None, **options):
        return self._list_detailed("releases", on_page, **options)


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
        if kind == "activity":
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
    assert archived["_meta"]["sources"]["commits"]["coverage"] == "partial"


def test_worker_uses_frozen_window_days_and_keeps_release_collection_at_365_days(backend_client, monkeypatch):
    client, factory, default_github = backend_client
    _create_repository(client)
    _patch_archives(monkeypatch)
    now = utc_now().replace(microsecond=0)
    start = now - timedelta(days=180)
    task_id = str(uuid4())
    with factory() as session:
        session.add(CollectionTask(
            task_id=task_id,
            repository_id=123,
            depth="deep",
            scope_kind="quick",
            scope_json=json.dumps({"window_start": iso_z(start), "window_end": iso_z(now), "window_days": 180}),
            status="queued",
            created_at=now,
        ))
        session.commit()
    with factory() as session:
        claimed = claim_next_task(session, "test-worker", 60)
        assert claimed and claimed.task_id == task_id and claimed.attempt == 1

    github = WorkerGitHub(default_github.repository)
    execute_task(factory, task_id, github)

    with factory() as session:
        task = session.get(CollectionTask, task_id)
        run = session.scalar(select(RepositoryInsightRun).where(RepositoryInsightRun.repository_id == 123))
        window = session.scalar(select(ActivityWindow).where(ActivityWindow.repository_id == 123))
    assert task.status == "succeeded"
    assert github.deep_queries[:2] == [("commits", iso_z(start), iso_z(now)), ("issues", iso_z(start), None)]
    assert window.window_start == start and window.window_end == now
    sources = json.loads(run.module_coverage_json)
    assert sources["releases"]["requested_interval"] == [iso_z(now - timedelta(days=365)), iso_z(now)]


def test_successful_empty_activity_is_complete_and_distinct_from_failed_endpoint(backend_client, monkeypatch):
    client, factory, default_github = backend_client
    _create_repository(client)
    task_id = _queue_task(factory, "deep")
    _patch_archives(monkeypatch)
    github = WorkerGitHub(default_github.repository)
    github.records = {module: [] for module in ("commits", "issues", "pulls", "releases")}

    execute_task(factory, task_id, github)

    with factory() as session:
        task = session.get(CollectionTask, task_id)
        insight = session.scalar(select(RepositoryInsightRun).where(RepositoryInsightRun.repository_id == 123))
    assert task.status == "succeeded"
    assert insight.status == "ready"
    assert insight.module_coverage_json
    sources = json.loads(insight.module_coverage_json)
    assert all(source["coverage"] == "complete" for source in sources.values())
    assert all(source["observed_records"] == 0 for source in sources.values())
    assert all(source.get("error_code") is None for source in sources.values())


def test_reaching_user_page_limit_marks_collection_and_analysis_incomplete(backend_client, monkeypatch):
    client, factory, default_github = backend_client
    _create_repository(client)
    task_id = _queue_task(factory, "deep")
    archived = {}

    class PageLimitedGitHub(WorkerGitHub):
        def __init__(self, repository):
            super().__init__(repository)
            self.max_pages = 2

        def list_commits_detailed(self, _full_name, _since, _until, *, on_page=None, **options):
            rows = self.records["commits"]
            pages = ["[]", "[]"]
            if on_page:
                for page in range(1, self.max_pages + 1):
                    on_page(PageObservation(
                        page_index=page,
                        pages_fetched=page,
                        observed_items=len(rows),
                        page_cap=self.max_pages,
                        has_next=True,
                        duration_ms=0.1,
                        records=rows,
                        raw_body=json.dumps(rows),
                        request_url="https://api.github.com/repos/example/project/commits?page=1",
                        next_url="https://api.github.com/repos/example/project/commits?page=3",
                        http_status=200,
                    ))
            return PaginatedResult(
                items=[] if not options.get("collect_items", True) else rows,
                raw_pages=pages,
                complete=False,
                pages_fetched=self.max_pages,
                observed_items=len(rows),
                has_next=True,
                http_calls=self.max_pages,
                duration_ms=0.2,
            )

    def capture_archive(_repository_id, _task_id, kind, value):
        if kind == "activity":
            archived.update(value)
        return f"test/{kind}.json.gz"

    monkeypatch.setattr("backend.app.worker.executor.archive_json", capture_archive)
    execute_task(factory, task_id, PageLimitedGitHub(default_github.repository))

    with factory() as session:
        task = session.get(CollectionTask, task_id)
        deep = latest_analysis(session, 123, "deep")
        commit_progress = session.get(TaskModuleProgress, (task_id, "commits"))
        insight = session.scalar(select(RepositoryInsightRun).where(RepositoryInsightRun.repository_id == 123))

    assert task.status == "partial"
    assert task.message == "已达到用户设置的页数预算，后续页面未采集完整"
    assert deep.coverage == "partial"
    assert commit_progress.status == "partial"
    assert commit_progress.coverage == "budget_exhausted"
    assert commit_progress.pages_fetched == commit_progress.page_cap == 2
    assert commit_progress.error_code == "GITHUB_MAX_PAGES"
    assert insight.status == "partial"
    assert archived["_meta"]["sources"]["commits"]["limit_reached"] is True
    assert archived["_meta"]["sources"]["commits"]["has_next"] is True
    assert archived["commits"]["error"] == "GITHUB_MAX_PAGES"


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


def test_history_backfill_yields_after_page_budget_with_checkpoint_for_resume(backend_client, monkeypatch):
    client, factory, default_github = backend_client
    _create_repository(client)
    _patch_archives(monkeypatch)
    now = utc_now().replace(microsecond=0)
    scope = {
        "window_start": "2020-01-01T00:00:00Z",
        "window_end": iso_z(now),
        "analysis_window_start": iso_z(now - timedelta(days=90)),
        "analysis_window_end": iso_z(now),
        "start_basis": "github_repository_created_at",
        "pilot": True,
    }
    task_id = str(uuid4())
    with factory() as session:
        session.add(CollectionTask(task_id=task_id, repository_id=123, depth="deep", scope_kind="backfill", scope_json=json.dumps(scope), status="queued", created_at=now))
        session.commit()
    with factory() as session:
        assert claim_next_task(session, "backfill-worker", 60).task_id == task_id

    class PageLimitedGitHub(WorkerGitHub):
        def __init__(self, repository):
            super().__init__(repository)
            self.max_pages = 2

        def list_commits_detailed(self, _full_name, _since, _until, *, on_page=None, **options):
            rows = self.records["commits"]
            if on_page:
                offset = options.get("page_offset", 0)
                for index in range(2):
                    on_page(PageObservation(
                        page_index=offset + index + 1,
                        pages_fetched=offset + index + 1,
                        observed_items=len(rows),
                        page_cap=2,
                        has_next=True,
                        duration_ms=0.1,
                        records=rows,
                        raw_body=json.dumps(rows),
                        request_url=f"https://api.github.com/repos/example/project/commits?page={offset + index + 1}",
                        next_url=f"https://api.github.com/repos/example/project/commits?page={offset + index + 2}",
                        http_status=200,
                    ))
            return PaginatedResult([], ["[]", "[]"], False, 2, len(rows), True, http_calls=2)

    execute_task(factory, task_id, PageLimitedGitHub(default_github.repository))

    with factory() as session:
        task = session.get(CollectionTask, task_id)
        checkpoint = session.scalar(select(CollectionCheckpoint).where(CollectionCheckpoint.repository_id == 123, CollectionCheckpoint.module == "commits"))
    assert task.status == "queued"
    assert task.resume_after is not None
    assert task.message == "历史回填已保存检查点，稍后让出队列并继续"
    assert checkpoint is not None
    assert checkpoint.status == "budget_exhausted"
    assert checkpoint.pages_fetched == 2
    assert checkpoint.next_url.endswith("page=3")


def test_raw_archive_rejects_paths_outside_configured_root(tmp_path, monkeypatch):
    root = tmp_path / "raw"
    root.mkdir()
    monkeypatch.setattr("backend.app.pipeline.raw_archive.get_settings", lambda: type("Settings", (), {"raw_data_path": root})())

    with pytest.raises(ValueError, match="escapes configured raw data directory"):
        archive_json(123, "task-id", "../../../../outside", {"data": "value"})
    assert not (tmp_path / "outside.json.gz").exists()


def test_scheduler_queues_overlapped_incremental_sync_and_recalculates_from_deduplicated_store(backend_client, monkeypatch):
    client, factory, default_github = backend_client
    _create_repository(client)
    monkeypatch.setattr("backend.app.worker.executor.archive_json", lambda _repository_id, task_id, kind, _value: f"test/{task_id}/{kind}.json.gz")
    from backend.app.worker.scheduler import enqueue_due_incremental_syncs

    assert enqueue_due_incremental_syncs() == 0
    baseline_task_id = _queue_task(factory, "deep")
    execute_task(factory, baseline_task_id, WorkerGitHub(default_github.repository))
    assert enqueue_due_incremental_syncs() == 1

    with factory() as session:
        incremental = session.scalar(select(CollectionTask).where(CollectionTask.scope_kind == "incremental"))
        scope = json.loads(incremental.scope_json)
        incremental_task_id = incremental.task_id
        claimed = claim_next_task(session, "incremental-test-worker", 60)
        assert claimed and claimed.task_id == incremental_task_id

    assert scope["overlap_days"] == 7
    assert scope["analysis_window_start"] < scope["analysis_window_end"]
    github = WorkerGitHub(default_github.repository)
    github.max_pages = None
    event_time = iso_z(utc_now() - timedelta(hours=6))
    github.records["commits"].append({"sha": "b" * 40, "commit": {"committer": {"date": event_time}}})
    github.records["issues"].append({"id": 4, "created_at": event_time, "closed_at": event_time})
    github.records["pulls"].append({"id": 5, "created_at": event_time, "merged_at": event_time})
    github.records["releases"].append({"id": 6, "published_at": event_time})
    execute_task(factory, incremental_task_id, github)

    with factory() as session:
        task = session.get(CollectionTask, incremental_task_id)
        run = session.scalar(select(RepositoryInsightRun).where(RepositoryInsightRun.repository_id == 123).order_by(RepositoryInsightRun.analyzed_at.desc()).limit(1))
        activity = session.scalar(select(ActivityWindow).where(ActivityWindow.repository_id == 123).order_by(ActivityWindow.collected_at.desc()).limit(1))
        event_count = session.scalar(select(func.count()).select_from(RepositoryActivityEvent).where(RepositoryActivityEvent.repository_id == 123))
        event_rows = session.scalars(select(RepositoryActivityEvent).where(RepositoryActivityEvent.repository_id == 123)).all()
        result = json.loads(run.result_json)

    assert task.status == "succeeded"
    assert event_count == 8, [(row.event_type, row.source_item_id, row.event_at) for row in event_rows]
    assert result["sources"]["commits"]["query"]["since"] == scope["window_start"]
    assert result["sources"]["commits"]["calculation_basis"] == "local_unique_event_store"
    assert result["observed_counts"] == {
        "commits_count": 2,
        "issues_opened_count": 2,
        "issues_closed_count": 2,
        "pulls_opened_count": 2,
        "pulls_merged_count": 2,
        "releases_count": 2,
    }
    assert set(result["source_task_ids"]) == {baseline_task_id, incremental_task_id}
    assert len(result["source_archive_paths"]) == 2
    assert activity.commits_count == 2 and activity.issues_closed_count == 2 and activity.releases_count == 2

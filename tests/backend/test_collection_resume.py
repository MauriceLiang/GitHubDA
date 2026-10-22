import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.core.clock import iso_z, utc_now
from backend.app.integrations.github.client import PageObservation, PaginatedResult
from backend.app.persistence.models import CollectionTask
from backend.app.pipeline.collection_archive import read_page, write_page
from backend.app.worker.collection import collect_deep


HEADERS = {"X-Internal-Api-Key": "test-internal-key"}


class ResumableGitHub:
    max_pages = None

    def __init__(self):
        self.commit_calls = 0
        self.resume_urls = []

    def list_commits_detailed(self, _full_name, _since, _until, *, on_page=None, **options):
        self.commit_calls += 1
        self.resume_urls.append(options.get("resume_url"))
        page_offset = options.get("page_offset", 0)
        records_offset = options.get("records_offset", 0)
        rows = [{"sha": ("a" if self.commit_calls == 1 else "b") * 40, "commit": {"committer": {"date": iso_z(utc_now() - timedelta(days=1))}}}]
        has_next = self.commit_calls == 1
        if on_page:
            on_page(PageObservation(
                page_index=page_offset + 1,
                pages_fetched=page_offset + 1,
                observed_items=records_offset + len(rows),
                page_cap=None,
                has_next=has_next,
                duration_ms=1,
                records=rows,
                raw_body=json.dumps(rows),
                request_url=f"https://api.github.com/repos/example/project/commits?page={page_offset + 1}",
                next_url="https://api.github.com/repos/example/project/commits?page=2" if has_next else None,
                http_status=200,
            ))
        if has_next:
            return PaginatedResult([], [], False, 1, 1, True, error_code="GITHUB_RATE_LIMITED", error_message="limited", error_status_code=429, error_details={"retry_after_seconds": 30})
        return PaginatedResult([], [], True, 1, 1, False)

    def _empty(self, _full_name, *args, **kwargs):
        return PaginatedResult([], [], True, 0, 0, False)

    list_issues_detailed = _empty
    list_pulls_detailed = _empty
    list_releases_detailed = _empty


def test_window_collection_resumes_from_last_saved_page_without_duplicate_records(backend_client):
    client, factory, _default_github = backend_client
    response = client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS)
    repository_id = response.json()["data"]["repository_id"]
    now = utc_now().replace(microsecond=0)
    start, end = now - timedelta(days=90), now
    task = CollectionTask(
        task_id=str(uuid4()),
        repository_id=repository_id,
        depth="deep",
        scope_kind="window",
        created_at=now,
        status="running",
    )
    with factory() as session:
        session.add(task)
        session.commit()

    github = ResumableGitHub()
    first, first_coverage, resume_after = collect_deep(github, "example/project", start, end, task, None, factory)
    assert first_coverage == "partial"
    assert resume_after is not None
    assert first["sources"]["commits"]["page_count"] == 1
    assert first["sources"]["commits"]["coverage"] == "deferred"

    second, second_coverage, second_resume_after = collect_deep(github, "example/project", start, end, task, None, factory)
    assert second_coverage == "complete"
    assert second_resume_after is None
    assert github.resume_urls == [None, "https://api.github.com/repos/example/project/commits?page=2"]
    assert [record["source_item_id"] for record in second["events"]["commits"]] == ["a" * 40, "b" * 40]
    assert second["commits_count"] == 2


def test_invalid_event_records_reduce_module_coverage(backend_client):
    client, factory, _default_github = backend_client
    response = client.post("/api/v1/library/repositories", json={"full_name": "example/invalid-events", "auto_analyze": False}, headers=HEADERS)
    repository_id = response.json()["data"]["repository_id"]
    now = utc_now().replace(microsecond=0)
    task = CollectionTask(task_id=str(uuid4()), repository_id=repository_id, depth="deep", scope_kind="window", status="running", created_at=now)
    with factory() as session:
        session.add(task)
        session.commit()

    class InvalidCommitGitHub(ResumableGitHub):
        def list_commits_detailed(self, _full_name, _since, _until, *, on_page=None, **_options):
            rows = [{"sha": "not-a-valid-sha", "commit": {"committer": {"date": iso_z(now - timedelta(days=1))}}}]
            if on_page:
                on_page(PageObservation(1, 1, 1, None, False, 1, rows, json.dumps(rows), "https://api.github.com/repos/example/project/commits", None, 200))
            return PaginatedResult([], [], True, 1, 1, False)

    result, coverage, _resume_after = collect_deep(InvalidCommitGitHub(), "example/project", now - timedelta(days=90), now, task, None, factory)

    assert coverage == "partial"
    assert result["coverage_by_module"]["commits_count"] == "partial"
    assert result["sources"]["commits"]["rejected_records"] == 1
    assert result["commits_count"] is None


def test_collected_page_requires_matching_sha256(backend_client):
    _client, _factory, _github = backend_client
    stored_path, _digest = write_page(123, "commits", "a" * 64, 1, [{"sha": "b" * 40}], '[{"sha":"' + "b" * 40 + '"}]', "https://api.github.com/repos/example/project/commits", 200)
    assert read_page(stored_path)["record_count"] == 1
    Path(stored_path + ".sha256").unlink()
    with pytest.raises(ValueError, match="checksum is missing"):
        read_page(stored_path)

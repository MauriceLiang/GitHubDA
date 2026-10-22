import gzip
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from backend.app.analytics.insights import calculate_insights
from backend.app.core.clock import iso_z
from backend.app.persistence.models import RepositoryActivityEvent, RepositoryInsightRun
from backend.app.pipeline.event_normalizer import normalize_events
from backend.app.pipeline.raw_archive import read_archive
from backend.app.services.insights import persist_insights

START = datetime(2026, 8, 17)
END = START + timedelta(weeks=8)
HEADERS = {"X-Internal-Api-Key": "test-internal-key"}


def fixture():
    commits = []
    for week, n in enumerate([5, 5, 10, 10, 10, 15, 14, 20]):
        for i in range(n):
            commits.append({"sha": f"{week * 100 + i:040x}", "commit": {"committer": {"date": iso_z(START + timedelta(weeks=week, hours=1))}}})
    issues = [{"id": i + 1, "created_at": iso_z(START), "closed_at": iso_z(START + timedelta(hours=h))} for i, h in enumerate([1, 3, 7, 9, 20, 40, 50, 80, 100, 120])]
    pulls = [{"id": i + 100, "created_at": iso_z(START), "merged_at": iso_z(START + timedelta(hours=h))} for i, h in enumerate([2, 4, 6, 8, 10])]
    return {"commits": commits, "issues": issues, "pulls": pulls, "releases": [{"id": i + 200, "published_at": iso_z(START + timedelta(days=d)), "draft": False, "prerelease": False} for i, d in enumerate([1, 11, 31])]}


def compute(rows=None, partial=None):
    raw = rows or fixture()
    events = {key: normalize_events(key, values)[0] for key, values in raw.items()}
    sources = {key: {"coverage": "partial" if key == partial else "complete"} for key in raw}
    return calculate_insights(events, sources, START, END)


def test_weekly_commits_deduplicate_and_exact_four_week_change():
    raw = fixture()
    raw["commits"].append(raw["commits"][0])
    value = compute(raw)["commit_activity"]
    assert [p["value"] for p in value["weekly"]] == [5, 5, 10, 10, 10, 15, 14, 20]
    assert value["previous_4w"] == 30
    assert value["recent_4w"] == 59
    assert value["delta"] == 29
    assert value["change_rate_pct"] == pytest.approx(96.6666667)


def test_zero_baseline_and_incomplete_coverage_are_not_growth():
    raw = fixture()
    raw["commits"] = [r for r in raw["commits"] if r["commit"]["committer"]["date"] >= iso_z(START + timedelta(weeks=4))]
    value = compute(raw)["commit_activity"]
    assert value["previous_4w"] == 0 and value["change_rate_pct"] is None
    partial = compute(partial="commits")
    assert partial["commit_activity"]["recent_4w"] is None
    assert all(p["value"] is None for p in partial["commit_activity"]["weekly"])
    assert partial["issue_resolution"]["quality"]["status"] == "ready"


def test_duration_threshold_invalid_dates_and_pr_filter():
    raw = fixture()
    raw["issues"] = raw["issues"][:4] + [{"id": 66, "created_at": None, "closed_at": iso_z(START + timedelta(hours=5))}, {"id": 67, "created_at": iso_z(END), "closed_at": iso_z(START)}, {"id": 68, "created_at": iso_z(START), "closed_at": None}, {"id": 69, "pull_request": {}, "created_at": iso_z(START), "closed_at": iso_z(END)}]
    issue = compute(raw)["issue_resolution"]
    assert issue["median_hours"] == 5
    assert issue["quality"]["valid_samples"] == 4
    assert issue["p75_hours"] is issue["p90_hours"] is None
    assert issue["excluded_invalid_duration"] == 2
    raw["pulls"] = raw["pulls"][:3] + [{"id": 999, "created_at": iso_z(START), "closed_at": iso_z(END)}]
    assert compute(raw)["pr_merges"]["median_hours"] == 4


def test_quantiles_release_interval_and_utc_boundaries():
    result = compute()
    issue = result["issue_resolution"]
    assert issue["p75_hours"] == 72.5 and issue["p90_hours"] == 102
    assert sum(x["count"] for x in issue["histogram"]) == 10
    assert result["release_cadence"]["median_interval_days"] == 15
    raw = fixture()
    raw["releases"] = raw["releases"][:1]
    assert compute(raw)["release_cadence"]["median_interval_days"] is None
    raw["commits"] = [{"sha": f"{i:040x}", "commit": {"committer": {"date": d}}} for i, d in enumerate(["2026-08-23T23:59:59Z", "2026-08-24T00:00:00Z", iso_z(END)])]
    assert [p["value"] for p in compute(raw)["commit_activity"]["weekly"]][:2] == [1, 1]
    events, counts = normalize_events("commits", [{"sha": "../invalid", "commit": {}}, {"sha": "a" * 40, "commit": {"committer": {"date": "invalid"}}}])
    assert counts["rejected_records"] == counts["invalid_event_times"] == 1


def test_import_replay_idempotency_versions_api_and_csv(backend_client):
    client, factory, _ = backend_client
    client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS)
    missing = client.get("/api/v1/repositories/123/insights", headers=HEADERS).json()["data"]
    assert missing["status"] == "missing" and not missing["insights"]
    assert client.get("/api/v1/repositories/123/insights").status_code == 401
    sources = {key: {"coverage": "complete", "collected_at": iso_z(END)} for key in fixture()}
    with factory() as session:
        a = persist_insights(session, 123, "source-task", fixture(), sources, START, END, ["123/activity.json.gz"])
        b = persist_insights(session, 123, "source-task", fixture(), sources, START, END, ["123/activity.json.gz"])
        assert a["run_id"] == b["run_id"]
        persist_insights(session, 123, "source-task", fixture(), sources, START, END, [], version="insights-v2")
        session.commit()
        assert session.scalar(select(func.count()).select_from(RepositoryActivityEvent)) == 107
        assert session.scalar(select(func.count()).select_from(RepositoryInsightRun)) == 2
    unavailable_response = client.get("/api/v1/repositories/123/insights?window_days=180", headers=HEADERS)
    assert unavailable_response.status_code == 200, unavailable_response.text
    unavailable = unavailable_response.json()["data"]
    assert unavailable["window_available"] is False
    assert unavailable["available_window_days"] == 56
    assert unavailable["insights"] == {}
    thirty_response = client.get("/api/v1/repositories/123/insights?window_days=30", headers=HEADERS)
    assert thirty_response.status_code == 200, thirty_response.text
    thirty_day = thirty_response.json()["data"]
    assert thirty_day["window_available"] is True
    assert thirty_day["requested_window_days"] == 30
    assert thirty_day["window_start"] == iso_z(END - timedelta(days=30))
    response = client.get("/api/v1/repositories/123/insights", headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["meta"]["request_id"]
    assert data["data"]["metric_version"] == "insights-v1"
    series = client.get("/api/v1/repositories/123/insights/series?metric=commits_weekly&window_days=30", headers=HEADERS).json()["data"]
    first_complete = next(point for point in series["points"] if point["complete_week"])
    assert first_complete["value"] == 10
    assert client.get("/api/v1/repositories/123/insights/quality?window_days=30", headers=HEADERS).status_code == 200
    exported = client.get("/api/v1/repositories/123/insights/export.csv?window_days=30", headers=HEADERS)
    assert exported.status_code == 200 and "insights-v1" in exported.text and "window_start" in exported.text


def test_insights_recompute_selected_window_and_keep_release_window_fixed(backend_client):
    client, factory, _ = backend_client
    client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS)
    sources = {key: {"coverage": "complete", "collected_at": iso_z(END)} for key in fixture()}
    with factory() as session:
        persist_insights(session, 123, "window-task", fixture(), sources, END - timedelta(days=180), END, [])
        session.commit()

    results = {}
    for days in (30, 90, 180):
        response = client.get(f"/api/v1/repositories/123/insights?window_days={days}", headers=HEADERS)
        assert response.status_code == 200, response.text
        results[days] = response.json()["data"]
    commit_totals = {}
    for days, result in results.items():
        assert result["window_available"] is True
        assert result["requested_window_days"] == days
        assert result["window_start"] == iso_z(END - timedelta(days=days))
        assert result["window_end"] == iso_z(END)
        commits = result["insights"]["commit_activity"]
        commit_totals[days] = sum(
            point["value"] for point in commits["weekly"]
            if point["complete_week"] and point["quality"] == "ready" and point["value"] is not None
        )
        assert results[days]["insights"]["release_cadence"]["window_start"] == iso_z(END - timedelta(days=365))
    default_window = client.get("/api/v1/repositories/123/insights", headers=HEADERS).json()["data"]
    assert default_window["requested_window_days"] == 90
    assert default_window["window_start"] == iso_z(END - timedelta(days=90))
    assert results[30]["insights"]["issue_resolution"]["quality"]["valid_samples"] == 0
    assert results[90]["insights"]["issue_resolution"]["quality"]["valid_samples"] == 10
    assert commit_totals == {30: 59, 90: 89, 180: 89}
    assert client.get("/api/v1/repositories/123/insights?window_days=60", headers=HEADERS).status_code == 422


def test_closed_issue_records_search_pagination_and_safe_csv(backend_client, monkeypatch, tmp_path):
    from backend.app.pipeline.raw_archive import archive_json

    client, factory, fake_github = backend_client
    client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS)
    raw = fixture()
    for index, item in enumerate(raw["issues"]):
        item["number"] = 100 + index
        item["title"] = f"Bug item {index}" if index < 4 else "=1+1"
        item["body"] = "private body must not be exposed"
        item["comments"] = 2 if index == 3 else 0
    raw["issues"].append({"id": 9001, "number": 999, "title": "Pull request masquerading as Issue", "pull_request": {"url": "hidden"}, "created_at": iso_z(START), "closed_at": iso_z(START + timedelta(days=1))})
    root = tmp_path / "raw"
    root.mkdir()
    monkeypatch.setattr("backend.app.pipeline.raw_archive.get_settings", lambda: type("Settings", (), {"raw_data_path": root})())
    archive_path = archive_json(123, "source-task", "activity", {"issues": [json.dumps(raw["issues"])]})
    sources = {key: {"coverage": "complete", "collected_at": iso_z(END)} for key in raw}
    with factory() as session:
        persist_insights(session, 123, "source-task", raw, sources, START, END, [archive_path])
        session.commit()

    response = client.get("/api/v1/repositories/123/issues?page=1&per_page=2&search=BUG", headers=HEADERS)
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["meta"]["pagination"] == {"page": 1, "per_page": 2, "total": 4, "has_next": True}
    assert page["data"]["available"] is True
    assert page["data"]["coverage"]["state"] == "complete"
    assert [item["number"] for item in page["data"]["items"]] == [103, 102]
    assert page["data"]["items"][0]["url"] == "https://github.com/example/project/issues/103"
    assert "body" not in page["data"]["items"][0]
    second = client.get("/api/v1/repositories/123/issues?page=2&per_page=2&search=bug", headers=HEADERS).json()["data"]
    assert [item["number"] for item in second["items"]] == [101, 100]

    detail_response = client.get("/api/v1/repositories/123/issues/103", headers=HEADERS)
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()["data"]
    assert detail["title"] == "Bug item 3"
    assert detail["body"] == "private body must not be exposed"
    assert detail["comments_count"] == 2
    assert client.get("/api/v1/repositories/123/issues/999", headers=HEADERS).status_code == 404

    issue_requests = []
    comment_requests = []
    fake_github.get_issue_detail = lambda full_name, number: (
        issue_requests.append((full_name, number)) or {
            "number": number,
            "title": "Current GitHub title",
            "body": "## Online issue body",
            "state": "closed",
            "user": {"login": "issue-author"},
            "labels": [{"name": "bug"}],
            "created_at": iso_z(START),
            "closed_at": iso_z(START + timedelta(hours=4)),
            "updated_at": iso_z(START + timedelta(hours=5)),
            "html_url": "https://github.com/example/project/issues/103",
            "comments": 2,
        }
    )
    fake_github.list_issue_comments_detailed = lambda full_name, number: (
        comment_requests.append((full_name, number)) or SimpleNamespace(
            items=[{"user": {"login": "maintainer"}, "body": "Fixed in latest release.", "created_at": iso_z(START + timedelta(hours=6))}],
            error_code=None,
            has_next=False,
        )
    )
    online = client.get("/api/v1/repositories/123/issues/103/online", headers=HEADERS)
    assert online.status_code == 200, online.text
    online_data = online.json()["data"]
    assert online_data["title"] == "Current GitHub title"
    assert online_data["body"] == "## Online issue body"
    assert online_data["author"] == "issue-author"
    assert online_data["labels"] == ["bug"]
    assert online_data["comments_count"] == 2
    assert online_data["comments"][0]["body"] == "Fixed in latest release."
    assert online_data["comments_complete"] is True
    assert online_data["comments_error"] is None
    assert issue_requests == [("example/project", 103)]
    assert comment_requests == [("example/project", 103)]

    exported = client.get("/api/v1/repositories/123/issues/export.csv", headers=HEADERS)
    assert exported.status_code == 200 and "issue_number,title,created_at" in exported.text
    assert "private body" not in exported.text
    assert "'=1+1" in exported.text


def test_pull_request_records_include_unmerged_details_and_fetch_online_only_on_request(backend_client, monkeypatch, tmp_path):
    from backend.app.pipeline.raw_archive import archive_json

    client, factory, fake_github = backend_client
    client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers=HEADERS)
    pulls = [
        {
            "id": 501, "number": 30, "title": "feat: add search", "body": "Local merged description",
            "created_at": iso_z(START + timedelta(days=1)), "closed_at": iso_z(START + timedelta(days=3)),
            "merged_at": iso_z(START + timedelta(days=3)), "comments": 0, "draft": False,
        },
        {
            "id": 502, "number": 31, "title": "=1+1", "body": "Local closed description",
            "created_at": iso_z(START + timedelta(days=1)), "closed_at": iso_z(START + timedelta(days=6)),
            "merged_at": None, "comments": 1, "draft": True,
        },
        {
            "id": 503, "number": 32, "title": "outside collection window", "body": "",
            "created_at": iso_z(START + timedelta(days=1)), "closed_at": iso_z(END + timedelta(hours=1)),
            "merged_at": None, "comments": 0, "draft": False,
        },
    ]
    root = tmp_path / "raw"
    root.mkdir()
    monkeypatch.setattr("backend.app.pipeline.raw_archive.get_settings", lambda: type("Settings", (), {"raw_data_path": root})())
    archive_path = archive_json(123, "pull-detail-task", "activity", {"pulls": [json.dumps(pulls)]})
    raw = {"commits": [], "issues": [], "pulls": pulls, "releases": []}
    sources = {key: {"coverage": "complete", "collected_at": iso_z(END)} for key in raw}
    with factory() as session:
        persist_insights(session, 123, "pull-detail-task", raw, sources, START, END, [archive_path])
        session.commit()

    list_response = client.get("/api/v1/repositories/123/pull-requests?page=1&per_page=1", headers=HEADERS)
    assert list_response.status_code == 200, list_response.text
    page = list_response.json()["data"]
    assert page["available"] is True
    assert page["coverage"]["state"] == "complete"
    assert page["total"] == 2
    assert page["items"][0]["number"] == 31
    assert page["items"][0]["state"] == "closed"
    assert page["items"][0]["draft"] is True
    assert client.get("/api/v1/repositories/123/pull-requests?search=ADD%20SEARCH", headers=HEADERS).json()["data"]["items"][0]["number"] == 30
    merged = client.get("/api/v1/repositories/123/pull-requests/30", headers=HEADERS)
    assert merged.status_code == 200, merged.text
    assert merged.json()["data"]["body"] == "Local merged description"
    assert merged.json()["data"]["duration_days"] == 2.0
    closed = client.get("/api/v1/repositories/123/pull-requests/31", headers=HEADERS)
    assert closed.json()["data"]["state"] == "closed"
    assert closed.json()["data"]["merged_at"] is None
    assert client.get("/api/v1/repositories/123/pull-requests/999", headers=HEADERS).status_code == 404

    pull_requests = []
    comments_requests = []
    fake_github.get_pull_request_detail = lambda full_name, number: (
        pull_requests.append((full_name, number)) or {
            "number": number, "title": "Latest GitHub title", "body": "## Online PR body", "state": "closed",
            "merged_at": None, "user": {"login": "pr-author"}, "labels": [{"name": "bug"}],
            "created_at": iso_z(START), "closed_at": iso_z(START + timedelta(days=6)),
            "updated_at": iso_z(START + timedelta(days=7)), "html_url": "https://github.com/example/project/pull/31", "comments": 1,
        }
    )
    fake_github.list_pull_request_comments_detailed = lambda full_name, number: (
        comments_requests.append((full_name, number)) or SimpleNamespace(
            items=[{"user": {"login": "reviewer"}, "body": "Please add a regression case.", "created_at": iso_z(START + timedelta(days=4))}],
            error_code=None,
            has_next=False,
        )
    )
    assert pull_requests == comments_requests == []
    online = client.get("/api/v1/repositories/123/pull-requests/31/online", headers=HEADERS)
    assert online.status_code == 200, online.text
    online_data = online.json()["data"]
    assert online_data["title"] == "Latest GitHub title"
    assert online_data["state"] == "closed"
    assert online_data["author"] == "pr-author"
    assert online_data["labels"] == ["bug"]
    assert online_data["comments"][0]["body"] == "Please add a regression case."
    assert online_data["comments_complete"] is True
    assert pull_requests == [("example/project", 31)]
    assert comments_requests == [("example/project", 31)]

    exported = client.get("/api/v1/repositories/123/pull-requests/export.csv", headers=HEADERS)
    assert exported.status_code == 200 and "pull_number,title,state" in exported.text
    assert "'=1+1" in exported.text


def test_unknown_api_route_does_not_fall_through_to_spa(backend_client):
    client, _, _ = backend_client

    response = client.get("/api/v1/route-that-does-not-exist", headers=HEADERS)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_archive_safety(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.app.pipeline.raw_archive.get_settings", lambda: type("Settings", (), {"raw_data_path": tmp_path})())
    target = tmp_path / "test.json.gz"
    with gzip.open(target, "wb") as f:
        f.write(b'{"value": "' + b'a' * 1000 + b'"}')
    with pytest.raises(ValueError, match="size limit"):
        read_archive("test.json.gz", max_bytes=100)
    with pytest.raises(ValueError, match="escapes"):
        read_archive("../test.json.gz")
    with gzip.open(target, "wb") as f:
        f.write(b'not json')
    with pytest.raises(ValueError, match="invalid"):
        read_archive("test.json.gz")


def test_worker_event_pipeline_and_safe_archive_replay(backend_client, monkeypatch, tmp_path):
    from backend.app.pipeline.archive_replay import replay_activity
    from backend.app.pipeline.raw_archive import archive_json
    from backend.app.persistence.models import ActivityWindow, CollectionTask
    from backend.app.worker.executor import execute_task
    from tests.backend.test_worker_deep import WorkerGitHub, _queue_task, _create_repository
    client, factory, github = backend_client
    _create_repository(client)
    root = tmp_path / 'raw'
    root.mkdir()
    monkeypatch.setattr('backend.app.pipeline.raw_archive.get_settings', lambda: type('Settings', (), {'raw_data_path': root})())
    worker = WorkerGitHub(github.repository)
    from backend.app.core.clock import utc_now
    # Dates aligned with the worker's live window, real IDs and committer timestamps.
    stamp = iso_z(utc_now() - timedelta(days=2))
    worker.records = {'commits': [{'sha': 'a' * 40, 'commit': {'committer': {'date': stamp}}}], 'issues': [{'id': 1, 'created_at': stamp, 'closed_at': stamp}], 'pulls': [{'id': 2, 'created_at': stamp, 'merged_at': stamp}], 'releases': [{'id': 3, 'published_at': stamp}]}
    original = worker._list
    def list_page(module):
        records, complete, _pages = original(module)
        return records, complete, [json.dumps(records)]
    worker._list = list_page
    task_id = _queue_task(factory, 'deep')
    execute_task(factory, task_id, worker)
    with factory() as session:
        assert session.get(CollectionTask, task_id).status == 'succeeded'
        run = session.scalar(select(RepositoryInsightRun))
        result = json.loads(run.result_json)
        assert result['insights']['issue_resolution']['median_hours'] == 0
        assert result['sources']['commits']['page_count'] == 1
        assert session.scalar(select(func.count()).select_from(RepositoryActivityEvent)) == 4
        preview = replay_activity(session, 123)
        assert preview['records']['commits'] == 1
        again = replay_activity(session, 123, apply=True)
        assert again['run_id'] == run.run_id
        assert session.scalar(select(func.count()).select_from(RepositoryInsightRun)) == 1
        # Tampered archive fails before touching any existing results.
        activity = session.scalar(select(ActivityWindow))
        activity.source_archive_path = '../outside.json.gz'
        session.flush()
        with pytest.raises(ValueError):
            replay_activity(session, 123, apply=True)
        assert session.scalar(select(func.count()).select_from(RepositoryInsightRun)) == 1


def test_fixture_contract_matches_expected_output():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    raw = json.loads((root / 'tests/fixtures/insights/events.json').read_text())
    expected = json.loads((root / 'tests/fixtures/insights/insights-expected.json').read_text())
    events = {key: normalize_events(key, values)[0] for key, values in raw['events'].items()}
    actual = calculate_insights(events, expected['sources'], START, END)
    assert actual == expected['insights']


def test_comparison_windows_and_research_dataset_isolation(backend_client):
    from backend.app.persistence.models import Repository, Dataset, DatasetRepository
    client, factory, _ = backend_client
    client.post('/api/v1/library/repositories', json={'full_name': 'example/project', 'auto_analyze': False}, headers=HEADERS)
    with factory() as session:
        session.add(Repository(repository_id=124, full_name='example/second', html_url='https://github.com/example/second'))
        session.add(Dataset(dataset_id='insight-research', name='test research', type='research'))
        session.flush()
        session.add(DatasetRepository(dataset_id='insight-research', repository_id=123))
        sources = {key: {'coverage': 'complete'} for key in fixture()}
        persist_insights(session, 123, 'one', fixture(), sources, START, END, [])
        persist_insights(session, 124, 'two', fixture(), sources, START + timedelta(days=1), END + timedelta(days=1), [])
        session.commit()
    response = client.post('/api/v1/comparisons/insights', json={'repository_ids': [123, 124], 'depth': 'deep'}, headers=HEADERS)
    assert response.status_code == 200, response.text
    value = response.json()['data']
    assert value['common_complete_weeks'] == 7
    assert value['repositories'][0]['metrics']['issue_median_hours']['value'] is None
    comparison_weeks = [point['start'] for point in value['repositories'][0]['weekly_commits']]
    assert len(comparison_weeks) == value['common_complete_weeks']
    assert comparison_weeks == [point['start'] for point in value['repositories'][1]['weekly_commits']]
    assert all(point['quality'] == 'ready' for repo in value['repositories'] for point in repo['weekly_commits'])
    assert len(value['warnings']) >= 2
    research = client.get('/api/v1/research/insights?dataset_id=insight-research', headers=HEADERS).json()['data']
    assert research['sample_size'] == 1
    assert [r['repository_id'] for r in research['rows']] == [123]
    assert research['summary']['issue_median_hours']['count'] == 1
    assert research['correlation']['coefficient'] is None
    assert client.get('/api/v1/research/insights?dataset_id=library', headers=HEADERS).status_code == 422


def test_rejects_short_windows_and_filters_formal_release_policy():
    raw = fixture()
    events = {k: normalize_events(k, v)[0] for k, v in raw.items()}
    sources = {k: {'coverage': 'complete'} for k in raw}
    result = calculate_insights(events, sources, START + timedelta(weeks=2), END)
    assert result['commit_activity']['recent_4w'] is None
    assert len([p for p in result['commit_activity']['weekly'] if p['quality'] == 'ready']) == 6
    raw['releases'][0]['draft'] = True
    raw['releases'][1]['prerelease'] = True
    result = compute(raw)['release_cadence']
    assert result['release_count'] == 1 and result['prerelease_count'] == 1
    assert result['median_interval_days'] is None


def test_validation_partial_is_reflected_in_worker_task_without_losing_ready_modules(backend_client, monkeypatch):
    from backend.app.persistence.models import CollectionTask
    from backend.app.worker.executor import execute_task
    from tests.backend.test_worker_deep import WorkerGitHub, _queue_task, _create_repository, _patch_archives
    client, factory, github = backend_client
    _create_repository(client)
    _patch_archives(monkeypatch)
    worker = WorkerGitHub(github.repository)
    worker.records['commits'] = [{'sha': '../invalid'}]
    task_id = _queue_task(factory, 'deep')
    execute_task(factory, task_id, worker)
    with factory() as session:
        assert session.get(CollectionTask, task_id).status == 'partial'
        result = json.loads(session.scalar(select(RepositoryInsightRun)).result_json)
        assert result['insights']['commit_activity']['quality']['status'] == 'partial'
        assert result['insights']['issue_resolution']['quality']['status'] == 'ready'


def test_research_chart_fixture_is_derived_from_fixed_events():
    import copy
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root/'tests/fixtures/insights/research-chart-scenarios.json').read_text())
    base = json.loads((root/'tests/fixtures/insights/events.json').read_text())
    expected = json.loads((root/'tests/fixtures/insights/research-charts-expected.json').read_text())
    for i, factor in enumerate(config['duration_multipliers']):
        raw = copy.deepcopy(base['events'])
        for module, field in [('issues','closed_at'),('pulls','merged_at')]:
            for event in raw[module]:
                created = datetime.fromisoformat(event['created_at'].replace('Z',''))
                terminal = datetime.fromisoformat(event[field].replace('Z',''))
                event[field] = iso_z(created+(terminal-created)*factor)
        result = compute(raw)
        assert expected['rows'][i]['values']['issue_median_hours'] == result['issue_resolution']['median_hours']
        assert expected['rows'][i]['values']['pr_median_hours'] == result['pr_merges']['median_hours']
    assert len(expected['rows']) == 24
    assert expected['summary']['issue_median_hours']['count'] == 5
    assert expected['summary']['issue_median_hours']['missing_count'] == 19


def test_commit_activity_archive_search_pagination_week_and_author_privacy(backend_client, monkeypatch, tmp_path):
    from backend.app.pipeline.raw_archive import archive_json

    client, factory, _ = backend_client
    client.post('/api/v1/library/repositories', json={'full_name': 'example/project', 'auto_analyze': False}, headers=HEADERS)
    raw = fixture()
    raw['commits'] = [
        {
            'sha': f'{i:040x}',
            'commit': {
                'committer': {'date': iso_z(START + timedelta(days=day, hours=hour))},
                'author': {'name': author_name, 'email': f'{author_name.lower()}@private.test'},
                'message': message,
            },
            'author': author,
        }
        for i, day, hour, author_name, message, author in [
            (1001, 0, 3, 'Alice Dev', 'fix: handle missing state\nDetails stay private', {'id': 1, 'login': 'alice', 'type': 'User'}),
            (1002, 0, 9, 'Automation', 'chore: refresh generated files', {'id': 2, 'login': 'sync[bot]', 'type': 'Bot'}),
            (1003, 8, 11, 'Unlinked Name', 'docs: explain setup', None),
        ]
    ]
    root = tmp_path / 'raw'
    root.mkdir()
    monkeypatch.setattr('backend.app.pipeline.raw_archive.get_settings', lambda: type('Settings', (), {'raw_data_path': root})())
    archive_path = archive_json(123, 'commit-detail-task', 'activity', {'commits': [json.dumps(raw['commits'])]})
    sources = {key: {'coverage': 'partial' if key == 'commits' else 'complete'} for key in raw}
    with factory() as session:
        persist_insights(session, 123, 'commit-detail-task', raw, sources, START, END, [archive_path])
        session.commit()

    response = client.get('/api/v1/repositories/123/commits?page=1&per_page=2', headers=HEADERS)
    assert response.status_code == 200, response.text
    page = response.json()['data']
    assert page['available'] is True
    assert page['coverage']['state'] == 'partial'
    assert page['commit_count'] == 3 and page['author_count'] == 3
    assert page['total'] == 3 and len(page['items']) == 2
    assert [item['sha'] for item in page['items']] == [f'{1003:040x}', f'{1002:040x}']
    assert page['daily_counts'] == [
        {'date': '2026-08-17', 'count': 2},
        {'date': '2026-08-25', 'count': 1},
    ]
    authors = {item['author']: item for item in page['authors']}
    assert authors['sync[bot]']['is_bot'] is True
    assert authors['Unlinked Name']['anonymous'] is True
    assert 'alice.dev@private.test' not in response.text

    second_page = client.get('/api/v1/repositories/123/commits?page=2&per_page=2', headers=HEADERS).json()['data']
    assert [item['author'] for item in second_page['items']] == ['alice']
    searched = client.get('/api/v1/repositories/123/commits?search=missing', headers=HEADERS).json()['data']
    assert searched['total'] == 1 and searched['items'][0]['author'] == 'alice'
    selected_week = client.get('/api/v1/repositories/123/commits?week_start=2026-08-17', headers=HEADERS).json()['data']
    assert selected_week['commit_count'] == 2
    assert {item['sha'] for item in selected_week['items']} == {f'{1001:040x}', f'{1002:040x}'}

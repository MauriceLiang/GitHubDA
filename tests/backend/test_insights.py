import gzip
import json
from datetime import datetime, timedelta

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
    response = client.get("/api/v1/repositories/123/insights", headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["meta"]["request_id"]
    assert data["data"]["metric_version"] == "insights-v1"
    series = client.get("/api/v1/repositories/123/insights/series?metric=commits_weekly", headers=HEADERS).json()["data"]
    assert series["points"][0]["value"] == 5
    assert client.get("/api/v1/repositories/123/insights/quality", headers=HEADERS).status_code == 200
    exported = client.get("/api/v1/repositories/123/insights/export.csv", headers=HEADERS)
    assert exported.status_code == 200 and "insights-v1" in exported.text and "window_start" in exported.text


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

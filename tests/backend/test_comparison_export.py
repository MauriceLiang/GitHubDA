import json
import csv
import io
from datetime import datetime, timedelta

import pytest

from backend.app.core.clock import iso_z, utc_now
from backend.app.persistence.models import AnalysisResult, Repository, RepositorySnapshot


HEADERS = {"X-Internal-Api-Key": "test-internal-key"}


def seed_activity_comparison(factory, *, second_days=180, second_offset=0, partial=False):
    from backend.app.services.insights import persist_insights

    end = datetime(2026, 10, 19)
    with factory() as session:
        for repository_id in (321, 322):
            session.add(Repository(repository_id=repository_id, full_name=f"fixture/{repository_id}", html_url=f"https://github.com/fixture/{repository_id}", language="Python"))
        session.flush()
        for repository_id in (321, 322):
            stop = end - timedelta(days=second_offset if repository_id == 322 else 0)
            raw = {
                "commits": [{"sha": f"{days:040x}", "commit": {"committer": {"date": iso_z(stop - timedelta(days=days))}}} for days in (5, 15, 45, 80, 120, 170)],
                "issues": [{"id": index + 1, "created_at": iso_z(stop - timedelta(days=days + index + 2)), "closed_at": iso_z(stop - timedelta(days=days + index))} for index, days in enumerate([2] * 10 + [45] * 10)],
                "pulls": [{"id": index + 1, "created_at": iso_z(stop - timedelta(days=days + index + 1)), "merged_at": iso_z(stop - timedelta(days=days + index))} for index, days in enumerate([2] * 10 + [45] * 10)],
                "releases": [{"id": index + 1, "published_at": iso_z(stop - timedelta(days=days)), "draft": False, "prerelease": False} for index, days in enumerate((10, 50, 200))],
            }
            sources = {module: {"coverage": "budget_exhausted" if partial and module == "commits" else "complete"} for module in raw}
            persist_insights(session, repository_id, f"source-{repository_id}", raw, sources, stop - timedelta(days=second_days if repository_id == 322 else 180), stop, [])
        session.commit()


@pytest.mark.parametrize("days", [30, 90, 180])
@pytest.mark.parametrize("mode", ["same_period", "individual_periods"])
def test_activity_comparison_and_csv_follow_selected_window(backend_client, days, mode):
    client, factory, _ = backend_client
    seed_activity_comparison(factory)
    response = client.post("/api/v1/comparisons/insights", json={"repository_ids": [321, 322], "mode": mode, "window_days": days}, headers=HEADERS)
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["requested_window_days"] == days
    expected_count = {30: 2, 90: 4, 180: 6}[days]
    for row in result["repositories"]:
        assert row["window_available"] is True
        assert row["window_reason"] is None
        assert row["window_start"] == iso_z(datetime(2026, 10, 19) - timedelta(days=days))
        assert sum(point["value"] for point in row["weekly_commits"]) == expected_count
        assert all(point["complete_week"] and point["quality"] == "ready" for point in row["weekly_commits"])
        assert row["metrics"]["issue_median_hours"]["valid_samples"] == (10 if days == 30 else 20)
    exported = client.get(f"/api/v1/exports/comparison.csv?repository_ids=321,322&mode={mode}&window_days={days}", headers=HEADERS)
    assert exported.status_code == 200, exported.text
    rows = list(csv.DictReader(io.StringIO(exported.text.lstrip('\ufeff'))))
    for api, exported_row in zip(result["repositories"], rows):
        assert exported_row["所选窗口天数"] == str(days)
        assert exported_row["窗口开始"] == api["window_start"]
        assert exported_row["窗口结束"] == api["window_end"]
        assert exported_row["窗口可用"] == "True"
        assert float(exported_row["每周提交均值"]) == api["metrics"]["commits_weekly_mean"]["value"]
        assert float(exported_row["Issue 关闭耗时 P50（天）"]) == round(api["metrics"]["issue_median_hours"]["value"] / 24, 1)


def test_comparison_preserves_missing_windows_and_does_not_invent_zero(backend_client):
    client, factory, _ = backend_client
    seed_activity_comparison(factory, second_days=90)
    for mode in ("same_period", "individual_periods"):
        result = client.post("/api/v1/comparisons/insights", json={"repository_ids": [321, 322], "mode": mode, "window_days": 180}, headers=HEADERS).json()["data"]
        assert len(result["repositories"]) == 2
        missing = result["repositories"][1]
        assert missing["window_available"] is False and "180" in missing["window_reason"]
        assert missing["weekly_commits"] == []
        assert all(metric["value"] is None for metric in missing["metrics"].values())
        if mode == "same_period":
            assert result["common_complete_weeks"] == 0
            assert result["repositories"][0]["metrics"]["commits_weekly_mean"]["value"] is None
        else:
            assert result["repositories"][0]["metrics"]["commits_weekly_mean"]["value"] is not None
        exported = client.get(f"/api/v1/exports/comparison.csv?repository_ids=321,322&mode={mode}&window_days=180", headers=HEADERS)
        row = list(csv.DictReader(io.StringIO(exported.text.lstrip('\ufeff'))))[1]
        assert row["窗口可用"] == "False" and row["范围缺失原因"] == missing["window_reason"]
        assert row["每周提交均值"] == row["Issue 关闭耗时 P50（天）"] == ""


def test_activity_comparison_defaults_to_90_days(backend_client):
    client, factory, _ = backend_client
    seed_activity_comparison(factory)
    body = {"repository_ids": [321, 322]}
    default = client.post("/api/v1/comparisons/insights", json=body, headers=HEADERS).json()["data"]
    explicit = client.post("/api/v1/comparisons/insights", json={**body, "window_days": 90}, headers=HEADERS).json()["data"]
    assert default == explicit
    exported = client.get("/api/v1/exports/comparison.csv?repository_ids=321,322&mode=same_period", headers=HEADERS)
    assert exported.status_code == 200
    assert all(row["所选窗口天数"] == "90" for row in csv.DictReader(io.StringIO(exported.text.lstrip('\ufeff'))))


def test_comparison_distinguishes_modes_and_preserves_partial_quality(backend_client):
    client, factory, _ = backend_client
    seed_activity_comparison(factory, second_offset=7)
    body = {"repository_ids": [321, 322], "window_days": 30}
    same = client.post("/api/v1/comparisons/insights", json={**body, "mode": "same_period"}, headers=HEADERS).json()["data"]
    individual = client.post("/api/v1/comparisons/insights", json={**body, "mode": "individual_periods"}, headers=HEADERS).json()["data"]
    assert same["common_complete_weeks"] == 3
    assert all(row["metrics"]["issue_median_hours"]["value"] is None for row in same["repositories"])
    assert all(row["metrics"]["issue_median_hours"]["value"] is not None for row in individual["repositories"])
    assert all(len(row["weekly_commits"]) == 4 for row in individual["repositories"])
    assert same["repositories"][0]["weekly_commits"] != individual["repositories"][0]["weekly_commits"]
    from sqlalchemy import select
    from backend.app.persistence.models import RepositoryInsightRun
    with factory() as session:
        run = session.scalar(select(RepositoryInsightRun).where(RepositoryInsightRun.repository_id == 321))
        sources = json.loads(run.module_coverage_json)
        sources["commits"]["coverage"] = "budget_exhausted"
        run.module_coverage_json = json.dumps(sources)
        session.commit()
    partial = client.post("/api/v1/comparisons/insights", json={**body, "mode": "individual_periods"}, headers=HEADERS).json()["data"]["repositories"][0]
    assert partial["window_available"] is True
    assert partial["metrics"]["commits_weekly_mean"]["quality"] == "partial"
    assert partial["metrics"]["commits_weekly_mean"]["value"] is None


def test_comparison_returns_available_metrics_and_csv_export(backend_client):
    client, factory, _github = backend_client
    collected_at = utc_now()
    with factory() as session:
        cases = ((321, "fixture/one", 120, 7), (322, "fixture/two", 250, 11))
        for repository_id, full_name, stars, _commits in cases:
            session.add(Repository(repository_id=repository_id, full_name=full_name, html_url=f"https://github.com/{full_name}", language="Python"))
            session.add(RepositorySnapshot(repository_id=repository_id, collected_at=collected_at, stars=stars, forks=12, source_http_status=200, valid=True))
        session.flush()
        for repository_id, _full_name, _stars, commits in cases:
            session.add(AnalysisResult(repository_id=repository_id, analysis_kind="basic", metric_version="metrics-v1", source_collected_at=collected_at, calculated_at=collected_at, coverage="complete", metrics_json=json.dumps({"age_days": 100, "days_since_push": 2, "commits_90d": commits, "issues_closed_90d": 3, "pr_merged_90d": 4, "release_count_365d": 1}), limitations_json="[]", valid_sample_size=1))
        session.commit()

    comparison = client.post("/api/v1/comparisons", json={"repository_ids": [321, 322], "depth": "basic"}, headers=HEADERS)
    assert comparison.status_code == 200
    first_metrics = comparison.json()["data"]["repositories"][0]["metrics"]
    assert first_metrics["commits_90d"] == 7
    assert first_metrics["issues_closed_90d"] == 3
    assert first_metrics["pr_merged_90d"] == 4
    assert first_metrics["release_count_365d"] == 1

    exported = client.get("/api/v1/exports/comparison.csv?repository_ids=321,322", headers=HEADERS)
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "近 90 天提交" in exported.text
    assert "fixture/one" in exported.text
    assert ",7,3,4,1,complete" in exported.text

    activity_collected_at = collected_at - timedelta(days=2)
    window_start = activity_collected_at - timedelta(days=90)
    with factory() as session:
        session.add(AnalysisResult(repository_id=321, analysis_kind="deep", metric_version="metrics-v1", source_collected_at=activity_collected_at, calculated_at=activity_collected_at, window_start=window_start, window_end=activity_collected_at, coverage="partial", metrics_json='{"commits_90d":42}', limitations_json="[]", valid_sample_size=1))
        session.commit()
    deep = client.post("/api/v1/comparisons", json={"repository_ids": [321, 322], "depth": "deep"}, headers=HEADERS)
    assert deep.status_code == 200
    rows = deep.json()["data"]["repositories"]
    assert rows[0]["source"] == {"profile_collected_at": iso_z(collected_at), "analysis_collected_at": iso_z(activity_collected_at), "analysis_depth": "deep", "window_start": iso_z(window_start), "window_end": iso_z(activity_collected_at)}
    assert rows[1]["source"]["analysis_depth"] == "basic"
    assert rows[1]["coverage"] == "partial"


def test_comparison_csv_rejects_duplicate_or_malformed_ids(backend_client):
    client, _factory, _github = backend_client
    duplicate = client.get("/api/v1/exports/comparison.csv?repository_ids=123,123", headers=HEADERS)
    malformed = client.get("/api/v1/exports/comparison.csv?repository_ids=one,two", headers=HEADERS)
    assert duplicate.status_code == malformed.status_code == 422
    assert duplicate.json()["error"]["code"] == "VALIDATION_ERROR"

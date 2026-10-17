import json
from datetime import timedelta

from backend.app.core.clock import iso_z, utc_now
from backend.app.persistence.models import AnalysisResult, Repository, RepositorySnapshot


HEADERS = {"X-Internal-Api-Key": "test-internal-key"}


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

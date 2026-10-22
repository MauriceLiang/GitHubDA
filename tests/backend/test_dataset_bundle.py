import json
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.app.services.dataset_bundle import _coverage_record


def test_coverage_record_maps_metric_coverage_to_collection_modules():
    window = SimpleNamespace(
        repository_id=123,
        window_start=datetime(2026, 7, 24, tzinfo=UTC),
        window_end=datetime(2026, 10, 22, tzinfo=UTC),
        collected_at=datetime(2026, 10, 22, 8, tzinfo=UTC),
        commits_count=12,
        issues_opened_count=3,
        issues_closed_count=2,
        pulls_opened_count=4,
        pulls_merged_count=1,
        releases_count=1,
        coverage="complete",
        details_json=json.dumps({
            "coverage_by_module": {
                "commits_count": "complete",
                "issues_closed_count": "partial",
                "pulls_merged_count": "deferred",
                "releases_count": "complete",
            }
        }),
    )

    record = _coverage_record(window)

    assert record["modules"] == {
        "commits": "complete",
        "issues": "partial",
        "pulls": "deferred",
        "releases": "complete",
    }

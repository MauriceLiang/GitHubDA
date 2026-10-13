from datetime import datetime

from backend.app.analytics.metrics import basic_metrics, spearman_summary
from backend.app.services.analytics import _csv_safe


def test_basic_metrics_keep_unknown_values_null_and_use_collection_time():
    result = basic_metrics(15, None, datetime(2026, 1, 11), datetime(2026, 1, 1), None)
    assert result["age_days"] == 10.0
    assert result["forks"] is None
    assert result["days_since_push"] is None
    assert result["commits_90d"] is None


def test_spearman_does_not_report_constant_or_small_samples():
    small = spearman_summary([1, 2, 3], [3, 2, 1])
    constant = spearman_summary([1] * 10, list(range(10)))
    assert small["coefficient"] is None and small["p_value"] is None
    assert constant["coefficient"] is None and constant["p_value"] is None
    assert small["note"] and constant["note"]


def test_csv_formula_prefix_is_escaped():
    assert _csv_safe("=SUM(A1:A4)") == "'=SUM(A1:A4)"
    assert _csv_safe("  @SUM(A1)") == "'  @SUM(A1)"
    assert _csv_safe("normal text") == "normal text"

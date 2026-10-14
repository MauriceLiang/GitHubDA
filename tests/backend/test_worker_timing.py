import json

from backend.app.worker import telemetry
from backend.app.worker.telemetry import (
    log_module_timing,
    log_page_progress,
    log_task_timing,
    request_metrics_delta,
)


def test_worker_timing_logs_structured_counts_without_response_content(monkeypatch):
    messages = []
    monkeypatch.setattr(telemetry.logger, "info", messages.append)
    log_page_progress(
        task_id="task-1",
        repository_id=42,
        module="issues",
        page_index=2,
        pages_fetched=2,
        observed_items=120,
        duration_ms=8.5,
        has_next=True,
    )
    log_module_timing(
        task_id="task-1",
        repository_id=42,
        module="issues",
        http_calls=2,
        pages_fetched=2,
        observed_items=120,
        duration_ms=18.0,
        coverage="partial",
        error_code="GITHUB_TIMEOUT",
        timeout_count=1,
    )
    log_task_timing(
        task_id="task-1",
        repository_id=42,
        depth="deep",
        status="partial",
        duration_ms=45.0,
        metrics={
            "http_calls": 3,
            "rate_limited_count": 0,
            "timeout_count": 1,
            "duration_ms": 28.0,
        },
    )

    events = [json.loads(message) for message in messages]
    assert [event["event"] for event in events] == [
        "github_page_fetched",
        "github_module_finished",
        "collection_task_finished",
    ]
    assert events[0]["pages_fetched"] == 2
    assert events[1]["error_code"] == "GITHUB_TIMEOUT"
    assert events[2]["http_calls"] == 3
    assert events[2]["timeout_count"] == 1
    assert all("response" not in event and "token" not in event for event in events)


def test_request_metrics_delta_reports_task_local_counts():
    assert request_metrics_delta(
        {"http_calls": 6, "rate_limited_count": 1, "timeout_count": 2, "duration_ms": 31.0},
        {"http_calls": 2, "rate_limited_count": 0, "timeout_count": 1, "duration_ms": 10.0},
    ) == {
        "http_calls": 4,
        "rate_limited_count": 1,
        "timeout_count": 1,
        "duration_ms": 21.0,
    }

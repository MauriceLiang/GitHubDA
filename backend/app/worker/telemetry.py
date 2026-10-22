import json
import logging
from collections.abc import Mapping
from typing import Any


logger = logging.getLogger("repovantage.worker.telemetry")


def request_metrics_delta(
    current: Mapping[str, int | float],
    previous: Mapping[str, int | float],
) -> dict[str, int | float]:
    return {
        name: current.get(name, 0) - previous.get(name, 0)
        for name in ("http_calls", "rate_limited_count", "timeout_count", "duration_ms")
    }


def log_page_progress(
    *,
    task_id: str,
    repository_id: int,
    module: str,
    page_index: int,
    pages_fetched: int,
    observed_items: int,
    duration_ms: float,
    has_next: bool,
) -> None:
    _log(
        "github_page_fetched",
        task_id=task_id,
        repository_id=repository_id,
        module=module,
        page_index=page_index,
        pages_fetched=pages_fetched,
        observed_items=observed_items,
        duration_ms=round(max(0.0, duration_ms), 3),
        has_next=has_next,
    )


def log_module_timing(
    *,
    task_id: str,
    repository_id: int,
    module: str,
    http_calls: int,
    pages_fetched: int,
    observed_items: int,
    duration_ms: float,
    coverage: str,
    error_code: str | None,
    rate_limited_count: int = 0,
    timeout_count: int = 0,
) -> None:
    _log(
        "github_module_finished",
        task_id=task_id,
        repository_id=repository_id,
        module=module,
        http_calls=http_calls,
        pages_fetched=pages_fetched,
        observed_items=observed_items,
        duration_ms=round(max(0.0, duration_ms), 3),
        coverage=coverage,
        error_code=error_code,
        rate_limited_count=rate_limited_count,
        timeout_count=timeout_count,
    )


def log_task_timing(
    *,
    task_id: str,
    repository_id: int | None,
    depth: str | None,
    status: str,
    duration_ms: float,
    metrics: Mapping[str, int | float],
) -> None:
    _log(
        "collection_task_finished",
        task_id=task_id,
        repository_id=repository_id,
        depth=depth,
        status=status,
        duration_ms=round(max(0.0, duration_ms), 3),
        http_calls=int(metrics.get("http_calls", 0)),
        rate_limited_count=int(metrics.get("rate_limited_count", 0)),
        timeout_count=int(metrics.get("timeout_count", 0)),
        request_duration_ms=round(max(0.0, metrics.get("duration_ms", 0)), 3),
    )


def _log(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

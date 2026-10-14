"""Shared error and source metadata helpers."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from frontend.api.errors import APIError
from frontend.api.models import RefreshTaskData, SourceMetadata


def render_api_error(error: APIError) -> None:
    st.error(error.user_message)


def render_provenance(metadata: SourceMetadata | None) -> None:
    if metadata is None:
        st.caption("尚无可用采集元信息。")
        return

    collected_at = _format_datetime(metadata.collected_at)
    scope = "—" if metadata.dataset_id is None else metadata.dataset_id
    sample = "未知" if metadata.sample_size is None else str(metadata.sample_size)
    window = "未提供"
    if metadata.window_start and metadata.window_end:
        window = f"{_format_datetime(metadata.window_start)} 至 {_format_datetime(metadata.window_end)}"
    st.caption(
        f"来源：{metadata.source} · 采集：{collected_at} · 样本 n={sample} · 数据集：{scope} · "
        f"窗口：{window} · 覆盖：{metadata.coverage}"
    )
    for note in metadata.notes:
        st.caption(note)


def display_value(value: int | float | str | None, *, missing: str = "—") -> int | float | str:
    return missing if value is None else value


def format_task_attempt(attempt: int) -> str:
    return "尚未执行（0 次尝试）" if attempt == 0 else f"{attempt} 次"


def format_refresh_result(result: RefreshTaskData, operation: str) -> str:
    status_labels = {
        "queued": "排队中",
        "running": "运行中",
        "succeeded": "已结束",
        "partial": "部分完成",
    }
    status = status_labels[result.status]
    if result.reused and result.status in {"succeeded", "partial"}:
        return f"{operation}最近结果可复用（{status}），无需重新采集。"
    if result.reused:
        return f"已复用{status}的{operation}任务：{result.task_id}"
    return f"{operation}任务已{status}：{result.task_id}"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "尚未采集"
    return value.astimezone().strftime("%Y-%m-%d %H:%M %Z") if value.tzinfo else value.isoformat()

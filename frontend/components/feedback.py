"""Shared empty, error, and provenance presentation helpers."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from frontend.api.errors import APIError
from frontend.api.models import SourceMetadata


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
        f"来源：{metadata.source} · 采集：{collected_at} · 样本 n={sample} · 数据集：{scope} · 窗口：{window} · 覆盖：{metadata.coverage}"
    )
    for note in metadata.notes:
        st.caption(note)


def display_value(value: int | float | str | None, *, missing: str = "未知") -> int | float | str:
    return missing if value is None else value


def _format_datetime(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M %Z") if value.tzinfo else value.isoformat()

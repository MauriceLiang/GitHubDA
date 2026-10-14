"""Shared data-source note for pages that will display API results."""

from __future__ import annotations

import streamlit as st


def render_provenance_note(*, mock_mode: bool) -> None:
    if mock_mode:
        st.caption("数据来源：frontend/fixtures 中的本地契约样例；这些数字仅用于显式演示。")
    else:
        st.caption("数据来源、采集时间和统计范围将在各页面随 API 结果展示。")

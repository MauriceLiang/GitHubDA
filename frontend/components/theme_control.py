"""Display preferences and explicit Mock scenarios."""

from __future__ import annotations

import streamlit as st

from frontend.api.mock_client import MockAPIClient
from frontend.state.keys import STATE_KEYS


def render_chart_theme_control() -> None:
    st.selectbox(
        "图表配色",
        options=("dark", "light"),
        format_func=lambda value: "Dark" if value == "dark" else "Light",
        key=STATE_KEYS["chart_theme"],
        help="仅控制 Plotly 图表；请与 Streamlit Settings 中的外观主题保持一致。",
    )


def render_mock_scenario_control(client: object, *, mock_mode: bool) -> None:
    if not mock_mode or not isinstance(client, MockAPIClient):
        return
    scenario = st.selectbox(
        "演示场景",
        options=("normal", "empty_library", "github_limited", "worker_stale", "invalid_url", "task_progress", "task_partial", "task_failed"),
        format_func={
            "normal": "标准样例",
            "empty_library": "空分析库",
            "github_limited": "GitHub 限流",
            "worker_stale": "Worker 心跳过期",
            "invalid_url": "无效仓库地址",
            "task_progress": "模块进度 v2",
            "task_partial": "部分完成任务",
            "task_failed": "任务失败与重试",
        }.get,
        key=STATE_KEYS["mock_scenario"],
    )
    client.activate_demo_scenario(scenario)

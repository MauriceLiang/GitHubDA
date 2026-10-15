"""Primary homepage input for starting repository analysis."""

from __future__ import annotations

import streamlit as st

from frontend.state.keys import STATE_KEYS


def render_repository_input() -> tuple[str, bool]:
    with st.form("dashboard-repository-analysis"):
        repository_input, analyze = st.columns([5, 1])
        value = repository_input.text_input(
            "GitHub 仓库",
            key=STATE_KEYS["home_repository_input"],
            placeholder="粘贴 https://github.com/owner/repo 或输入 owner/repo",
        )
        submitted = analyze.form_submit_button(
            "分析仓库",
            key="dashboard-analyze-repository",
            type="primary",
            width="stretch",
        )
    return value, submitted

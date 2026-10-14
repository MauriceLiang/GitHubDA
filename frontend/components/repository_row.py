"""Dense repository metadata shared by discovery and library rows."""

from __future__ import annotations

import textwrap
from datetime import datetime

import streamlit as st

from frontend.components.status_indicator import render_status


def render_repository_row(
    *,
    full_name: str,
    description: str | None,
    language: str | None,
    stars: int | None,
    forks: int | None,
    html_url: str | None = None,
    analysis_status: str | None = None,
    data_status: str | None = None,
    collected_at: datetime | None = None,
) -> None:
    st.markdown(f"**{full_name}**")
    if description:
        st.write(textwrap.shorten(description, width=180, placeholder="…"))
    details = [
        f"语言：{language or '未知'}",
        f"Stars：{stars:,}" if stars is not None else "Stars：未采集",
        f"Forks：{forks:,}" if forks is not None else "Forks：未采集",
    ]
    if collected_at:
        details.append(f"最近采集：{collected_at.astimezone().strftime('%Y-%m-%d %H:%M') if collected_at.tzinfo else collected_at.isoformat()}")
    st.caption(" · ".join(details))
    if analysis_status or data_status:
        render_status(analysis_status, data_status)
    if html_url:
        st.link_button("在 GitHub 打开", html_url)

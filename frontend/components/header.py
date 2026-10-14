"""Global app header and service status area."""

from __future__ import annotations

import streamlit as st

from frontend.api.client import APIClient
from frontend.api.errors import APIError


def render_header() -> None:
    st.caption("GitHub Developer Workspace")
    st.title("GitHub 开源项目分析台")
    st.caption("用于发现、比较和研究开源项目的本地开发者工作台。")


def render_service_status(client: APIClient, *, mock_mode: bool) -> None:
    if mock_mode:
        st.warning("演示模式：当前只回放本地契约 fixture，不代表实时 GitHub 数据。")
    elif not client.api_key_configured:
        st.error("服务端尚未配置 INTERNAL_API_KEY；受保护的 API 请求不可用。")

    try:
        client.health()
    except APIError as error:
        st.warning(error.user_message)
        return

    if mock_mode:
        st.caption("Fixture API 已就绪。")
    else:
        st.success("后端 API 可用。")

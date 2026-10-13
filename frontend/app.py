"""GitHubDA Streamlit app entry point."""

from __future__ import annotations

import streamlit as st

from frontend.api.factory import get_api_client
from frontend.components.header import render_header, render_service_status
from frontend.components.navigation import build_navigation
from frontend.components.provenance import render_provenance_note
from frontend.components.theme_control import render_chart_theme_control, render_mock_scenario_control
from frontend.state.keys import initialize_state


def main() -> None:
    st.set_page_config(
        page_title="GitHub 开源项目分析台",
        page_icon=":material/query_stats:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    initialize_state()
    page = st.navigation(build_navigation(), position="sidebar", expanded=True)

    try:
        client, mock_mode = get_api_client()
    except ValueError:
        render_header()
        st.error("MOCK_MODE 配置无效，请设置为 true 或 false。")
        render_provenance_note(mock_mode=False)
        return

    render_header()
    render_service_status(client, mock_mode=mock_mode)
    with st.sidebar:
        st.divider()
        render_chart_theme_control()
        render_mock_scenario_control(client, mock_mode=mock_mode)
    page.run()
    st.divider()
    render_provenance_note(mock_mode=mock_mode)
    st.caption("数据统计范围、有效样本和采集元信息以 API 返回为准。")


if __name__ == "__main__":
    main()

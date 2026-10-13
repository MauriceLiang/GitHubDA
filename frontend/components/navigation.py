"""Native Streamlit navigation for the routes defined in the frontend handout."""

from __future__ import annotations

from pathlib import Path

import streamlit as st


_PAGES_DIR = Path(__file__).resolve().parents[1] / "pages"


def build_navigation() -> dict[str, list[st.Page]]:
    return {
        "分析工作台": [
            st.Page(_PAGES_DIR / "dashboard.py", title="数据概览", url_path="dashboard", default=True),
            st.Page(_PAGES_DIR / "explore.py", title="仓库发现", url_path="explore"),
            st.Page(_PAGES_DIR / "library.py", title="我的分析库", url_path="library"),
            st.Page(_PAGES_DIR / "comparison.py", title="项目对比", url_path="comparison"),
            st.Page(
                _PAGES_DIR / "repository.py",
                title="仓库详情",
                url_path="repository",
                visibility="hidden",
            ),
        ],
        "研究与运维": [
            st.Page(_PAGES_DIR / "research.py", title="数据研究", url_path="research"),
            st.Page(_PAGES_DIR / "operations.py", title="数据与任务", url_path="operations"),
        ],
    }

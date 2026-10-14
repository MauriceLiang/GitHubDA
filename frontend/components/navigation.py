"""Native Streamlit navigation for the product's user-facing routes."""

from __future__ import annotations

from pathlib import Path

import streamlit as st


_PAGES_DIR = Path(__file__).resolve().parents[1] / "pages"


def build_navigation() -> dict[str, list[st.Page]]:
    return {
        "工作区": [
            st.Page(_PAGES_DIR / "dashboard.py", title="工作台", url_path="dashboard", default=True),
            st.Page(_PAGES_DIR / "explore.py", title="发现仓库", url_path="explore"),
            st.Page(_PAGES_DIR / "library.py", title="我的分析库", url_path="library"),
            st.Page(_PAGES_DIR / "comparison.py", title="仓库对比", url_path="comparison"),
            st.Page(
                _PAGES_DIR / "repository.py",
                title="仓库详情",
                url_path="repository",
                visibility="hidden",
            ),
        ],
        "高级功能": [
            st.Page(_PAGES_DIR / "research.py", title="研究分析", url_path="research"),
            st.Page(_PAGES_DIR / "operations.py", title="任务中心", url_path="operations"),
        ],
    }

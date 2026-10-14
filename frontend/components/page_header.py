"""Compact, consistent page titles for the main content area."""

from __future__ import annotations

import streamlit as st


def render_page_header(title: str, description: str | None = None) -> None:
    st.header(title)
    if description:
        st.caption(description)

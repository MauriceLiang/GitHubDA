"""Collapsed provenance and limitation details."""

from __future__ import annotations

import streamlit as st

from frontend.api.models import SourceMetadata
from frontend.components.feedback import render_provenance


def render_metadata_panel(
    metadata: SourceMetadata | None,
    *,
    title: str = "数据来源与范围",
    limitations: list[str] | None = None,
) -> None:
    with st.expander(title):
        render_provenance(metadata)
        for limitation in limitations or []:
            st.caption(f"局限：{limitation}")

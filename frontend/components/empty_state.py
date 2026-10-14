"""Small, actionable empty states."""

from __future__ import annotations

import streamlit as st


def render_empty_state(
    title: str,
    description: str,
    *,
    action_label: str | None = None,
    target: str | None = None,
    steps: tuple[str, ...] = (),
) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.write(description)
        if steps:
            st.caption(" → ".join(steps))
        if action_label and target:
            st.page_link(target, label=action_label)

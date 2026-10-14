"""Consistent, explicit confirmation for recoverable actions."""

from __future__ import annotations

import streamlit as st


def render_confirm_action(
    title: str,
    description: str,
    *,
    confirm_key: str,
    cancel_key: str,
    confirm_label: str = "确认移除",
) -> bool | None:
    st.warning(f"{title}？{description}")
    confirm, cancel, _ = st.columns([1, 1, 5])
    if confirm.button(confirm_label, key=confirm_key, type="primary"):
        return True
    if cancel.button("取消", key=cancel_key):
        return False
    return None

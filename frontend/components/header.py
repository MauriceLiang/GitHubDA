"""Compact app branding and cached service health."""

from __future__ import annotations

import time

import streamlit as st

from frontend.api.client import APIClient
from frontend.api.errors import APIError
from frontend.state.keys import STATE_KEYS


_HEALTH_TTL_SECONDS = 20


def render_header() -> None:
    st.caption("GitHubDA · GitHub Developer Workspace")


def render_service_status(client: APIClient, *, mock_mode: bool) -> None:
    now = time.monotonic()
    checked_at = st.session_state[STATE_KEYS["service_status_checked_at"]]
    if now - checked_at >= _HEALTH_TTL_SECONDS:
        if not client.api_key_configured and not mock_mode:
            kind, message = "error", "尚未配置 INTERNAL_API_KEY"
        else:
            try:
                client.health()
            except APIError as error:
                kind, message = "error", error.user_message
            else:
                kind, message = "ok", ""
        st.session_state[STATE_KEYS["service_status_checked_at"]] = now
        st.session_state[STATE_KEYS["service_status_kind"]] = kind
        st.session_state[STATE_KEYS["service_status_message"]] = message

    kind = st.session_state[STATE_KEYS["service_status_kind"]]
    with st.sidebar:
        st.divider()
        if mock_mode:
            st.caption("服务 · 本地 Mock fixture")
        elif kind == "ok":
            st.caption("API · 正常")
        else:
            st.warning(st.session_state[STATE_KEYS["service_status_message"]])

"""Cached API client selected from server-side frontend settings."""

from __future__ import annotations

import streamlit as st

from frontend.api.client import APIClient, APISettings
from frontend.api.mock_client import MockAPIClient
from frontend.state.keys import STATE_KEYS


@st.cache_resource
def _get_real_api_client() -> APIClient:
    settings = APISettings.from_environment()
    return APIClient(base_url=settings.api_base_url, internal_api_key=settings.internal_api_key)


def get_api_client() -> tuple[APIClient, bool]:
    settings = APISettings.from_environment()
    if not settings.mock_mode:
        return _get_real_api_client(), False

    mock_key = STATE_KEYS["mock_api_client"]
    client = st.session_state.get(mock_key)
    if not isinstance(client, MockAPIClient):
        client = MockAPIClient()
        st.session_state[mock_key] = client
    client.activate_demo_scenario(st.session_state.get(STATE_KEYS["mock_scenario"], "normal"))
    return client, True

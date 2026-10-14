"""Cached API client selected from server-side frontend settings."""

from __future__ import annotations

import streamlit as st

from frontend.api.client import APIClient, APISettings
from frontend.api.mock_client import MockAPIClient


@st.cache_resource
def get_api_client() -> tuple[APIClient, bool]:
    settings = APISettings.from_environment()
    if settings.mock_mode:
        return MockAPIClient(), True
    return APIClient(base_url=settings.api_base_url, internal_api_key=settings.internal_api_key), False

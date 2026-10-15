"""Shared resolve/add/navigation flow for repository analysis entry points."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import streamlit as st

from frontend.api.client import APIClient
from frontend.api.models import RepositoryPreview
from frontend.state.keys import STATE_KEYS


@dataclass(frozen=True)
class RepositoryAnalysisStart:
    repository_id: int
    task_id: str | None


def _submission_key_for(full_name: str) -> str:
    value_key = STATE_KEYS["repository_submission_value"]
    key_key = STATE_KEYS["repository_submission_key"]
    if st.session_state[value_key] != full_name or not st.session_state[key_key]:
        st.session_state[value_key] = full_name
        st.session_state[key_key] = str(uuid4())
    return st.session_state[key_key]


def _clear_submission_key(full_name: str) -> None:
    value_key = STATE_KEYS["repository_submission_value"]
    if st.session_state[value_key] == full_name:
        st.session_state[value_key] = None
        st.session_state[STATE_KEYS["repository_submission_key"]] = None


def start_repository_analysis(client: APIClient, repository: RepositoryPreview) -> RepositoryAnalysisStart:
    if repository.already_in_library:
        _clear_submission_key(repository.full_name)
        return RepositoryAnalysisStart(repository_id=repository.repository_id, task_id=None)

    added = client.add_repository(
        repository.full_name,
        auto_analyze=True,
        depth="basic",
        idempotency_key=_submission_key_for(repository.full_name),
    ).data
    _clear_submission_key(repository.full_name)
    return RepositoryAnalysisStart(repository_id=added.repository_id, task_id=added.task_id)


def open_repository(start: RepositoryAnalysisStart | int, task_id: str | None = None) -> None:
    if isinstance(start, RepositoryAnalysisStart):
        repository_id = start.repository_id
        task_id = start.task_id
    else:
        repository_id = start

    st.session_state[STATE_KEYS["repository_id"]] = repository_id
    st.session_state[STATE_KEYS["task_id"]] = task_id
    st.session_state[STATE_KEYS["task_poll_complete_for"]] = None
    st.session_state[STATE_KEYS["task_poll_error_for"]] = None
    added_ids = st.session_state[STATE_KEYS["added_repository_ids"]]
    if repository_id not in added_ids:
        st.session_state[STATE_KEYS["added_repository_ids"]] = [*added_ids, repository_id]
    st.switch_page("pages/repository.py", query_params={"repository_id": str(repository_id)})

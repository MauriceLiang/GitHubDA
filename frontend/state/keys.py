"""Namespaced session-state keys reserved for frontend interactions."""

from __future__ import annotations

import streamlit as st


STATE_KEYS = {
    "scope": "githubda.scope",
    "dataset_id": "githubda.dataset_id",
    "search_query": "githubda.search_query",
    "search_results": "githubda.search_results",
    "added_repository_ids": "githubda.added_repository_ids",
    "search_page": "githubda.search_page",
    "search_language": "githubda.search_language",
    "search_stars_min": "githubda.search_stars_min",
    "search_sort": "githubda.search_sort",
    "library_query": "githubda.library_query",
    "library_status": "githubda.library_status",
    "library_sort": "githubda.library_sort",
    "library_order": "githubda.library_order",
    "library_page": "githubda.library_page",
    "selected_repository_ids": "githubda.selected_repository_ids",
    "repository_id": "githubda.repository_id",
    "task_id": "githubda.task_id",
    "pending_delete_repository_id": "githubda.pending_delete_repository_id",
    "chart_theme": "githubda.chart_theme",
    "dashboard_language": "githubda.dashboard_language",
    "research_group_by": "githubda.research_group_by",
    "research_dataset_id": "githubda.research_dataset_id",
    "research_language": "githubda.research_language",
    "comparison_depth": "githubda.comparison_depth",
    "export_language": "githubda.export_language",
    "comparison_result": "githubda.comparison_result",
    "repository_metric": "githubda.repository_metric",
    "task_status_filter": "githubda.task_status_filter",
    "task_repository_filter": "githubda.task_repository_filter",
    "task_page": "githubda.task_page",
    "task_poll_complete_for": "githubda.task_poll_complete_for",
    "task_poll_error_for": "githubda.task_poll_error_for",
    "export_scope": "githubda.export_scope",
    "export_dataset_id": "githubda.export_dataset_id",
    "export_payload": "githubda.export_payload",
    "mock_scenario": "githubda.mock_scenario",
}

_DEFAULTS = {
    "scope": "research",
    "dataset_id": None,
    "search_query": "",
    "search_results": None,
    "added_repository_ids": [],
    "search_page": 1,
    "search_language": "",
    "search_stars_min": 0,
    "search_sort": "best_match",
    "library_query": "",
    "library_status": "",
    "library_sort": "name",
    "library_order": "asc",
    "library_page": 1,
    "selected_repository_ids": [],
    "repository_id": None,
    "task_id": None,
    "pending_delete_repository_id": None,
    "chart_theme": "dark",
    "dashboard_language": "",
    "research_group_by": "language",
    "research_dataset_id": None,
    "research_language": "",
    "comparison_depth": "basic",
    "export_language": "",
    "comparison_result": None,
    "repository_metric": "stars",
    "task_status_filter": "",
    "task_repository_filter": "",
    "task_page": 1,
    "task_poll_complete_for": None,
    "task_poll_error_for": None,
    "export_scope": "research",
    "export_dataset_id": None,
    "export_payload": None,
    "mock_scenario": "normal",
}


def initialize_state() -> None:
    for name, value in _DEFAULTS.items():
        st.session_state.setdefault(STATE_KEYS[name], value)

"""HTTPX-backed mock client that only replays checked-in contract fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qs

import httpx

from frontend.api.client import APIClient


DEFAULT_FIXTURES = {
    "health": "health_ok",
    "system_status": "system_status",
    "search_repositories": "search_ok",
    "resolve_repository": "resolve_ok",
    "add_repository": "add_created",
    "list_library": "library_initial",
    "remove_from_library": "library_removed",
    "repository_detail": "repository_detail",
    "refresh_repository": "refresh_queued",
    "task_detail": "task_running",
    "repository_series": "series_points",
    "list_tasks": "tasks_list",
    "retry_task": "retry_queued",
    "datasets": "datasets_initial",
    "repository_analysis": "analysis_done",
    "overview": "overview_research",
    "research_statistics": "research_statistics",
    "research_data_quality": "research_data_quality",
    "compare": "comparison_partial",
    "export_repositories_csv": "repositories_export",
}

FIXTURE_STATUSES = {
    "add_created": 201,
    "add_existing": 200,
    "refresh_queued": 202,
    "retry_queued": 202,
    "retry_queued_partial": 202,
    "github_limited": 429,
    "resolve_invalid": 400,
}


class MockAPIClient(APIClient):
    """Drop-in client for explicit fixture demos and frontend development."""

    def __init__(
        self,
        *,
        fixture_dir: Path | None = None,
        scenarios: Mapping[str, str] | None = None,
    ) -> None:
        self.fixture_dir = fixture_dir or Path(__file__).resolve().parents[1] / "fixtures"
        self.scenarios = {**DEFAULT_FIXTURES, **(scenarios or {})}
        self._custom_scenarios = set(scenarios or {})
        self._added = False
        self._removed = False
        self._task_detail_calls = 0
        self._task_available = False
        self._collection_complete = False
        self._demo_task_status: str | None = None
        self._retry_started = False
        self._active_demo_scenario = "normal"
        transport = httpx.MockTransport(self._replay_fixture)
        mock_http_client = httpx.Client(transport=transport)
        super().__init__(
            base_url="http://mock.local",
            internal_api_key="fixture-only",
            http_client=mock_http_client,
            owns_http_client=True,
        )

    def activate_demo_scenario(self, scenario: str) -> None:
        if scenario == self._active_demo_scenario:
            return
        self._active_demo_scenario = scenario
        self.scenarios = dict(DEFAULT_FIXTURES)
        self._custom_scenarios = set()
        self._demo_task_status = scenario.removeprefix("task_") if scenario in {"task_failed", "task_partial", "task_progress"} else None
        self._retry_started = False
        self._task_detail_calls = 0
        if scenario == "github_limited":
            self.scenarios["search_repositories"] = "github_limited"
            self._custom_scenarios.add("search_repositories")
        elif scenario == "worker_stale":
            self.scenarios["system_status"] = "system_status_worker_stale"
            self._custom_scenarios.add("system_status")
        elif scenario == "task_failed":
            self.scenarios["list_tasks"] = "tasks_list_failed"
            self._custom_scenarios.add("list_tasks")
        elif scenario == "task_partial":
            self.scenarios["list_tasks"] = "tasks_list_partial"
            self._custom_scenarios.add("list_tasks")
        elif scenario == "invalid_url":
            self.scenarios["resolve_repository"] = "resolve_invalid"
            self._custom_scenarios.add("resolve_repository")
        elif scenario == "empty_library":
            self.scenarios.update(
                list_library="library_empty",
                overview="overview_library_empty",
                list_tasks="tasks_list_empty",
            )
            self._custom_scenarios.update({"list_library", "overview", "list_tasks"})
        elif scenario == "task_progress":
            self.scenarios["list_tasks"] = "tasks_list_progress"
            self._custom_scenarios.add("list_tasks")

    def _replay_fixture(self, request: httpx.Request) -> httpx.Response:
        operation = self._operation_for_request(request)
        fixture_stem = self.scenarios.get(operation or "")
        if operation == "overview" and "overview" not in self._custom_scenarios:
            scope = parse_qs(request.url.query.decode("utf-8")).get("scope", ["research"])[0]
            if scope == "library":
                if self._added and not self._removed:
                    fixture_stem = "overview_library_after_analysis" if self._collection_complete else "overview_library_after_add"
                else:
                    fixture_stem = "overview_library_initial"
        if operation == "add_repository" and operation not in self._custom_scenarios:
            fixture_stem = "add_existing" if self._added and not self._removed else "add_created"
        if operation == "list_library" and operation not in self._custom_scenarios:
            if self._removed:
                fixture_stem = "library_after_remove"
            elif self._added:
                fixture_stem = "library_after_analysis" if self._collection_complete else "library_after_add"
        if operation == "list_tasks" and operation not in self._custom_scenarios:
            if not self._task_available:
                fixture_stem = "tasks_list_empty"
            else:
                fixture_stem = "tasks_list_succeeded" if self._collection_complete else "tasks_list"
        if operation == "datasets" and operation not in self._custom_scenarios and self._added and not self._removed:
            fixture_stem = "datasets_after_add"
        if operation == "task_detail" and operation not in self._custom_scenarios:
            if self._demo_task_status and not self._retry_started:
                fixture_stem = f"task_{self._demo_task_status}"
            elif self._retry_started:
                fixture_stem = "task_retry_running" if self._task_detail_calls == 0 else "task_retry_succeeded"
                if self._task_detail_calls > 0:
                    self._collection_complete = True
            else:
                fixture_stem = "task_running" if self._task_detail_calls == 0 else "task_succeeded"
                if self._task_detail_calls > 0:
                    self._collection_complete = True
            self._task_detail_calls += 1
        if operation == "retry_task" and self._demo_task_status == "partial" and not self._retry_started:
            fixture_stem = "retry_queued_partial"
        if operation in {"repository_detail", "repository_analysis", "repository_series"} and operation not in self._custom_scenarios:
            repository_id = request.url.path.split("/")[4]
            if repository_id == "1362490" and operation == "repository_detail" and self._added and not self._collection_complete:
                fixture_stem = "repository_detail_queued"
            elif repository_id == "1362490" and operation == "repository_analysis":
                depth = parse_qs(request.url.query.decode("utf-8")).get("depth", ["basic"])[0]
                if depth == "deep":
                    if self._demo_task_status == "partial":
                        fixture_stem = "analysis_deep_partial"
                    elif self._demo_task_status == "failed":
                        fixture_stem = "analysis_deep_failed"
                    else:
                        fixture_stem = "analysis_deep_done" if self._collection_complete else "analysis_deep_missing"
                else:
                    fixture_stem = "analysis_missing" if self._added and not self._collection_complete else "analysis_done"
            elif repository_id == "724712" and operation == "repository_series":
                metric = parse_qs(request.url.query.decode("utf-8")).get("metric", ["stars"])[0]
                fixture_stem = f"series_rust_{metric}"
            elif repository_id == "724712" and operation == "repository_detail":
                fixture_stem = "repository_detail_rust"
            elif repository_id == "724712" and operation == "repository_analysis":
                depth = parse_qs(request.url.query.decode("utf-8")).get("depth", ["basic"])[0]
                fixture_stem = "analysis_rust_deep" if depth == "deep" else "analysis_rust"
            elif operation == "repository_series":
                metric = parse_qs(request.url.query.decode("utf-8")).get("metric", ["stars"])[0]
                fixture_stem = "series_points" if metric == "stars" else f"series_points_{metric}"

        if not fixture_stem:
            return self._missing_fixture_response(operation)

        if fixture_stem == "library_removed":
            try:
                manifest = json.loads((self.fixture_dir / "library_removed.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return self._missing_fixture_response(operation)
            if manifest.get("status_code") != 204:
                return self._missing_fixture_response(operation)
            repository_id = request.url.path.rsplit("/", 1)[-1]
            if repository_id == "1362490":
                self._removed = True
                self._added = False
            return httpx.Response(204)

        if fixture_stem == "repositories_export":
            try:
                scope = parse_qs(request.url.query.decode("utf-8")).get("scope", ["library"])[0]
                filename = "repositories_export_research.csv" if scope == "research" else "repositories_export.csv"
                body = (self.fixture_dir / filename).read_bytes()
            except OSError:
                return self._missing_fixture_response(operation)
            return httpx.Response(
                200,
                content=body,
                headers={
                    "content-type": "text/csv; charset=utf-8",
                    "content-disposition": 'attachment; filename="repositories_2026-10-13.csv"',
                },
            )

        fixture_path = self.fixture_dir / f"{fixture_stem}.json"
        try:
            body = json.loads(fixture_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._missing_fixture_response(operation)

        if operation == "list_tasks":
            requested_status = parse_qs(request.url.query.decode("utf-8")).get("status", [None])[0]
            if requested_status:
                body.setdefault("data", {})["items"] = [
                    item for item in body.get("data", {}).get("items", []) if item.get("status") == requested_status
                ]
                pagination = body.get("meta", {}).get("pagination")
                if pagination is not None:
                    pagination["total"] = len(body["data"]["items"])
                    pagination["has_next"] = False
        status = FIXTURE_STATUSES.get(fixture_stem, 200)
        if fixture_stem == "github_limited":
            status = 429
        if operation == "add_repository" and status in {200, 201}:
            self._added = True
            self._removed = False
            self._task_available = True
            self._collection_complete = False
            self._task_detail_calls = 0
        if operation == "refresh_repository" and status == 202:
            self._task_available = True
            self._collection_complete = False
            self._task_detail_calls = 0
        if operation == "retry_task" and status == 202:
            self._retry_started = True
            self._task_available = True
            self._collection_complete = False
            self._task_detail_calls = 0
        return httpx.Response(status, json=body, headers={"content-type": "application/json"})

    @staticmethod
    def _operation_for_request(request: httpx.Request) -> str | None:
        path = request.url.path
        method = request.method
        if method == "GET" and path == "/healthz":
            return "health"
        if method == "GET" and path == "/api/v1/system/status":
            return "system_status"
        if method == "GET" and path == "/api/v1/github/search":
            return "search_repositories"
        if method == "POST" and path == "/api/v1/github/resolve":
            return "resolve_repository"
        if method == "POST" and path == "/api/v1/library/repositories":
            return "add_repository"
        if method == "GET" and path == "/api/v1/library/repositories":
            return "list_library"
        if method == "DELETE" and path.startswith("/api/v1/library/repositories/"):
            return "remove_from_library"
        if method == "GET" and path.startswith("/api/v1/repositories/") and path.count("/") == 4:
            return "repository_detail"
        if method == "POST" and path.startswith("/api/v1/repositories/") and path.endswith("/refresh"):
            return "refresh_repository"
        if method == "GET" and path.startswith("/api/v1/repositories/") and path.endswith("/analysis"):
            return "repository_analysis"
        if method == "GET" and path.startswith("/api/v1/repositories/") and path.endswith("/series"):
            return "repository_series"
        if method == "GET" and path == "/api/v1/tasks":
            return "list_tasks"
        if method == "POST" and path.startswith("/api/v1/tasks/") and path.endswith("/retry"):
            return "retry_task"
        if method == "GET" and path.startswith("/api/v1/tasks/") and path.count("/") == 4:
            return "task_detail"
        if method == "GET" and path == "/api/v1/datasets":
            return "datasets"
        if method == "GET" and path == "/api/v1/overview":
            return "overview"
        if method == "GET" and path == "/api/v1/research/statistics":
            return "research_statistics"
        if method == "GET" and path == "/api/v1/research/data-quality":
            return "research_data_quality"
        if method == "POST" and path == "/api/v1/comparisons":
            return "compare"
        if method == "GET" and path == "/api/v1/exports/repositories.csv":
            return "export_repositories_csv"
        return None

    @staticmethod
    def _missing_fixture_response(operation: str | None) -> httpx.Response:
        body = {
            "error": {
                "code": "MOCK_FIXTURE_MISSING",
                "message": "No local fixture is registered for this API operation.",
                "details": {"operation": operation},
            },
            "request_id": "mock-fixture-missing",
        }
        return httpx.Response(501, json=body, headers={"content-type": "application/json"})

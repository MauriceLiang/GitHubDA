"""The only frontend entry point for FastAPI HTTP requests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import quote

import httpx
from dotenv import dotenv_values
from pydantic import TypeAdapter, ValidationError

from frontend.api.errors import APIError
from frontend.api.models import (
    APIEnvelope,
    AddRepositoryData,
    ComparisonData,
    DataQualityData,
    DatasetListData,
    ErrorEnvelope,
    HealthResponse,
    OverviewData,
    RefreshTaskData,
    RepositoryAnalysisData,
    RepositoryDetailData,
    RepositoryListData,
    RepositoryPreview,
    RepositorySearchData,
    RepositorySeriesData,
    ResearchStatisticsData,
    RetryTaskData,
    SystemStatusData,
    Task,
    TaskListData,
)


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUEST_TIMEOUT = httpx.Timeout(connect=3.0, read=15.0, write=15.0, pool=3.0)

T = TypeVar("T")


@dataclass(frozen=True)
class APISettings:
    api_base_url: str = DEFAULT_API_BASE_URL
    internal_api_key: str | None = None
    mock_mode: bool = False

    @classmethod
    def from_environment(cls) -> "APISettings":
        file_values = dotenv_values(PROJECT_ROOT / ".env")

        def configured(name: str, default: str) -> str:
            if name in os.environ:
                return os.environ[name]
            value = file_values.get(name)
            return default if value is None else value

        raw_mock_mode = configured("MOCK_MODE", "false").strip().lower()
        if raw_mock_mode not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
            raise ValueError("MOCK_MODE must be a boolean value")

        return cls(
            api_base_url=configured("API_BASE_URL", DEFAULT_API_BASE_URL).strip().rstrip("/"),
            internal_api_key=configured("INTERNAL_API_KEY", "").strip() or None,
            mock_mode=raw_mock_mode in {"true", "1", "yes", "on"},
        )


class CSVExport:
    """Raw CSV payload and safe filename returned by the export endpoint."""

    def __init__(self, *, content: bytes, content_type: str, filename: str) -> None:
        self.content = content
        self.content_type = content_type
        self.filename = filename


class APIClient:
    """Typed synchronous client; UI code must not call HTTPX directly."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        internal_api_key: str | None = None,
        http_client: httpx.Client | None = None,
        owns_http_client: bool | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("API_BASE_URL") or DEFAULT_API_BASE_URL).rstrip("/")
        self._internal_api_key = internal_api_key if internal_api_key is not None else os.getenv("INTERNAL_API_KEY")
        self._http_client = http_client or httpx.Client(timeout=REQUEST_TIMEOUT)
        self._owns_http_client = http_client is None if owns_http_client is None else owns_http_client

    @property
    def api_key_configured(self) -> bool:
        return bool(self._internal_api_key)

    def close(self) -> None:
        if self._owns_http_client:
            self._http_client.close()

    def health(self) -> HealthResponse:
        response = self._send("GET", "/healthz", requires_auth=False)
        return self._parse_json(response, HealthResponse)

    def system_status(self) -> APIEnvelope[SystemStatusData]:
        return self._request_json("GET", "/api/v1/system/status", APIEnvelope[SystemStatusData])

    def search_repositories(
        self,
        q: str,
        language: str | None = None,
        stars_min: int | None = None,
        sort: str = "best_match",
        order: str = "desc",
        page: int = 1,
        per_page: int = 20,
    ) -> APIEnvelope[RepositorySearchData]:
        params = self._without_none(
            {"q": q, "language": language, "stars_min": stars_min, "sort": sort, "order": order,
             "page": page, "per_page": per_page}
        )
        return self._request_json("GET", "/api/v1/github/search", APIEnvelope[RepositorySearchData], params=params)

    def resolve_repository(self, input: str) -> APIEnvelope[RepositoryPreview]:
        return self._request_json("POST", "/api/v1/github/resolve", APIEnvelope[RepositoryPreview], json={"input": input})

    def add_repository(
        self,
        full_name: str,
        auto_analyze: bool = True,
        depth: str = "basic",
        idempotency_key: str | None = None,
    ) -> APIEnvelope[AddRepositoryData]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        body = {"full_name": full_name, "auto_analyze": auto_analyze, "depth": depth}
        return self._request_json("POST", "/api/v1/library/repositories", APIEnvelope[AddRepositoryData], json=body, headers=headers)

    def list_library(self, **filters: Any) -> APIEnvelope[RepositoryListData]:
        params = self._validated_filters(
            filters, {"q", "language", "status", "sort", "order", "page", "per_page"}
        )
        return self._request_json("GET", "/api/v1/library/repositories", APIEnvelope[RepositoryListData], params=params)

    def remove_from_library(self, repository_id: int) -> None:
        response = self._send("DELETE", f"/api/v1/library/repositories/{int(repository_id)}")
        if response.status_code != 204:
            self._raise_for_error(response)

    def repository_detail(self, repository_id: int) -> APIEnvelope[RepositoryDetailData]:
        path = f"/api/v1/repositories/{int(repository_id)}"
        return self._request_json("GET", path, APIEnvelope[RepositoryDetailData])

    def refresh_repository(
        self,
        repository_id: int,
        depth: str = "basic",
        force: bool = False,
        idempotency_key: str | None = None,
    ) -> APIEnvelope[RefreshTaskData]:
        path = f"/api/v1/repositories/{int(repository_id)}/refresh"
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._request_json(
            "POST",
            path,
            APIEnvelope[RefreshTaskData],
            json={"depth": depth, "force": force},
            headers=headers,
        )

    def repository_analysis(self, repository_id: int, depth: str = "basic") -> APIEnvelope[RepositoryAnalysisData]:
        path = f"/api/v1/repositories/{int(repository_id)}/analysis"
        return self._request_json("GET", path, APIEnvelope[RepositoryAnalysisData], params={"depth": depth})

    def repository_series(self, repository_id: int, metric: str, **period: Any) -> APIEnvelope[RepositorySeriesData]:
        params = self._validated_filters(period, {"from", "to", "granularity"})
        params["metric"] = metric
        path = f"/api/v1/repositories/{int(repository_id)}/series"
        return self._request_json("GET", path, APIEnvelope[RepositorySeriesData], params=params)

    def list_tasks(self, **filters: Any) -> APIEnvelope[TaskListData]:
        params = self._validated_filters(filters, {"status", "repository_id", "page", "per_page"})
        return self._request_json("GET", "/api/v1/tasks", APIEnvelope[TaskListData], params=params)

    def task_detail(self, task_id: str) -> APIEnvelope[Task]:
        path = f"/api/v1/tasks/{quote(task_id, safe='')}"
        return self._request_json("GET", path, APIEnvelope[Task])

    def retry_task(self, task_id: str, idempotency_key: str | None = None) -> APIEnvelope[RetryTaskData]:
        path = f"/api/v1/tasks/{quote(task_id, safe='')}/retry"
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._request_json("POST", path, APIEnvelope[RetryTaskData], json={}, headers=headers)

    def datasets(self) -> APIEnvelope[DatasetListData]:
        return self._request_json("GET", "/api/v1/datasets", APIEnvelope[DatasetListData])

    def overview(
        self, scope: str, dataset_id: str | None = None, language: str | None = None
    ) -> APIEnvelope[OverviewData]:
        params = self._without_none({"scope": scope, "dataset_id": dataset_id, "language": language})
        return self._request_json("GET", "/api/v1/overview", APIEnvelope[OverviewData], params=params)

    def research_statistics(
        self, dataset_id: str, language: str | None = None, group_by: str = "language"
    ) -> APIEnvelope[ResearchStatisticsData]:
        params = self._without_none({"dataset_id": dataset_id, "language": language, "group_by": group_by})
        return self._request_json("GET", "/api/v1/research/statistics", APIEnvelope[ResearchStatisticsData], params=params)

    def research_data_quality(self, dataset_id: str) -> APIEnvelope[DataQualityData]:
        return self._request_json(
            "GET", "/api/v1/research/data-quality", APIEnvelope[DataQualityData], params={"dataset_id": dataset_id}
        )

    def compare(self, repository_ids: list[int], depth: str = "basic") -> APIEnvelope[ComparisonData]:
        body = {"repository_ids": repository_ids, "depth": depth}
        return self._request_json("POST", "/api/v1/comparisons", APIEnvelope[ComparisonData], json=body)

    def export_repositories_csv(
        self, scope: str, dataset_id: str | None = None, language: str | None = None
    ) -> CSVExport:
        params = self._without_none({"scope": scope, "dataset_id": dataset_id, "language": language})
        response = self._send("GET", "/api/v1/exports/repositories.csv", params=params, accept="text/csv")
        if not 200 <= response.status_code < 300:
            self._raise_for_error(response)

        disposition = Message()
        disposition["content-disposition"] = response.headers.get("content-disposition", "")
        raw_filename = disposition.get_param("filename", header="content-disposition")
        filename = Path(str(raw_filename or "repositories.csv").replace("\\", "/")).name
        return CSVExport(
            content=response.content,
            content_type=response.headers.get("content-type", "text/csv; charset=utf-8"),
            filename=filename or "repositories.csv",
        )

    def _request_json(
        self,
        method: str,
        path: str,
        response_model: Any,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        response = self._send(method, path, params=params, json=json, headers=headers)
        if not 200 <= response.status_code < 300:
            self._raise_for_error(response)
        return self._parse_json(response, response_model)

    def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        requires_auth: bool = True,
        accept: str = "application/json",
    ) -> httpx.Response:
        request_headers = {"Accept": accept}
        if requires_auth:
            if not self.api_key_configured:
                raise APIError(status_code=0, code="CLIENT_CONFIGURATION_ERROR")
            request_headers["X-Internal-Api-Key"] = str(self._internal_api_key)
        if headers:
            request_headers.update(headers)

        try:
            return self._http_client.request(
                method,
                f"{self.base_url}{path}",
                params=params,
                json=json,
                headers=request_headers,
                timeout=REQUEST_TIMEOUT,
            )
        except httpx.TimeoutException as exc:
            raise APIError(status_code=504, code="API_TIMEOUT") from exc
        except httpx.RequestError as exc:
            raise APIError(status_code=503, code="BACKEND_UNAVAILABLE") from exc

    @staticmethod
    def _parse_json(response: httpx.Response, response_model: Any) -> Any:
        try:
            return TypeAdapter(response_model).validate_python(response.json())
        except (ValueError, ValidationError) as exc:
            request_id = APIClient._request_id_from_response(response)
            raise APIError(
                status_code=response.status_code,
                code="INVALID_API_RESPONSE",
                request_id=request_id,
            ) from exc

    @staticmethod
    def _raise_for_error(response: httpx.Response) -> None:
        try:
            envelope = ErrorEnvelope.model_validate(response.json())
            error = envelope.error
            raise APIError(
                status_code=response.status_code,
                code=error.code,
                message=error.message,
                details=error.details,
                request_id=envelope.request_id,
            )
        except ValidationError:
            raise APIError(
                status_code=response.status_code,
                code="HTTP_ERROR",
                request_id=APIClient._request_id_from_response(response),
            ) from None
        except ValueError:
            raise APIError(
                status_code=response.status_code,
                code="HTTP_ERROR",
                request_id=APIClient._request_id_from_response(response),
            ) from None

    @staticmethod
    def _request_id_from_response(response: httpx.Response) -> str | None:
        try:
            body = response.json()
        except ValueError:
            return None
        if not isinstance(body, dict):
            return None
        request_id = body.get("request_id")
        if not request_id and isinstance(body.get("meta"), dict):
            request_id = body["meta"].get("request_id")
        return request_id if isinstance(request_id, str) else None

    @staticmethod
    def _without_none(values: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in values.items() if value is not None}

    @staticmethod
    def _validated_filters(filters: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
        unexpected = set(filters) - allowed
        if unexpected:
            raise ValueError(f"Unsupported API filter(s): {', '.join(sorted(unexpected))}")
        return APIClient._without_none(filters)

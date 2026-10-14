import json
import os
from pathlib import Path

import httpx
import pytest

from frontend.api import client as client_module
from frontend.api.client import APIClient, APISettings
from frontend.api.errors import APIError


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_settings_read_root_env_file_and_process_environment_wins(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "API_BASE_URL=http://dotenv.example/\nINTERNAL_API_KEY=dotenv-key\nMOCK_MODE=true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(client_module, "PROJECT_ROOT", tmp_path)
    for name in ("API_BASE_URL", "INTERNAL_API_KEY", "MOCK_MODE"):
        monkeypatch.delenv(name, raising=False)

    from_file = APISettings.from_environment()
    assert from_file.api_base_url == "http://dotenv.example"
    assert from_file.internal_api_key == "dotenv-key"
    assert from_file.mock_mode is True
    assert "INTERNAL_API_KEY" not in os.environ

    monkeypatch.setenv("API_BASE_URL", "http://process.example/")
    monkeypatch.setenv("INTERNAL_API_KEY", "process-key")
    monkeypatch.setenv("MOCK_MODE", "false")
    from_process = APISettings.from_environment()
    assert from_process.api_base_url == "http://process.example"
    assert from_process.internal_api_key == "process-key"
    assert from_process.mock_mode is False


def test_settings_reject_invalid_mock_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(client_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("MOCK_MODE", "sometimes")

    with pytest.raises(ValueError, match="MOCK_MODE"):
        APISettings.from_environment()


def test_client_keeps_auth_server_side_and_supports_refresh_delete_and_csv():
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/datasets":
            return httpx.Response(200, json=load_fixture("default_datasets.json"))
        if request.url.path == "/api/v1/repositories/123/refresh":
            return httpx.Response(202, json=load_fixture("refresh_reused_succeeded.json"))
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path == "/api/v1/exports/repositories.csv":
            return httpx.Response(
                200,
                content=b"repository_id,full_name\n123,example/project\n",
                headers={
                    "content-type": "text/csv; charset=utf-8",
                    "content-disposition": 'attachment; filename="repositories.csv"',
                },
            )
        return httpx.Response(404)

    http_client = httpx.Client(transport=httpx.MockTransport(respond))
    client = APIClient(
        base_url="http://backend.test",
        internal_api_key="server-only-test-key",
        http_client=http_client,
        owns_http_client=True,
    )
    try:
        datasets = client.datasets().data.items
        refresh = client.refresh_repository(123, idempotency_key="refresh-once").data
        client.remove_from_library(123)
        export = client.export_repositories_csv("library")
    finally:
        client.close()

    assert {item.type for item in datasets} == {"library", "research", "featured"}
    assert refresh.status == "succeeded"
    assert export.content.startswith(b"repository_id,")
    assert export.filename == "repositories.csv"
    assert requests[0].headers["X-Internal-Api-Key"] == "server-only-test-key"
    assert requests[1].headers["Idempotency-Key"] == "refresh-once"
    assert all("server-only-test-key" not in str(request.url) for request in requests)
    assert requests[2].method == "DELETE"


@pytest.mark.parametrize(
    ("status", "code", "safe_message"),
    [
        (401, "UNAUTHORIZED_CLIENT", "认证配置不匹配"),
        (429, "GITHUB_RATE_LIMITED", "请求暂时受限"),
        (503, "BACKEND_UNAVAILABLE", "后端服务暂不可用"),
    ],
)
def test_error_responses_are_mapped_without_echoing_backend_text(status, code, safe_message):
    secret_marker = "never-display-this-token"

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={
                "error": {"code": code, "message": f"INTERNAL_API_KEY={secret_marker}", "details": {}},
                "request_id": "req_test_error",
            },
        )

    client = APIClient(
        base_url="http://backend.test",
        internal_api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
        owns_http_client=True,
    )
    try:
        with pytest.raises(APIError) as raised:
            client.datasets()
    finally:
        client.close()

    assert raised.value.code == code
    assert safe_message in raised.value.user_message
    assert secret_marker not in raised.value.user_message

from fastapi.testclient import TestClient

from backend.app.main import app


def local_client():
    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 55001))


def test_browser_session_is_local_http_only_and_proxies_without_exposing_internal_key(backend_client):
    legacy_client, _factory, _github = backend_client
    with local_client() as client:
        bootstrap = client.get("/api/browser/session", headers={"X-GDA-Request": "browser", "Origin": "http://127.0.0.1"})
        assert bootstrap.status_code == 200
        assert bootstrap.json()["csrf_token"]
        cookie = bootstrap.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=strict" in cookie
        assert "secure" not in cookie
        assert "internal_api_key" not in bootstrap.text.lower()

        proxied = client.get("/api/browser/v1/datasets", headers={"X-GDA-Request": "browser", "Origin": "http://127.0.0.1"})
        assert proxied.status_code == 200
        assert proxied.json()["data"]["items"]

    assert legacy_client.get("/api/v1/datasets").status_code == 401


def test_browser_gateway_rejects_cross_origin_and_missing_csrf(backend_client):
    _legacy_client, _factory, _github = backend_client
    with local_client() as client:
        cross_origin = client.get("/api/browser/session", headers={"X-GDA-Request": "browser", "Origin": "https://attacker.example"})
        assert cross_origin.status_code == 403
        assert cross_origin.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"

        bootstrap = client.get("/api/browser/session", headers={"X-GDA-Request": "browser", "Origin": "http://127.0.0.1"})
        assert bootstrap.status_code == 200
        blocked = client.post(
            "/api/browser/v1/library/repositories",
            headers={"X-GDA-Request": "browser", "Origin": "http://127.0.0.1"},
            json={"full_name": "example/project", "auto_analyze": False},
        )
        assert blocked.status_code == 403
        assert blocked.json()["error"]["code"] == "CSRF_VALIDATION_FAILED"


def test_browser_gateway_rejects_non_loopback_peer(backend_client):
    _legacy_client, _factory, _github = backend_client
    with TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.20", 55001)) as client:
        response = client.get("/api/browser/session", headers={"X-GDA-Request": "browser"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "LOCAL_ACCESS_ONLY"


def test_browser_gateway_forwards_empty_delete_response(backend_client):
    _legacy_client, _factory, _github = backend_client
    with local_client() as client:
        headers = {"X-GDA-Request": "browser", "Origin": "http://127.0.0.1"}
        bootstrap = client.get("/api/browser/session", headers=headers)
        headers["X-CSRF-Token"] = bootstrap.json()["csrf_token"]
        added = client.post("/api/browser/v1/library/repositories", headers=headers, json={"full_name": "example/project", "auto_analyze": False})
        assert added.status_code == 201

        removed = client.delete(f"/api/browser/v1/library/repositories/{added.json()['data']['repository_id']}", headers=headers)

    assert removed.status_code == 204
    assert removed.content == b""

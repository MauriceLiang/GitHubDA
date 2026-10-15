import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter
from streamlit.testing.v1 import AppTest

from frontend.api.errors import APIError
from frontend.api.mock_client import MockAPIClient
from frontend.api.models import APIEnvelope, Task
from frontend.state.keys import STATE_KEYS


APP_PATH = Path(__file__).resolve().parents[2] / "frontend" / "app.py"
PAGES = [
    ("pages/dashboard.py", "分析任何公开 GitHub 仓库"),
    ("pages/explore.py", "发现仓库"),
    ("pages/library.py", "我的分析库"),
    ("pages/comparison.py", "仓库对比"),
    ("pages/repository.py", "仓库详情"),
    ("pages/research.py", "研究分析"),
    ("pages/operations.py", "任务中心"),
]


@pytest.mark.parametrize(("page_path", "expected_header"), PAGES)
def test_navigation_executes_each_page_body(page_path, expected_header, monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    app.switch_page(page_path)
    # AppTest switches directly to the page script and does not rerun the app shell,
    # so restore the shell-owned chart preference used by chart-bearing pages.
    app.session_state[STATE_KEYS["chart_theme"]] = "dark"
    app.run()

    assert expected_header in [item.value for item in app.header]
    assert not app.exception


def test_library_detail_navigation_and_query_param_refresh(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    app.switch_page("pages/library.py")
    app.session_state[STATE_KEYS["chart_theme"]] = "dark"
    app.run()
    detail_button = next(button for button in app.button if button.key and button.key.startswith("detail-"))
    repository_id = detail_button.key.removeprefix("detail-")

    detail_button.click()
    app.session_state[STATE_KEYS["chart_theme"]] = "dark"
    app.run()

    assert "仓库详情" in [item.value for item in app.header]
    assert app.query_params["repository_id"] == [repository_id]
    assert not app.exception

    reloaded = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    reloaded.query_params["repository_id"] = repository_id
    reloaded.switch_page("pages/repository.py")
    reloaded.session_state[STATE_KEYS["chart_theme"]] = "dark"
    reloaded.run()
    assert "仓库详情" in [item.value for item in reloaded.header]
    assert not reloaded.exception


def test_empty_library_dashboard_has_a_search_action(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    app.session_state[STATE_KEYS["mock_scenario"]] = "empty_library"
    app.run()

    assert any(element.key == STATE_KEYS["home_repository_input"] for element in app.text_input)
    assert app.button(key="dashboard-analyze-repository").label == "分析仓库"
    assert any("最近仓库" in item.value for item in app.markdown)
    assert not app.exception


def test_dashboard_analysis_adds_repository_and_opens_detail(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    app.text_input(key=STATE_KEYS["home_repository_input"]).set_value("psf/requests")
    app.run()

    app.button(key="dashboard-analyze-repository").click()
    app.run()

    assert "仓库详情" in [item.value for item in app.header]
    assert app.query_params["repository_id"] == ["1362490"]
    assert app.session_state[STATE_KEYS["repository_id"]] == 1362490
    assert app.session_state[STATE_KEYS["task_id"]] == "11111111-2222-4333-8444-555555555555"
    assert not app.exception


def test_dashboard_invalid_repository_preserves_input_and_shows_error(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    client = MockAPIClient(scenarios={"resolve_repository": "resolve_invalid"})
    app.session_state[STATE_KEYS["mock_api_client"]] = client
    app.run()
    app.text_input(key=STATE_KEYS["home_repository_input"]).set_value("not a repository")
    app.run()

    app.button(key="dashboard-analyze-repository").click()
    app.run()

    assert any("仓库地址格式不正确" in item.value for item in app.error)
    assert app.text_input(key=STATE_KEYS["home_repository_input"]).value == "not a repository"
    assert app.session_state[STATE_KEYS["repository_id"]] is None
    assert not app.exception


def test_dashboard_existing_repository_does_not_add_again(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    client = MockAPIClient(scenarios={"resolve_repository": "resolve_existing"})

    def fail_add(*_args, **_kwargs):
        raise AssertionError("already-added repository must not be added again")

    client.add_repository = fail_add
    app.session_state[STATE_KEYS["mock_api_client"]] = client
    app.run()
    app.text_input(key=STATE_KEYS["home_repository_input"]).set_value("https://github.com/psf/requests")
    app.run()

    app.button(key="dashboard-analyze-repository").click()
    app.run()

    assert app.query_params["repository_id"] == ["1362490"]
    assert app.session_state[STATE_KEYS["task_id"]] is None
    assert not app.exception


def test_dashboard_retry_reuses_idempotency_key_and_preserves_input(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    client = MockAPIClient()
    add_keys = []
    add_repository = client.add_repository

    def fail_once(full_name, **kwargs):
        add_keys.append(kwargs.get("idempotency_key"))
        if len(add_keys) == 1:
            raise APIError(status_code=503, code="BACKEND_UNAVAILABLE")
        return add_repository(full_name, **kwargs)

    client.add_repository = fail_once
    app.session_state[STATE_KEYS["mock_api_client"]] = client
    app.run()
    app.text_input(key=STATE_KEYS["home_repository_input"]).set_value("psf/requests")
    app.run()

    app.button(key="dashboard-analyze-repository").click()
    app.run()
    assert any("后端服务暂不可用" in item.value for item in app.error)
    assert app.text_input(key=STATE_KEYS["home_repository_input"]).value == "psf/requests"

    app.button(key="dashboard-analyze-repository").click()
    app.run()

    assert add_keys[0] == add_keys[1]
    assert add_keys[0]
    assert app.query_params["repository_id"] == ["1362490"]
    assert not app.exception


def test_explore_analysis_uses_direct_detail_flow(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    app.switch_page("pages/explore.py")
    app.session_state[STATE_KEYS["chart_theme"]] = "dark"
    app.run()
    app.text_input(key=STATE_KEYS["search_query"]).set_value("requests")
    app.run()

    app.button(key="repository-search-submit").click()
    app.run()
    app.button(key="add-repository-1362490").click()
    app.run()

    assert "仓库详情" in [item.value for item in app.header]
    assert app.query_params["repository_id"] == ["1362490"]
    assert app.session_state[STATE_KEYS["task_id"]] == "11111111-2222-4333-8444-555555555555"
    assert not app.exception


def test_v2_task_progress_fixture_renders_in_task_center(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    app.session_state[STATE_KEYS["mock_scenario"]] = "task_progress"
    app.switch_page("pages/operations.py")
    app.run()

    assert app.session_state[STATE_KEYS["task_id"]] == "11111111-2222-4333-8444-555555555555"
    assert not app.exception


def test_running_task_with_null_stage_percentage_explains_missing_progress():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "task_progress.json").read_text(encoding="utf-8"))
    fixture["data"]["progress_percent"] = None
    task = TypeAdapter(APIEnvelope[Task]).validate_python(fixture).data
    app = AppTest.from_string(
        """
import streamlit as st
from frontend.components.task_summary import render_task_summary

render_task_summary(st.session_state.task)
""",
        default_timeout=20,
    )
    app.session_state["task"] = task
    app.run()

    assert any("阶段进度暂不可用" in item.value for item in app.caption)
    assert not app.exception

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter
from streamlit.testing.v1 import AppTest

from frontend.api.models import APIEnvelope, Task
from frontend.state.keys import STATE_KEYS


APP_PATH = Path(__file__).resolve().parents[2] / "frontend" / "app.py"
PAGES = [
    ("pages/dashboard.py", "工作台"),
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

    assert any("分析库还没有仓库" in item.value for item in app.markdown)
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

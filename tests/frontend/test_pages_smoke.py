from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from frontend.state.keys import STATE_KEYS


APP_PATH = Path(__file__).resolve().parents[2] / "frontend" / "app.py"
PAGES = [
    ("pages/dashboard.py", "数据概览"),
    ("pages/explore.py", "仓库发现"),
    ("pages/library.py", "我的分析库"),
    ("pages/comparison.py", "项目对比"),
    ("pages/repository.py", "仓库详情"),
    ("pages/research.py", "数据研究"),
    ("pages/operations.py", "数据与任务"),
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

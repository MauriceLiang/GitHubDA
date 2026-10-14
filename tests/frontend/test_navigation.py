from frontend.components.navigation import build_navigation


def test_navigation_registers_seven_pages_with_hidden_repository_details():
    pages = [page for section in build_navigation().values() for page in section]

    assert len(pages) == 7
    assert sum(page.visibility != "hidden" for page in pages) == 6
    hidden_pages = [page for page in pages if page.visibility == "hidden"]
    assert len(hidden_pages) == 1

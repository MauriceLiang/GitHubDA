from __future__ import annotations

import re
from uuid import uuid4

import streamlit as st

from frontend.api.errors import APIError
from frontend.api.factory import get_api_client
from frontend.components.feedback import render_api_error
from frontend.components.page_header import render_page_header
from frontend.components.repository_row import render_repository_row
from frontend.state.keys import STATE_KEYS


def _looks_like_repository_input(value: str) -> bool:
    text = value.strip()
    return text.lower().startswith(("http://", "https://")) or bool(
        re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", text)
    )


def _search(query: str, language: str, stars_min: int, sort: str, page: int) -> None:
    if not query.strip():
        st.session_state[STATE_KEYS["search_results"]] = None
        return

    st.session_state[STATE_KEYS["search_results"]] = None
    try:
        client, _ = get_api_client()
        if _looks_like_repository_input(query):
            response = client.resolve_repository(query.strip())
            st.session_state[STATE_KEYS["search_results"]] = {
                "items": [response.data],
                "pagination": None,
                "search": None,
                "is_resolve": True,
            }
        else:
            response = client.search_repositories(
                query.strip(),
                language=language.strip() or None,
                stars_min=stars_min or None,
                sort=sort,
                page=page,
                per_page=20,
            )
            st.session_state[STATE_KEYS["search_results"]] = {
                "items": response.data.items,
                "pagination": response.meta.pagination,
                "search": response.meta.search,
                "is_resolve": False,
            }
    except APIError as error:
        render_api_error(error)


def _open_repository(repository_id: int) -> None:
    st.session_state[STATE_KEYS["repository_id"]] = repository_id
    st.switch_page("pages/repository.py", query_params={"repository_id": str(repository_id)})


def render() -> None:
    render_page_header(
        "发现仓库",
        "搜索公开 GitHub 仓库，或直接粘贴 owner/repo 和仓库链接。",
    )
    client, _ = get_api_client()
    notice = st.session_state[STATE_KEYS["search_add_notice"]]
    if notice:
        if notice["membership_created"]:
            st.success(f"{notice['full_name']} 已加入分析库；基础采集已提交。")
        else:
            st.info(f"{notice['full_name']} 已在分析库中，没有重复添加。")
        if notice["task_id"]:
            st.caption(f"最近任务：{status_text(notice['status'])}")
            st.page_link("pages/operations.py", label="查看任务中心")
        st.page_link("pages/library.py", label="打开我的分析库")

    with st.form("repository-search"):
        query = st.text_input(
            "GitHub 仓库",
            key=STATE_KEYS["search_query"],
            placeholder="例如：psf/requests 或 https://github.com/psf/requests",
        )
        with st.expander("筛选条件"):
            left, middle, right = st.columns(3)
            language = left.text_input(
                "语言",
                key=STATE_KEYS["search_language"],
                placeholder="Python",
            )
            stars_min = middle.number_input(
                "最低 Star",
                min_value=0,
                max_value=1_000_000,
                step=100,
                key=STATE_KEYS["search_stars_min"],
            )
            sort = right.selectbox(
                "排序",
                options=("best_match", "stars", "updated"),
                format_func={"best_match": "最佳匹配", "stars": "Star", "updated": "最近更新"}.get,
                key=STATE_KEYS["search_sort"],
            )
        submitted = st.form_submit_button("搜索仓库", type="primary", width="stretch")

    if submitted:
        st.session_state[STATE_KEYS["search_page"]] = 1
        st.session_state[STATE_KEYS["search_add_notice"]] = None
        if not query.strip():
            st.warning("请输入关键词或仓库地址。")
            st.session_state[STATE_KEYS["search_results"]] = None
        else:
            _search(query, language, int(stars_min), sort, 1)

    results = st.session_state[STATE_KEYS["search_results"]]
    if not results:
        st.caption("搜索只列出远程候选；只有选择添加后才会进入个人分析库。")
        return

    search_meta = results["search"]
    if search_meta and search_meta.incomplete_results:
        st.warning("GitHub 搜索结果可能不完整。")
    if search_meta:
        st.caption(
            f"来源：GitHub REST API · 候选数 {search_meta.total_count} · "
            f"可观察窗口最多 {search_meta.result_window_limit} 项；不是 GitHub 全站项目总数。"
        )

    if not results["items"]:
        st.info("没有匹配的仓库。请调整关键词或筛选条件。")
        return

    for repository in results["items"]:
        already_added = repository.already_in_library or repository.repository_id in st.session_state[
            STATE_KEYS["added_repository_ids"]
        ]
        with st.container(border=True):
            title, action = st.columns([5, 1])
            with title:
                render_repository_row(
                    full_name=repository.full_name,
                    description=repository.description,
                    language=repository.language,
                    stars=repository.stars,
                    forks=repository.forks,
                    html_url=repository.html_url,
                )
                if already_added:
                    st.caption("已在我的分析库")
            with action:
                if already_added:
                    if st.button("查看分析", key=f"explore-detail-{repository.repository_id}"):
                        _open_repository(repository.repository_id)
                elif st.button(
                    "添加分析库",
                    key=f"add-repository-{repository.repository_id}",
                    type="primary",
                ):
                    try:
                        added = client.add_repository(
                            repository.full_name,
                            auto_analyze=True,
                            depth="basic",
                            idempotency_key=str(uuid4()),
                        ).data
                    except APIError as error:
                        render_api_error(error)
                    else:
                        added_ids = st.session_state[STATE_KEYS["added_repository_ids"]]
                        if repository.repository_id not in added_ids:
                            st.session_state[STATE_KEYS["added_repository_ids"]] = [*added_ids, repository.repository_id]
                        if added.task_id:
                            st.session_state[STATE_KEYS["task_id"]] = added.task_id
                            st.session_state[STATE_KEYS["task_poll_complete_for"]] = None
                            st.session_state[STATE_KEYS["task_poll_error_for"]] = None
                        st.session_state[STATE_KEYS["search_add_notice"]] = {
                            "full_name": repository.full_name,
                            "membership_created": added.membership_created,
                            "status": added.analysis_status,
                            "task_id": added.task_id,
                        }
                        st.rerun()

    pagination = results["pagination"]
    if pagination and (pagination.page > 1 or pagination.has_next):
        previous, page_label, next_page = st.columns([1, 2, 1])
        if previous.button("上一页", disabled=pagination.page <= 1):
            new_page = pagination.page - 1
            st.session_state[STATE_KEYS["search_page"]] = new_page
            _search(query, language, int(stars_min), sort, new_page)
            st.rerun()
        page_label.caption(f"第 {pagination.page} 页 · 每页 {pagination.per_page} 项")
        if next_page.button("下一页", disabled=not pagination.has_next):
            new_page = pagination.page + 1
            st.session_state[STATE_KEYS["search_page"]] = new_page
            _search(query, language, int(stars_min), sort, new_page)
            st.rerun()


def status_text(status: str) -> str:
    return {
        "not_started": "等待采集",
        "queued": "已排队",
        "processing": "正在采集",
        "completed": "基础分析已完成",
        "partial": "部分完成",
        "failed": "失败",
    }.get(status, "等待状态更新")


render()

from __future__ import annotations

import re
from uuid import uuid4

import streamlit as st

from frontend.api.errors import APIError
from frontend.api.factory import get_api_client
from frontend.components.feedback import render_api_error
from frontend.state.keys import STATE_KEYS


def _looks_like_repository_input(value: str) -> bool:
    text = value.strip()
    return text.lower().startswith(("http://", "https://")) or bool(
        re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", text)
    )


def _search(query: str, language: str, stars_min: int, sort: str, page: int) -> None:
    if not query.strip():
        st.session_state[STATE_KEYS["search_results"]] = None
        st.warning("请输入搜索词或 GitHub 仓库地址。")
        return

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


def render() -> None:
    st.header("仓库发现")
    client, _ = get_api_client()
    with st.form("repository-search"):
        query = st.text_input(
            "关键词、owner/repo 或 GitHub 仓库链接",
            key=STATE_KEYS["search_query"],
            placeholder="例如：requests 或 psf/requests",
        )
        left, middle, right = st.columns(3)
        with left:
            language = st.text_input("语言（可选）", key=STATE_KEYS["search_language"], placeholder="Python")
        with middle:
            stars_min = st.number_input(
                "最低 Star", min_value=0, max_value=1_000_000, step=100, key=STATE_KEYS["search_stars_min"]
            )
        with right:
            sort = st.selectbox(
                "排序",
                options=("best_match", "stars", "updated"),
                format_func={"best_match": "最佳匹配", "stars": "Star", "updated": "最近更新"}.get,
                key=STATE_KEYS["search_sort"],
            )
        submitted = st.form_submit_button("搜索 / 解析", type="primary", use_container_width=True)

    if submitted:
        st.session_state[STATE_KEYS["search_page"]] = 1
        _search(query, language, int(stars_min), sort, 1)

    results = st.session_state[STATE_KEYS["search_results"]]
    if not results:
        st.info("搜索结果只作为远程候选，不会自动加入分析库。")
        return

    search_meta = results["search"]
    if search_meta and search_meta.incomplete_results:
        st.warning("GitHub 搜索结果可能不完整。")
    if search_meta:
        st.caption(
            f"来源：GitHub REST API · 候选数 {search_meta.total_count} · 可观察窗口最多 {search_meta.result_window_limit} 项；不是 GitHub 全站项目总数。"
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
                st.subheader(repository.full_name)
                st.caption(repository.description or "暂无简介")
                st.markdown(
                    f"语言：{repository.language or '未知'} · Stars：{repository.stars if repository.stars is not None else '未知'} · Forks：{repository.forks if repository.forks is not None else '未知'}"
                )
                if repository.github_updated_at:
                    st.caption(f"GitHub 仓库更新时间：{repository.github_updated_at.isoformat()}")
                st.link_button("在 GitHub 打开", repository.html_url)
                if already_added:
                    st.caption("已在我的分析库")
            with action:
                if st.button(
                    "已加入" if already_added else "添加",
                    key=f"add-repository-{repository.repository_id}",
                    disabled=already_added,
                    type="primary" if not already_added else "secondary",
                ):
                    try:
                        added = client.add_repository(
                            repository.full_name,
                            auto_analyze=True,
                            depth="basic",
                            idempotency_key=str(uuid4()),
                        ).data
                        if added.membership_created:
                            st.success("已加入分析库，基础分析任务已提交。")
                        else:
                            st.info("该仓库已在分析库中，未重复创建成员关系。")
                        added_ids = st.session_state[STATE_KEYS["added_repository_ids"]]
                        if repository.repository_id not in added_ids:
                            st.session_state[STATE_KEYS["added_repository_ids"]] = [*added_ids, repository.repository_id]
                        if added.task_id:
                            st.session_state[STATE_KEYS["task_id"]] = added.task_id
                            st.session_state[STATE_KEYS["task_poll_complete_for"]] = None
                            st.session_state[STATE_KEYS["task_poll_error_for"]] = None
                            st.caption(f"任务：{added.task_id} · 状态：{added.analysis_status}")
                        st.page_link("frontend/pages/library.py", label="打开我的分析库")
                    except APIError as error:
                        render_api_error(error)

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

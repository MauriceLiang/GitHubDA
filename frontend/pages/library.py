from __future__ import annotations

from uuid import uuid4

import streamlit as st

from frontend.api.errors import APIError
from frontend.api.factory import get_api_client
from frontend.components.confirm_action import render_confirm_action
from frontend.components.empty_state import render_empty_state
from frontend.components.feedback import format_refresh_result, render_api_error
from frontend.components.page_header import render_page_header
from frontend.components.repository_row import render_repository_row
from frontend.components.status_indicator import STATUS_LABELS
from frontend.state.keys import STATE_KEYS


ANALYSIS_STATUSES = ("not_started", "queued", "processing", "completed", "partial", "failed")


def _start_refresh(client: object, repository_id: int, depth: str) -> None:
    operation = "深度分析" if depth == "deep" else "基础刷新"
    try:
        result = client.refresh_repository(
            repository_id,
            depth=depth,
            idempotency_key=str(uuid4()),
        ).data
    except APIError as error:
        render_api_error(error)
        return
    st.session_state[STATE_KEYS["task_id"]] = result.task_id
    st.session_state[STATE_KEYS["task_poll_complete_for"]] = None
    st.session_state[STATE_KEYS["task_poll_error_for"]] = None
    st.toast(format_refresh_result(result, operation))


def _render_export(client: object) -> None:
    with st.expander("导出分析库数据"):
        st.caption("导出范围为个人分析库，不包含研究数据集。缺失指标按 API 原始 CSV 契约保留。")
        if st.button("准备分析库 CSV", key="prepare-library-csv"):
            try:
                st.session_state[STATE_KEYS["library_export_payload"]] = client.export_repositories_csv("library")
            except APIError as error:
                render_api_error(error)
        payload = st.session_state[STATE_KEYS["library_export_payload"]]
        if payload:
            st.download_button(
                "下载分析库 CSV",
                data=payload.content,
                file_name=payload.filename,
                mime=payload.content_type,
                key="download-library-csv",
            )


def render() -> None:
    render_page_header("我的分析库", "管理个人仓库列表；移除成员关系不会删除历史数据。")
    st.page_link("pages/explore.py", label="发现并添加仓库")
    client, _ = get_api_client()

    with st.form("library-filters"):
        name_query = st.text_input(
            "搜索仓库",
            key=STATE_KEYS["library_query"],
            placeholder="仓库名或简介",
        )
        with st.expander("筛选与排序"):
            first, second, third = st.columns(3)
            status = first.selectbox(
                "分析状态",
                options=("", *ANALYSIS_STATUSES),
                format_func=lambda value: "全部" if not value else STATUS_LABELS[value],
                key=STATE_KEYS["library_status"],
            )
            sort = second.selectbox(
                "排序方式",
                options=("name", "stars", "last_collected"),
                format_func={"name": "名称", "stars": "Stars", "last_collected": "最近采集"}.get,
                key=STATE_KEYS["library_sort"],
            )
            order = third.selectbox(
                "顺序",
                options=("asc", "desc"),
                format_func={"asc": "升序", "desc": "降序"}.get,
                key=STATE_KEYS["library_order"],
            )
        filters_submitted = st.form_submit_button("应用筛选")
    if filters_submitted:
        st.session_state[STATE_KEYS["library_page"]] = 1

    try:
        response = client.list_library(
            q=name_query.strip() or None,
            status=status or None,
            sort=sort,
            order=order,
            page=st.session_state[STATE_KEYS["library_page"]],
            per_page=20,
        )
    except APIError as error:
        render_api_error(error)
        return

    repositories = response.data.items
    pending_id = st.session_state[STATE_KEYS["pending_delete_repository_id"]]
    if pending_id is not None:
        repository = next((item for item in repositories if item.repository_id == pending_id), None)
        name = repository.full_name if repository else f"仓库 ID {pending_id}"
        confirmed = render_confirm_action(
            f"确认从我的分析库移除 {name}",
            "这只移除个人分析库成员关系，不删除仓库快照、历史数据或研究样本。",
            confirm_key=f"confirm-remove-{pending_id}",
            cancel_key=f"cancel-remove-{pending_id}",
        )
        if confirmed is True:
            try:
                client.remove_from_library(int(pending_id))
            except APIError as error:
                render_api_error(error)
            else:
                st.session_state[STATE_KEYS["pending_delete_repository_id"]] = None
                st.session_state[STATE_KEYS["library_page"]] = 1
                st.session_state[STATE_KEYS["selected_repository_ids"]] = [
                    item for item in st.session_state[STATE_KEYS["selected_repository_ids"]] if item != pending_id
                ]
                st.success("已从我的分析库移除。")
                st.rerun()
        elif confirmed is False:
            st.session_state[STATE_KEYS["pending_delete_repository_id"]] = None
            st.rerun()

    if not repositories:
        total = response.meta.pagination.total if response.meta.pagination else None
        if total == 0 and not (name_query.strip() or status):
            render_empty_state(
                "分析库还没有仓库",
                "添加公开仓库后即可查看采集状态与分析结果。",
                action_label="搜索并添加仓库",
                target="pages/explore.py",
            )
        else:
            st.info("没有符合当前搜索和筛选条件的仓库。")
        _render_export(client)
        return

    selection_mode = st.checkbox(
        "进入多选对比模式",
        key=STATE_KEYS["library_selection_mode"],
    )
    name_by_id = {item.repository_id: item.full_name for item in repositories}
    if selection_mode:
        selected_names = st.session_state[STATE_KEYS["comparison_selected_names"]]
        selected_names.update(name_by_id)
        st.session_state[STATE_KEYS["comparison_selected_names"]] = selected_names
        selected_ids = list(st.session_state[STATE_KEYS["selected_repository_ids"]])
        options = [*name_by_id, *(item for item in selected_ids if item not in name_by_id)]
        selected = st.multiselect(
            "选择 2–5 个仓库；切换分页后会保留已选项",
            options=options,
            format_func=lambda repository_id: selected_names.get(repository_id, f"仓库 ID {repository_id}"),
            max_selections=5,
            key=STATE_KEYS["selected_repository_ids"],
        )
        if st.button("继续比较", disabled=not 2 <= len(selected) <= 5):
            st.switch_page("pages/comparison.py")

    for repository in repositories:
        with st.container(border=True):
            title, action = st.columns([5, 1])
            with title:
                render_repository_row(
                    full_name=repository.full_name,
                    description=repository.description,
                    language=repository.language,
                    stars=repository.stars,
                    forks=repository.forks,
                    analysis_status=repository.analysis_status,
                    data_status=repository.data_status,
                    collected_at=repository.last_successful_collection_at,
                )
                if repository.latest_task_id and repository.analysis_status in {"queued", "processing"}:
                    st.caption("进行中的任务可在任务中心继续查看。")
            with action:
                if st.button(
                    "查看分析",
                    key=f"detail-{repository.repository_id}",
                    type="primary",
                ):
                    st.session_state[STATE_KEYS["repository_id"]] = repository.repository_id
                    st.switch_page(
                        "pages/repository.py",
                        query_params={"repository_id": str(repository.repository_id)},
                    )
                with st.popover("更多操作"):
                    if st.button("基础刷新", key=f"refresh-{repository.repository_id}"):
                        _start_refresh(client, repository.repository_id, "basic")
                    if st.button("深度分析", key=f"deep-{repository.repository_id}"):
                        _start_refresh(client, repository.repository_id, "deep")
                    if st.button("移除", key=f"remove-{repository.repository_id}"):
                        st.session_state[STATE_KEYS["pending_delete_repository_id"]] = repository.repository_id
                        st.rerun()
                if repository.latest_task_id:
                    if st.button("查看任务", key=f"task-{repository.repository_id}"):
                        st.session_state[STATE_KEYS["task_id"]] = repository.latest_task_id
                        st.session_state[STATE_KEYS["task_poll_error_for"]] = None
                        st.switch_page("pages/operations.py")

    pagination = response.meta.pagination
    if pagination and (pagination.page > 1 or pagination.has_next):
        previous, label, next_page = st.columns([1, 2, 1])
        if previous.button("上一页", disabled=pagination.page <= 1):
            st.session_state[STATE_KEYS["library_page"]] = pagination.page - 1
            st.rerun()
        label.caption(f"第 {pagination.page} 页 · 共 {pagination.total if pagination.total is not None else '未知'} 项")
        if next_page.button("下一页", disabled=not pagination.has_next):
            st.session_state[STATE_KEYS["library_page"]] = pagination.page + 1
            st.rerun()

    _render_export(client)


render()

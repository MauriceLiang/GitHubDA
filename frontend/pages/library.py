from __future__ import annotations

from uuid import uuid4

import streamlit as st

from frontend.api.errors import APIError
from frontend.api.factory import get_api_client
from frontend.components.feedback import display_value, format_refresh_result, format_task_attempt, render_api_error
from frontend.state.keys import STATE_KEYS


ANALYSIS_STATUSES = ("not_started", "queued", "processing", "completed", "partial", "failed")
STATUS_LABELS = {
    "not_started": "未开始",
    "queued": "排队中",
    "processing": "处理中",
    "completed": "已完成",
    "partial": "部分完成",
    "failed": "失败",
}
DATA_STATUS_LABELS = {"missing": "缺少数据", "fresh": "数据新鲜", "stale": "数据已过期"}


def _format_datetime(value: object) -> str:
    return value.isoformat() if value is not None else "未采集"


def _show_task(client: object, task_id: str) -> None:
    try:
        task = client.task_detail(task_id).data
    except APIError as error:
        render_api_error(error)
        return
    label = STATUS_LABELS.get(task.status, task.status)
    progress = "进度未提供" if task.progress_percent is None else f"{task.progress_percent:g}%"
    st.info(
        f"任务 {task.task_id} · {label} · 阶段：{task.phase or '—'} · {progress} · 尝试次数：{format_task_attempt(task.attempt)}"
    )
    if task.message:
        st.caption(task.message)
    st.page_link("pages/operations.py", label="打开任务监控")


def render() -> None:
    st.header("我的分析库")
    client, _ = get_api_client()
    with st.form("library-filters"):
        query, status_filter, sort_filter, order_filter = st.columns([2, 1, 1, 1])
        with query:
            name_query = st.text_input("仓库名或简介", key=STATE_KEYS["library_query"])
        with status_filter:
            status = st.selectbox(
                "分析状态",
                options=("", *ANALYSIS_STATUSES),
                format_func=lambda value: "全部" if not value else STATUS_LABELS[value],
                key=STATE_KEYS["library_status"],
            )
        with sort_filter:
            sort = st.selectbox(
                "排序",
                options=("name", "stars", "last_collected"),
                format_func={"name": "名称", "stars": "Stars", "last_collected": "最近采集"}.get,
                key=STATE_KEYS["library_sort"],
            )
        with order_filter:
            order = st.selectbox(
                "顺序",
                options=("asc", "desc"),
                format_func={"asc": "升序", "desc": "降序"}.get,
                key=STATE_KEYS["library_order"],
            )
        filters_submitted = st.form_submit_button("应用筛选", width="stretch")
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
    if not repositories:
        st.session_state[STATE_KEYS["selected_repository_ids"]] = []
        st.info("分析库为空。前往“仓库发现”搜索并添加公开仓库。")
        return

    pending_id = st.session_state[STATE_KEYS["pending_delete_repository_id"]]
    if pending_id is not None:
        repository = next((item for item in repositories if item.repository_id == pending_id), None)
        name = repository.full_name if repository else f"仓库 ID {pending_id}"
        st.warning(f"确认从我的分析库移除 {name}？这只移除成员关系，不删除仓库快照、历史或研究样本。")
        confirm, cancel, _ = st.columns([1, 1, 5])
        if confirm.button("确认移除", type="primary"):
            try:
                client.remove_from_library(int(pending_id))
                st.session_state[STATE_KEYS["pending_delete_repository_id"]] = None
                st.success("已从我的分析库移除。")
                st.rerun()
            except APIError as error:
                render_api_error(error)
        if cancel.button("取消"):
            st.session_state[STATE_KEYS["pending_delete_repository_id"]] = None
            st.rerun()

    name_by_id = {item.repository_id: item.full_name for item in repositories}
    current_selection = st.session_state[STATE_KEYS["selected_repository_ids"]]
    current_selection = [repo_id for repo_id in current_selection if repo_id in name_by_id]
    st.session_state[STATE_KEYS["selected_repository_ids"]] = current_selection
    selected = st.multiselect(
        "选择 2–5 个仓库加入比较",
        options=list(name_by_id),
        format_func=lambda repo_id: name_by_id[repo_id],
        max_selections=5,
        key=STATE_KEYS["selected_repository_ids"],
    )
    if st.button("加入项目对比", type="primary", disabled=not 2 <= len(selected) <= 5):
        st.switch_page("pages/comparison.py")

    for repository in repositories:
        with st.container(border=True):
            heading, metrics = st.columns([3, 3])
            with heading:
                st.subheader(repository.full_name)
                st.caption(repository.description or "暂无简介")
                st.caption(f"语言：{repository.language or '未知'} · {DATA_STATUS_LABELS[repository.data_status]}")
            with metrics:
                left, right, collected = st.columns(3)
                left.metric("Stars", display_value(repository.stars))
                right.metric("Forks", display_value(repository.forks))
                collected.metric("最近采集", _format_datetime(repository.last_successful_collection_at))
            st.caption(f"分析状态：{STATUS_LABELS[repository.analysis_status]}")
            details, refresh, deep, remove, task = st.columns(5)
            if details.button("查看详情", key=f"detail-{repository.repository_id}"):
                st.session_state[STATE_KEYS["repository_id"]] = repository.repository_id
                st.switch_page(
                    "pages/repository.py",
                    query_params={"repository_id": str(repository.repository_id)},
                )
            if refresh.button("基础刷新", key=f"refresh-{repository.repository_id}"):
                try:
                    result = client.refresh_repository(
                        repository.repository_id,
                        depth="basic",
                        idempotency_key=str(uuid4()),
                    ).data
                    st.session_state[STATE_KEYS["task_id"]] = result.task_id
                    st.session_state[STATE_KEYS["task_poll_complete_for"]] = None
                    st.session_state[STATE_KEYS["task_poll_error_for"]] = None
                    st.toast(format_refresh_result(result, "基础刷新"))
                except APIError as error:
                    render_api_error(error)
            if deep.button("深度采集", key=f"deep-{repository.repository_id}"):
                try:
                    result = client.refresh_repository(
                        repository.repository_id,
                        depth="deep",
                        idempotency_key=str(uuid4()),
                    ).data
                    st.session_state[STATE_KEYS["task_id"]] = result.task_id
                    st.session_state[STATE_KEYS["task_poll_complete_for"]] = None
                    st.session_state[STATE_KEYS["task_poll_error_for"]] = None
                    st.toast(format_refresh_result(result, "深度采集"))
                except APIError as error:
                    render_api_error(error)
            if remove.button("移除", key=f"remove-{repository.repository_id}"):
                st.session_state[STATE_KEYS["pending_delete_repository_id"]] = repository.repository_id
                st.rerun()
            if repository.latest_task_id and task.button("查看任务", key=f"task-{repository.repository_id}"):
                st.session_state[STATE_KEYS["task_id"]] = repository.latest_task_id

    task_id = st.session_state[STATE_KEYS["task_id"]]
    if task_id:
        st.subheader("最近任务")
        _show_task(client, task_id)

    pagination = response.meta.pagination
    if pagination and (pagination.page > 1 or pagination.has_next):
        previous, label, next_page = st.columns([1, 2, 1])
        if previous.button("上一页", disabled=pagination.page <= 1):
            st.session_state[STATE_KEYS["library_page"]] = pagination.page - 1
            st.rerun()
        label.caption(f"第 {pagination.page} 页 · 共 {pagination.total or 0} 项")
        if next_page.button("下一页", disabled=not pagination.has_next):
            st.session_state[STATE_KEYS["library_page"]] = pagination.page + 1
            st.rerun()


render()

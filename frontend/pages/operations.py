from __future__ import annotations

import streamlit as st

from frontend.api.errors import APIError
from frontend.api.factory import get_api_client
from frontend.components.feedback import render_api_error
from frontend.components.page_header import render_page_header
from frontend.components.status_indicator import status_label
from frontend.components.task_summary import render_task_panel
from frontend.state.keys import STATE_KEYS


TASK_STATUSES = ("succeeded", "partial", "failed", "cancelled")
PHASE_LABELS = {
    "collecting": "采集数据",
    "cleaning": "整理数据",
    "analyzing": "分析数据",
    "persisting": "保存结果",
}


def _task_progress_label(task: object) -> str:
    if task.attempt == 0 and task.status == "queued":
        return "尚未启动"
    if task.progress_kind == "stages" and task.progress_percent is not None:
        return f"阶段进度 {task.progress_percent:g}%"
    if task.phase:
        return f"阶段：{PHASE_LABELS.get(task.phase, '阶段未知')}"
    return "等待进度更新"


def _open_task(task_id: str) -> None:
    st.session_state[STATE_KEYS["task_id"]] = task_id
    st.session_state[STATE_KEYS["task_poll_error_for"]] = None
    st.session_state[STATE_KEYS["task_poll_complete_for"]] = None
    st.rerun()


def _render_system_status(client: object) -> None:
    with st.expander("系统与队列状态"):
        try:
            status = client.system_status().data
        except APIError as error:
            st.warning(f"系统状态暂不可用：{error.user_message}")
            return

        first, second, third = st.columns(3)
        first.metric("API", status_label(status.api))
        second.metric("数据库", status_label(status.database))
        third.metric("Worker", status_label(status.worker))
        st.caption(
            f"队列：{status.queue.queued} 个待处理 · {status.queue.running} 个运行中 · "
            f"{status.queue.failed} 个失败"
        )
        if status.worker != "ok":
            st.warning("Worker 心跳不可用或已过期；已有分析数据仍可以查看。")
        if status.worker_last_heartbeat_at:
            st.caption(f"Worker 最近心跳：{status.worker_last_heartbeat_at.isoformat()}")
        quota = status.github
        if quota.rate_limit_remaining is None:
            st.caption("GitHub 配额：未获取配额数据。")
        else:
            reset = quota.rate_limit_reset_at.isoformat() if quota.rate_limit_reset_at else "重置时间未知"
            st.caption(f"GitHub 剩余配额：{quota.rate_limit_remaining} · {reset}")


def _render_history(client: object) -> None:
    with st.expander("历史任务"):
        with st.form("task-filters"):
            status_filter, repository_filter = st.columns(2)
            task_status = status_filter.selectbox(
                "任务状态",
                options=("", *TASK_STATUSES),
                format_func=lambda value: "全部终态" if not value else status_label(value),
                key=STATE_KEYS["task_status_filter"],
            )
            repository_input = repository_filter.text_input(
                "仓库 ID（可选）",
                key=STATE_KEYS["task_repository_filter"],
            )
            filters_submitted = st.form_submit_button("应用筛选")
        if filters_submitted:
            st.session_state[STATE_KEYS["task_page"]] = 1

        repository_id = None
        if repository_input.strip():
            try:
                repository_id = int(repository_input)
            except ValueError:
                st.warning("仓库 ID 必须是整数。")
                return
        try:
            response = client.list_tasks(
                status=task_status or None,
                repository_id=repository_id,
                page=st.session_state[STATE_KEYS["task_page"]],
                per_page=20,
            )
        except APIError as error:
            render_api_error(error)
            return

        if not response.data.items:
            st.info("当前筛选没有历史任务。")
            return

        for task in response.data.items:
            left, right = st.columns([5, 1])
            left.write(
                f"仓库 #{task.repository_id} · {'深度' if task.depth == 'deep' else '基础'} · "
                f"{status_label(task.status)}"
            )
            left.caption(f"{task.created_at.isoformat()} · {_task_progress_label(task)}")
            if right.button("打开", key=f"open-task-{task.task_id}"):
                _open_task(task.task_id)

        pagination = response.meta.pagination
        if pagination and (pagination.page > 1 or pagination.has_next):
            previous, label, next_page = st.columns([1, 2, 1])
            if previous.button("上一页", disabled=pagination.page <= 1):
                st.session_state[STATE_KEYS["task_page"]] = pagination.page - 1
                st.rerun()
            label.caption(
                f"第 {pagination.page} 页 · 共 {pagination.total if pagination.total is not None else '未知'} 项"
            )
            if next_page.button("下一页", disabled=not pagination.has_next):
                st.session_state[STATE_KEYS["task_page"]] = pagination.page + 1
                st.rerun()


def render() -> None:
    render_page_header("任务中心", "查看排队、运行中和历史任务；进度与数据覆盖分别说明。")
    client, _ = get_api_client()
    _render_system_status(client)

    active_tasks = []
    active_total = 0
    try:
        for task_status in ("running", "queued"):
            response = client.list_tasks(status=task_status, page=1, per_page=50)
            active_tasks.extend(response.data.items)
            active_total += (
                response.meta.pagination.total
                if response.meta.pagination and response.meta.pagination.total is not None
                else len(response.data.items)
            )
    except APIError as error:
        render_api_error(error)

    active_tasks.sort(key=lambda task: task.created_at, reverse=True)
    st.subheader(f"进行中与排队 · {active_total}")
    if not active_tasks:
        st.info("当前没有排队或运行中的任务。")
    else:
        for task in active_tasks[:10]:
            left, right = st.columns([5, 1])
            left.write(
                f"仓库 #{task.repository_id} · {'深度' if task.depth == 'deep' else '基础'} · "
                f"{status_label(task.status)}"
            )
            left.caption(
                _task_progress_label(task) +
                (f" · {task.message}" if task.message else "")
            )
            if right.button("查看", key=f"active-task-{task.task_id}"):
                st.session_state[STATE_KEYS["task_id"]] = task.task_id
                st.session_state[STATE_KEYS["task_poll_error_for"]] = None
                st.session_state[STATE_KEYS["task_poll_complete_for"]] = None
                st.rerun()

    selected_task_id = st.session_state[STATE_KEYS["task_id"]]
    if selected_task_id is None and active_tasks:
        selected_task_id = active_tasks[0].task_id
        st.session_state[STATE_KEYS["task_id"]] = selected_task_id
    if selected_task_id:
        st.subheader("选中任务")
        render_task_panel(client, selected_task_id)

    _render_history(client)


render()

"""Shared task progress rendering with compatibility-safe polling."""

from __future__ import annotations

from uuid import uuid4

import streamlit as st

from frontend.api.errors import APIError
from frontend.api.models import Task, TaskModuleProgress
from frontend.components.status_indicator import status_label
from frontend.state.keys import STATE_KEYS


ACTIVE_STATUSES = {"queued", "running"}
TERMINAL_STATUSES = {"succeeded", "partial", "failed", "cancelled"}
PHASE_LABELS = {
    "collecting": "采集数据",
    "cleaning": "整理数据",
    "analyzing": "分析数据",
    "persisting": "保存结果",
}
MODULE_LABELS = {
    "profile": "仓库资料",
    "commits": "Commits",
    "issues": "Issues",
    "pulls": "Pull Requests",
    "releases": "Releases",
}
MODULE_STATUS_LABELS = {
    "pending": "尚未开始",
    "running": "正在获取",
    "complete": "已完成",
    "partial": "部分完成",
    "failed": "失败",
    "skipped": "已跳过",
}
COVERAGE_LABELS = {
    "complete": "完整",
    "partial": "不完整",
    "not_collected": "尚未采集",
    "unknown": "未知",
}


def _render_module(module: TaskModuleProgress) -> None:
    name = MODULE_LABELS[module.name]
    state = MODULE_STATUS_LABELS[module.status]
    cap = f" / 页数上限 {module.page_cap}" if module.page_cap is not None else ""
    elapsed = "" if module.elapsed_seconds is None else f" · 耗时 {module.elapsed_seconds:.1f} 秒"
    st.caption(
        f"{name} · {state} · 已处理 {module.pages_fetched} 页{cap} · "
        f"观察到 {module.observed_items} 条 · 覆盖 {COVERAGE_LABELS[module.coverage]}{elapsed}"
    )
    if module.error_code:
        st.caption(f"{name}错误码：{module.error_code}")


def render_task_summary(task: Task) -> None:
    depth = "深度分析" if task.depth == "deep" else "基础分析"
    st.markdown(f"**{depth} · {status_label(task.status)}**")

    if task.attempt == 0 and task.status == "queued":
        st.caption("已排队，尚未启动。")
    else:
        phase = PHASE_LABELS.get(task.phase, "阶段未知") if task.phase else "阶段未知"
        current_module = MODULE_LABELS.get(task.current_module) if task.current_module else None
        if task.status in ACTIVE_STATUSES:
            running_at = f" · 当前模块：{current_module}" if current_module else ""
            st.caption(f"{phase}{running_at} · {task.message or '等待状态更新'}")
        elif task.message:
            st.caption(task.message)

    if task.attempt > 0:
        if task.progress_kind == "stages" and task.progress_percent is not None:
            st.progress(
                task.progress_percent / 100,
                text=f"阶段进度 {task.progress_percent:g}% · 不代表数据覆盖率",
            )
        elif task.status in ACTIVE_STATUSES:
            st.caption("阶段进度暂不可用；不会用分页数量估算完成百分比。")
        if task.status in ACTIVE_STATUSES and task.eta_seconds is None:
            st.caption("完成时间暂不可估计。")
        if task.elapsed_seconds is not None:
            st.caption(f"已运行 {task.elapsed_seconds:.1f} 秒。")
        if task.progress_updated_at:
            st.caption(f"进度更新时间：{task.progress_updated_at.isoformat()}")

    if task.modules:
        with st.container(border=True):
            st.markdown("**模块进度**")
            for module in task.modules:
                _render_module(module)
    elif task.depth == "deep" and task.status in ACTIVE_STATUSES:
        st.caption("模块明细尚未由当前 API 提供；请以任务阶段和状态为准。")

    if task.status == "succeeded":
        st.caption("任务已结束。此状态不代表覆盖了 GitHub 上的全部历史数据。")
    elif task.status == "partial":
        st.warning("本次任务部分完成；请按模块覆盖状态判断哪些指标可用。")
    elif task.status == "failed":
        code = (task.error or {}).get("code")
        if code:
            message = APIError(status_code=0, code=str(code)).user_message
            st.error(f"任务失败：{message}（{code}）")
        else:
            st.error("任务失败，后端未提供可安全显示的错误说明。")
    elif task.status == "cancelled":
        st.info("任务已取消；已保存的结果仍按其覆盖状态展示。")


def render_task_panel(client: object, task_id: str) -> Task | None:
    if st.session_state[STATE_KEYS["task_poll_error_for"]] == task_id:
        st.warning("任务状态查询失败，自动轮询已暂停。")
        if st.button("重新查询任务", key=f"refresh-task-{task_id}"):
            st.session_state[STATE_KEYS["task_poll_error_for"]] = None
            st.rerun()
        return None

    try:
        task = client.task_detail(task_id).data
    except APIError as error:
        st.session_state[STATE_KEYS["task_poll_error_for"]] = task_id
        st.error(error.user_message)
        if st.button("重新查询任务", key=f"refresh-task-{task_id}"):
            st.session_state[STATE_KEYS["task_poll_error_for"]] = None
            st.rerun()
        return None

    with st.expander("任务编号"):
        st.code(task.task_id)

    if task.status == "queued":
        if st.button("刷新任务状态", key=f"refresh-queued-task-{task_id}"):
            st.rerun()

    if task.status == "running":
        first_run = [True]

        @st.fragment(run_every="3s")
        def poll_task() -> None:
            if first_run[0]:
                first_run[0] = False
                render_task_summary(task)
                return
            try:
                latest = client.task_detail(task_id).data
            except APIError as error:
                st.session_state[STATE_KEYS["task_poll_error_for"]] = task_id
                st.error(error.user_message)
                st.rerun(scope="app")
                return
            render_task_summary(latest)
            if latest.status in TERMINAL_STATUSES:
                st.session_state[STATE_KEYS["task_poll_complete_for"]] = task_id
                st.rerun(scope="app")

        poll_task()
    else:
        render_task_summary(task)

    if task.status in {"failed", "partial"}:
        if st.button("重试此任务", key=f"retry-task-{task_id}", type="primary"):
            try:
                retry = client.retry_task(task_id, idempotency_key=str(uuid4())).data
            except APIError as error:
                st.error(error.user_message)
            else:
                st.session_state[STATE_KEYS["task_id"]] = retry.task_id
                st.session_state[STATE_KEYS["task_poll_complete_for"]] = None
                st.session_state[STATE_KEYS["task_poll_error_for"]] = None
                st.rerun()
    return task

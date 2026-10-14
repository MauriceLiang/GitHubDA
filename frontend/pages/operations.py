from uuid import uuid4

import streamlit as st

from frontend.api.errors import APIError
from frontend.api.factory import get_api_client
from frontend.components.feedback import render_api_error
from frontend.state.keys import STATE_KEYS


TASK_STATUSES = ("queued", "running", "succeeded", "partial", "failed", "cancelled")
TERMINAL_TASK_STATUSES = {"succeeded", "partial", "failed", "cancelled"}


@st.fragment(run_every="3s")
def _render_selected_task(task_id: str) -> None:
    if st.session_state[STATE_KEYS["task_poll_complete_for"]] == task_id:
        st.caption("此任务已结束，自动轮询已停止。")
        return
    if st.session_state[STATE_KEYS["task_poll_error_for"]] == task_id:
        st.caption("任务状态查询失败；自动轮询已暂停，请手动重新选择任务。")
        return

    client, _ = get_api_client()
    try:
        task = client.task_detail(task_id).data
    except APIError as error:
        render_api_error(error)
        st.session_state[STATE_KEYS["task_poll_error_for"]] = task_id
        return

    status_labels = {
        "queued": "排队中",
        "running": "运行中",
        "succeeded": "已完成",
        "partial": "部分完成",
        "failed": "失败",
        "cancelled": "已取消",
    }
    st.write(f"仓库 ID：{task.repository_id} · {status_labels[task.status]} · 尝试次数：{task.attempt}")
    st.caption(f"阶段：{task.phase or '—'} · {task.message or '无状态消息'}")
    if task.progress_percent is None:
        if task.status in {"queued", "running"}:
            st.status("任务正在执行；后端没有提供可靠的百分比。", state="running", expanded=False)
    else:
        st.progress(task.progress_percent / 100, text=f"{task.progress_percent:g}%")
    if task.error:
        st.error(str(task.error.get("code") or task.error.get("message") or "任务失败"))

    if task.status in TERMINAL_TASK_STATUSES:
        st.session_state[STATE_KEYS["task_poll_complete_for"]] = task_id
    if task.status in {"failed", "partial"} and st.button("重试此任务", key=f"retry-{task_id}", type="primary"):
        try:
            retry = client.retry_task(task_id, idempotency_key=str(uuid4())).data
            st.session_state[STATE_KEYS["task_id"]] = retry.task_id
            st.session_state[STATE_KEYS["task_poll_complete_for"]] = None
            st.session_state[STATE_KEYS["task_poll_error_for"]] = None
            st.rerun()
        except APIError as error:
            render_api_error(error)

def render() -> None:
    st.header("数据与任务")
    client, _ = get_api_client()
    try:
        status = client.system_status().data
    except APIError as error:
        render_api_error(error)
        status = None

    if status is not None:
        api_state, worker_state, queue = st.columns(3)
        api_state.metric("API", status.api)
        worker_state.metric("Worker", status.worker)
        queue.metric("排队 / 运行 / 失败", f"{status.queue.queued} / {status.queue.running} / {status.queue.failed}")
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

    with st.form("task-filters"):
        status_filter, repository_filter = st.columns(2)
        with status_filter:
            task_status = st.selectbox(
                "任务状态",
                options=("", *TASK_STATUSES),
                format_func=lambda value: "全部" if not value else value,
                key=STATE_KEYS["task_status_filter"],
            )
        with repository_filter:
            repository_input = st.text_input("仓库 ID（可选）", key=STATE_KEYS["task_repository_filter"])
        filters_submitted = st.form_submit_button("刷新任务列表", use_container_width=True)
    if filters_submitted:
        st.session_state[STATE_KEYS["task_page"]] = 1

    repository_id = None
    if repository_input.strip():
        try:
            repository_id = int(repository_input)
        except ValueError:
            st.warning("仓库 ID 必须是整数。")
    try:
        task_response = client.list_tasks(
            status=task_status or None,
            repository_id=repository_id,
            page=st.session_state[STATE_KEYS["task_page"]],
            per_page=20,
        )
    except APIError as error:
        render_api_error(error)
        task_response = None

    if task_response:
        tasks = task_response.data.items
        if not tasks:
            st.info("当前筛选没有任务。")
        else:
            st.dataframe(
                [
                    {
                        "Task ID": task.task_id,
                        "Repository ID": task.repository_id,
                        "状态": task.status,
                        "阶段": task.phase or "—",
                        "进度": "未提供" if task.progress_percent is None else f"{task.progress_percent:g}%",
                        "创建时间": task.created_at.isoformat(),
                        "失败码": (task.error or {}).get("code", "—"),
                    }
                    for task in tasks
                ],
                hide_index=True,
                use_container_width=True,
            )
            for task in tasks:
                if st.button("查看并轮询", key=f"open-task-{task.task_id}"):
                    st.session_state[STATE_KEYS["task_id"]] = task.task_id
                    st.session_state[STATE_KEYS["task_poll_complete_for"]] = None
                    st.session_state[STATE_KEYS["task_poll_error_for"]] = None
            pagination = task_response.meta.pagination
            if pagination and (pagination.page > 1 or pagination.has_next):
                previous, label, next_page = st.columns([1, 2, 1])
                if previous.button("上一页", disabled=pagination.page <= 1):
                    st.session_state[STATE_KEYS["task_page"]] = pagination.page - 1
                    st.rerun()
                label.caption(f"第 {pagination.page} 页 · 共 {pagination.total or 0} 项")
                if next_page.button("下一页", disabled=not pagination.has_next):
                    st.session_state[STATE_KEYS["task_page"]] = pagination.page + 1
                    st.rerun()

    task_id = st.session_state[STATE_KEYS["task_id"]]
    if task_id:
        st.subheader("选中任务状态")
        _render_selected_task(task_id)

    st.subheader("导出 CSV")
    try:
        datasets = client.datasets().data.items
    except APIError as error:
        datasets = []
        st.warning(f"数据集列表暂不可用：{error.user_message}")
    research_datasets = [dataset for dataset in datasets if dataset.type == "research"]
    with st.form("csv-export"):
        scope = st.selectbox(
            "导出范围",
            options=("research", "library"),
            format_func={"research": "固定研究样本", "library": "我的分析库"}.get,
            key=STATE_KEYS["export_scope"],
        )
        dataset_id = None
        if scope == "research":
            if research_datasets:
                ids = [dataset.dataset_id for dataset in research_datasets]
                if st.session_state[STATE_KEYS["export_dataset_id"]] not in ids:
                    st.session_state[STATE_KEYS["export_dataset_id"]] = ids[0]
                dataset_id = st.selectbox("研究样本版本", options=ids, key=STATE_KEYS["export_dataset_id"])
            else:
                st.warning("没有可用的研究数据集。")
        language = st.text_input("语言筛选（可选）", key=STATE_KEYS["export_language"])
        export_clicked = st.form_submit_button("准备导出", type="primary", disabled=scope == "research" and dataset_id is None)
    if export_clicked:
        try:
            st.session_state[STATE_KEYS["export_payload"]] = client.export_repositories_csv(
                scope, dataset_id=dataset_id, language=language.strip() or None
            )
        except APIError as error:
            render_api_error(error)
    export_payload = st.session_state[STATE_KEYS["export_payload"]]
    if export_payload:
        st.download_button(
            "下载 CSV",
            data=export_payload.content,
            file_name=export_payload.filename,
            mime=export_payload.content_type,
        )

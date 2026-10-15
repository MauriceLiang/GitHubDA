from __future__ import annotations

from datetime import datetime

import streamlit as st

from frontend.api.errors import APIError
from frontend.api.factory import get_api_client
from frontend.charts.distributions import distribution_figure
from frontend.charts.theme import language_color, theme_options
from frontend.components.empty_state import render_empty_state
from frontend.components.feedback import display_value, render_api_error
from frontend.components.metadata_panel import render_metadata_panel
from frontend.components.page_header import render_page_header
from frontend.components.repository_input import render_repository_input
from frontend.components.status_indicator import status_label
from frontend.repository_flow import open_repository, start_repository_analysis
from frontend.state.keys import STATE_KEYS


def _format_datetime(value: datetime | None) -> str:
    return value.astimezone().strftime("%Y-%m-%d") if value and value.tzinfo else (
        value.date().isoformat() if value else "—"
    )


def _open_task(task_id: str) -> None:
    st.session_state[STATE_KEYS["task_id"]] = task_id
    st.session_state[STATE_KEYS["task_poll_error_for"]] = None
    st.switch_page("pages/operations.py")


def render() -> None:
    render_page_header(
        "分析任何公开 GitHub 仓库",
        "输入 owner/repo 或仓库链接，开始基础分析并直接查看结果。",
    )
    client, _ = get_api_client()
    repository_input, submitted = render_repository_input()
    st.page_link("pages/explore.py", label="更多筛选 / 搜索项目")
    if submitted:
        if not repository_input.strip():
            st.error("请输入 GitHub 仓库地址或 owner/repo。")
        else:
            try:
                with st.spinner("正在验证仓库并准备基础分析…"):
                    preview = client.resolve_repository(repository_input.strip()).data
                    start = start_repository_analysis(client, preview)
            except APIError as error:
                render_api_error(error)
            else:
                open_repository(start)

    try:
        library = client.list_library(page=1, per_page=5, sort="last_collected", order="desc")
    except APIError as error:
        render_api_error(error)
        return

    if not library.data.items and (library.meta.pagination is None or library.meta.pagination.total in {None, 0}):
        render_empty_state(
            "最近仓库",
            "分析库还没有仓库。使用上方输入框开始分析；也可以先搜索候选项目。",
        )
        return

    try:
        overview = client.overview("library").data
        queued = client.list_tasks(status="queued", page=1, per_page=20)
        running = client.list_tasks(status="running", page=1, per_page=20)
    except APIError as error:
        render_api_error(error)
        return

    total = (
        library.meta.pagination.total
        if library.meta.pagination and library.meta.pagination.total is not None
        else overview.kpis.repositories_total
    )
    active_count = sum(
        response.meta.pagination.total
        if response.meta.pagination and response.meta.pagination.total is not None
        else len(response.data.items)
        for response in (queued, running)
    )
    latest_collected = next(
        (item.last_successful_collection_at for item in library.data.items if item.last_successful_collection_at),
        None,
    )
    first, second, third, fourth = st.columns(4)
    first.metric("分析库仓库", total)
    second.metric("已采集仓库", overview.kpis.repositories_analyzed)
    third.metric("排队或运行任务", active_count)
    fourth.metric("最近采集", _format_datetime(latest_collected))

    active_tasks = sorted(
        [*queued.data.items, *running.data.items],
        key=lambda task: task.created_at,
        reverse=True,
    )
    if active_tasks:
        st.subheader("待处理任务")
        for task in active_tasks[:5]:
            left, right = st.columns([5, 1])
            left.write(
                f"仓库 #{task.repository_id} · {'深度' if task.depth == 'deep' else '基础'} · "
                f"{status_label(task.status)}"
            )
            if task.message:
                left.caption(task.message)
            if right.button("查看", key=f"dashboard-task-{task.task_id}"):
                _open_task(task.task_id)
    if library.data.items:
        st.subheader("最近仓库")
        for repository in library.data.items[:5]:
            left, right = st.columns([5, 1])
            left.write(repository.full_name)
            left.caption(
                f"{repository.language or '语言未知'} · "
                f"Stars {display_value(repository.stars)} · "
                f"{status_label(repository.analysis_status)}"
            )
            if right.button("查看分析", key=f"dashboard-repository-{repository.repository_id}"):
                open_repository(repository.repository_id)

    distributions = overview.language_distribution or overview.stars_distribution
    if distributions:
        st.subheader("分析库分布")
        left, right = st.columns(2)
        theme = st.session_state[STATE_KEYS["chart_theme"]]
        options = theme_options(theme)
        if overview.language_distribution:
            try:
                figure = distribution_figure(
                    [item.language for item in overview.language_distribution],
                    [item.count for item in overview.language_distribution],
                    title="语言样本分布",
                    theme=theme,
                    colors=[language_color(item.language, theme) for item in overview.language_distribution],
                )
                left.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
                left.caption(f"有效分析样本 n={overview.kpis.repositories_analyzed}")
            except ImportError:
                left.error("当前环境未安装 Plotly；请按项目安装说明安装前端依赖。")
        if overview.stars_distribution:
            try:
                figure = distribution_figure(
                    [item.bucket for item in overview.stars_distribution],
                    [item.count for item in overview.stars_distribution],
                    title="Star 区间分布",
                    theme=theme,
                )
                figure.update_traces(marker_color=options["palette"][0])
                right.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
                right.caption(f"有效分析样本 n={overview.kpis.repositories_analyzed}")
            except ImportError:
                right.error("当前环境未安装 Plotly；请按项目安装说明安装前端依赖。")
    else:
        st.info("分析库中还没有可绘制的基础快照；未采集仓库不会被当作零值。")

    render_metadata_panel(overview.source_metadata)


render()

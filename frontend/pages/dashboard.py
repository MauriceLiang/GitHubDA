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
from frontend.components.status_indicator import status_label
from frontend.state.keys import STATE_KEYS


def _format_datetime(value: datetime | None) -> str:
    return value.astimezone().strftime("%Y-%m-%d") if value and value.tzinfo else (
        value.date().isoformat() if value else "—"
    )


def _open_repository(repository_id: int) -> None:
    st.session_state[STATE_KEYS["repository_id"]] = repository_id
    st.switch_page("pages/repository.py", query_params={"repository_id": str(repository_id)})


def _open_task(task_id: str) -> None:
    st.session_state[STATE_KEYS["task_id"]] = task_id
    st.session_state[STATE_KEYS["task_poll_error_for"]] = None
    st.switch_page("pages/operations.py")


def render() -> None:
    render_page_header(
        "工作台",
        "从分析库查看最近状态，或搜索一个公开仓库开始分析。",
    )
    client, _ = get_api_client()
    try:
        library = client.list_library(page=1, per_page=10, sort="last_collected", order="desc")
    except APIError as error:
        render_api_error(error)
        return

    if not library.data.items and (library.meta.pagination is None or library.meta.pagination.total in {None, 0}):
        render_empty_state(
            "分析库还没有仓库",
            "把公开仓库加入分析库后，就能在这里查看基础指标、采集状态和比较结果。",
            action_label="搜索并添加仓库",
            target="pages/explore.py",
            steps=("搜索仓库", "加入分析库", "查看分析结果"),
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
    else:
        st.caption("当前没有排队或运行中的任务。")

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
                _open_repository(repository.repository_id)

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

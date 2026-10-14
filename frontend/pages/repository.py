from uuid import uuid4

import streamlit as st

from frontend.api.errors import APIError
from frontend.api.factory import get_api_client
from frontend.charts.time_series import time_series_figure
from frontend.components.feedback import display_value, format_refresh_result, render_api_error
from frontend.components.metadata_panel import render_metadata_panel
from frontend.components.page_header import render_page_header
from frontend.components.status_indicator import status_label
from frontend.components.task_summary import render_task_panel
from frontend.state.keys import STATE_KEYS


MODULE_NAMES = {
    "profile": "仓库资料",
    "activity": "维护活动",
    "community": "社区协作",
    "commits": "Commits",
    "issues": "Issues",
    "pulls": "Pull Requests",
    "releases": "Releases",
}


def _start_deep_analysis(client: object, repository_id: int) -> None:
    try:
        result = client.refresh_repository(
            repository_id,
            depth="deep",
            idempotency_key=str(uuid4()),
        ).data
    except APIError as error:
        render_api_error(error)
        return
    st.session_state[STATE_KEYS["task_id"]] = result.task_id
    st.session_state[STATE_KEYS["task_poll_complete_for"]] = None
    st.session_state[STATE_KEYS["task_poll_error_for"]] = None
    st.toast(format_refresh_result(result, "深度分析"))
    st.rerun()


def _render_history(client: object, repository_id: int) -> None:
    with st.expander("历史趋势"):
        metric = st.selectbox(
            "历史指标",
            options=("stars", "forks"),
            format_func={"stars": "Stars", "forks": "Forks"}.get,
            key=STATE_KEYS["repository_metric"],
        )
        try:
            series = client.repository_series(repository_id, metric).data
        except APIError as error:
            render_api_error(error)
            return
        st.caption(f"观测点 n={series.observed_days}。历史接口不补值、不插值。")
        if series.note:
            st.caption(series.note)
        if len(series.points) < 2:
            if series.points:
                st.info("目前只有一个真实观测点，不绘制增长曲线。")
                st.write(f"{series.points[0].date.isoformat()}：{series.points[0].value:,}")
            else:
                st.info("暂无历史采集点。")
        else:
            points = [(item.date.isoformat(), item.value) for item in series.points]
            try:
                figure = time_series_figure(
                    points,
                    metric="Stars" if metric == "stars" else "Forks",
                    theme=st.session_state.get(STATE_KEYS["chart_theme"], "dark"),
                )
                st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
            except ImportError:
                st.error("当前环境未安装 Plotly；请按项目安装说明安装前端依赖。")
        st.dataframe(
            [{"采集日期": item.date.isoformat(), "观测值": item.value} for item in series.points],
            hide_index=True,
        )


def render() -> None:
    render_page_header("仓库详情", "基础指标、深度采集状态和数据覆盖集中在当前页面。")
    repository_id = st.query_params.get("repository_id") or st.session_state.get(STATE_KEYS["repository_id"])
    if not repository_id:
        st.info("从我的分析库选择一个仓库后可查看详情。")
        st.page_link("pages/library.py", label="返回我的分析库")
        return
    try:
        repository_id = int(repository_id)
    except (TypeError, ValueError):
        st.error("仓库 ID 格式无效。")
        return

    client, _ = get_api_client()
    try:
        detail = client.repository_detail(repository_id).data
    except APIError as error:
        render_api_error(error)
        return

    repository = detail.repository
    st.page_link("pages/library.py", label="返回我的分析库")
    st.subheader(repository.full_name)
    st.caption(repository.description or "暂无简介")
    st.caption(f"语言：{repository.language or '未知'} · 数据状态：{status_label(repository.data_status)}")
    st.link_button("在 GitHub 打开", detail.html_url)
    if repository.data_status == "stale":
        st.warning("当前展示的是上次成功采集的快照。")

    try:
        basic = client.repository_analysis(repository_id, depth="basic").data
    except APIError as error:
        basic = None
        st.warning(f"基础分析暂不可用：{error.user_message}")
    try:
        deep = client.repository_analysis(repository_id, depth="deep").data
    except APIError as error:
        deep = None
        st.warning(f"深度分析暂不可用：{error.user_message}")

    basic_metrics = basic.metrics if basic else None
    first, second, third, fourth = st.columns(4)
    first.metric("Stars", display_value(repository.stars))
    second.metric("Forks", display_value(repository.forks))
    third.metric("仓库年龄（天）", display_value(basic_metrics.age_days if basic_metrics else None))
    fourth.metric("距最近推送（天）", display_value(basic_metrics.days_since_push if basic_metrics else None))
    collected = repository.last_successful_collection_at
    st.caption(
        "基础快照最近采集：" +
        (collected.astimezone().strftime("%Y-%m-%d %H:%M") if collected and collected.tzinfo else
         collected.isoformat() if collected else "尚未采集")
    )

    task_id = repository.latest_task_id
    if task_id is None and st.session_state[STATE_KEYS["repository_id"]] == repository_id:
        task_id = st.session_state[STATE_KEYS["task_id"]]
    latest_task = None
    if task_id:
        st.subheader("最近采集任务")
        latest_task = render_task_panel(client, task_id)

    st.subheader("深度分析")
    deep_status = deep.analysis_status if deep else "missing"
    if deep and deep_status == "completed" and deep.modules:
        collected_modules = [
            module.coverage for name, module in deep.modules.items()
            if name not in {"profile"} and module.coverage != "not_collected"
        ]
        if not collected_modules:
            deep_status = "not_started"
    task_is_active = bool(latest_task and latest_task.status in {"queued", "running"})
    if deep_status == "not_started" or deep_status == "missing":
        st.info("深度分析可补充 Commit、Release、Issue 和 Pull Request 的近期活动指标。")
    elif deep_status == "queued":
        st.info("深度分析已排队，等待 Worker 开始处理。")
    elif deep_status == "processing":
        st.info("深度分析正在运行；模块状态以任务摘要为准。")
    elif deep_status == "partial":
        st.warning("深度分析已结束，但部分模块或分页覆盖不完整。")
    elif deep_status == "failed":
        st.warning("最近一次深度分析失败；已有成功快照仍可查看。")
    elif deep_status == "completed":
        st.caption("深度分析任务已结束；下方指标只表示 API 返回的观察结果。")

    if not task_is_active and deep_status not in {"queued", "processing"}:
        label = "重新进行深度分析" if deep_status == "completed" else "开始深度分析"
        if st.button(label, type="primary"):
            _start_deep_analysis(client, repository_id)

    if deep is None:
        st.info("当前无法读取深度分析结果。")
    else:
        metrics = deep.metrics
        first, second, third, fourth = st.columns(4)
        first.metric("近 90 天 Commit", display_value(metrics.commits_90d if metrics else None, missing="未采集"))
        second.metric("近一年 Release", display_value(metrics.release_count_365d if metrics else None, missing="未采集"))
        third.metric("近 90 天关闭 Issue", display_value(metrics.issues_closed_90d if metrics else None, missing="未采集"))
        fourth.metric("近 90 天合并 PR", display_value(metrics.pr_merged_90d if metrics else None, missing="未采集"))

        if deep.modules:
            st.markdown("**模块覆盖**")
            for module_name, module in deep.modules.items():
                label = MODULE_NAMES.get(module_name, module_name)
                st.caption(f"{label} · 覆盖：{module.coverage}")
        elif deep_status in {"queued", "processing"}:
            st.caption("模块进度尚未由当前 API 提供；不会根据请求数推算覆盖率。")

        render_metadata_panel(
            deep.source_metadata or (basic.source_metadata if basic else None) or detail.source_metadata,
            title="深度结果来源与时间窗口",
            limitations=deep.limitations,
        )

    with st.expander("仓库资料"):
        st.write(f"创建时间：{repository.created_at.isoformat() if repository.created_at else '未知'}")
        st.write(f"最近推送：{repository.pushed_at.isoformat() if repository.pushed_at else '未知'}")
        st.write(f"许可证：{detail.license_spdx or '未知'}")
        st.write(f"仓库大小：{display_value(detail.size_kb)} KB")
        st.write("主题：" + ("、".join(detail.topics) if detail.topics else "未提供"))
        render_metadata_panel(detail.source_metadata, title="基础资料来源")

    if st.checkbox("查看历史趋势", key=STATE_KEYS["repository_show_history"]):
        _render_history(client, repository_id)


render()

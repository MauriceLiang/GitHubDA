import streamlit as st

from frontend.api.errors import APIError
from frontend.api.factory import get_api_client
from frontend.charts.time_series import time_series_figure
from frontend.components.feedback import display_value, render_api_error, render_provenance
from frontend.state.keys import STATE_KEYS


def render() -> None:
    st.header("仓库详情")
    repository_id = st.query_params.get("repository_id") or st.session_state.get(STATE_KEYS["repository_id"])
    if not repository_id:
        st.info("从“我的分析库”打开仓库详情。")
        return
    try:
        repository_id = int(repository_id)
    except (TypeError, ValueError):
        st.error("仓库 ID 格式无效。")
        return

    client, _ = get_api_client()
    try:
        detail = client.repository_detail(repository_id).data
        analysis = client.repository_analysis(repository_id).data
    except APIError as error:
        render_api_error(error)
        return

    repository = detail.repository
    st.subheader(repository.full_name)
    st.caption(repository.description or "暂无简介")
    st.link_button("在 GitHub 打开", detail.html_url)
    if repository.data_status == "stale":
        st.warning("当前快照已过期；所示指标来自最近一次成功采集。")

    stars = repository.stars
    forks = repository.forks
    age = analysis.metrics.age_days if analysis.metrics else None
    pushed = analysis.metrics.days_since_push if analysis.metrics else None
    first, second, third, fourth = st.columns(4)
    first.metric("Stars", display_value(stars))
    second.metric("Forks", display_value(forks))
    third.metric("仓库年龄（天）", display_value(age))
    fourth.metric("距最近推送（天）", display_value(pushed))
    st.caption(f"分析状态：{analysis.analysis_status} · 数据状态：{repository.data_status} · 深度：{analysis.depth}")

    if st.button("开始深度分析", type="primary", disabled=analysis.analysis_status in {"queued", "processing"}):
        try:
            task = client.refresh_repository(repository_id, depth="deep").data
            st.session_state[STATE_KEYS["task_id"]] = task.task_id
            st.success(f"深度分析任务已{'复用' if task.reused else '排队'}：{task.task_id}")
        except APIError as error:
            render_api_error(error)

    overview_tab, activity_tab, community_tab, history_tab, info_tab = st.tabs(
        ["概览", "维护活动", "社区协作", "历史趋势", "指标说明"]
    )
    with overview_tab:
        st.write(f"创建时间：{repository.created_at.isoformat() if repository.created_at else '未知'}")
        st.write(f"最近推送：{repository.pushed_at.isoformat() if repository.pushed_at else '未知'}")
        st.write(f"许可证：{detail.license_spdx or '未知'}")
        st.write(f"仓库大小：{display_value(detail.size_kb)} KB")
        st.write("主题：" + ("、".join(detail.topics) if detail.topics else "未提供"))
    with activity_tab:
        metrics = analysis.metrics
        modules = analysis.modules
        activity_coverage = modules.get("activity")
        if activity_coverage and activity_coverage.coverage == "not_collected":
            st.info("维护活动深度数据尚未采集。可以使用上方按钮开始深度分析。")
        col1, col2 = st.columns(2)
        col1.metric("近 90 天 Commit", display_value(metrics.commits_90d if metrics else None))
        col2.metric("近一年 Release", display_value(metrics.release_count_365d if metrics else None))
    with community_tab:
        metrics = analysis.metrics
        community_coverage = analysis.modules.get("community")
        if community_coverage and community_coverage.coverage == "not_collected":
            st.info("社区活动深度数据尚未采集。")
        first, second = st.columns(2)
        first.metric("未关闭 Issue + PR", display_value(detail.open_issues_and_pr_count))
        second.metric("近 90 天关闭 Issue", display_value(metrics.issues_closed_90d if metrics else None))
        st.metric("近 90 天合并 PR", display_value(metrics.pr_merged_90d if metrics else None))
    with history_tab:
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
        else:
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
                        theme=st.session_state[STATE_KEYS["chart_theme"]],
                    )
                    st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})
                except ImportError:
                    st.error("当前环境未安装 Plotly；请按 frontend/requirements.txt 安装依赖。")
            st.dataframe(
                [{"采集日期": item.date.isoformat(), "观测值": item.value} for item in series.points],
                hide_index=True,
            )
    with info_tab:
        render_provenance(analysis.source_metadata or detail.source_metadata)
        for limitation in analysis.limitations:
            st.caption(f"局限：{limitation}")

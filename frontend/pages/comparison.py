import streamlit as st

from frontend.api.errors import APIError
from frontend.api.factory import get_api_client
from frontend.charts.comparisons import comparison_figure
from frontend.components.feedback import display_value, render_api_error
from frontend.state.keys import STATE_KEYS


def render() -> None:
    st.header("项目对比")
    client, _ = get_api_client()
    try:
        repositories = client.list_library(page=1, per_page=100).data.items
    except APIError as error:
        render_api_error(error)
        return
    names = {item.repository_id: item.full_name for item in repositories}
    stored = [item for item in st.session_state[STATE_KEYS["selected_repository_ids"]] if item in names]
    st.session_state[STATE_KEYS["selected_repository_ids"]] = stored
    if len(repositories) < 2:
        st.info("至少需要两个分析库成员才能比较。先在“仓库发现”添加项目。")
        return
    with st.form("comparison-selection"):
        selected = st.multiselect(
            "选择 2–5 个分析库仓库；选择顺序对应展示顺序",
            options=list(names),
            format_func=lambda repo_id: names[repo_id],
            max_selections=5,
            key=STATE_KEYS["selected_repository_ids"],
        )
        depth = st.selectbox(
            "分析深度",
            options=("basic", "deep"),
            format_func=lambda v: "基础" if v == "basic" else "深度",
            key=STATE_KEYS["comparison_depth"],
        )
        submitted = st.form_submit_button("比较仓库", type="primary", disabled=not 2 <= len(selected) <= 5)

    if submitted:
        valid_ids = {
            item.repository_id
            for item in repositories
            if item.analysis_status in {"completed", "partial"} and (item.stars is not None or item.forks is not None)
        }
        if not set(selected).issubset(valid_ids):
            st.warning("选择的仓库尚无有效基础分析数据；请先等待任务完成或刷新数据。")
            return
        try:
            result = client.compare(selected, depth=depth).data
            st.session_state[STATE_KEYS["comparison_result"]] = result
        except APIError as error:
            render_api_error(error)
            return

    result = st.session_state[STATE_KEYS["comparison_result"]]
    if result is None:
        st.info("选择仓库后运行比较。指标分别展示，不计算综合质量分。")
        return

    basis = result.comparison_basis
    st.caption(f"比较深度：{basis.depth} · 时间口径：{basis.metric_window}")
    if not basis.same_project_type:
        st.warning("这些项目类型不同，数值差异不能直接说明谁更适合你的场景。")
    for warning in basis.warnings:
        st.warning(warning)

    metric_rows = []
    for repository in result.repositories:
        metrics = repository.metrics
        metric_rows.append(
            {
                "仓库": repository.full_name,
                "Stars": display_value(metrics.stars),
                "Forks": display_value(metrics.forks),
                "仓库年龄（天）": display_value(metrics.age_days),
                "距最近推送（天）": display_value(metrics.days_since_push),
                "90 天 Commit": display_value(metrics.commits_90d),
                "一年 Release": display_value(metrics.release_count_365d),
                "数据覆盖": repository.coverage,
            }
        )
    st.dataframe(metric_rows, hide_index=True, use_container_width=True)

    chart_theme = st.session_state[STATE_KEYS["chart_theme"]]
    names = [item.full_name for item in result.repositories]
    for metric in ("stars", "forks"):
        values = [getattr(item.metrics, metric) for item in result.repositories]
        if all(value is None for value in values):
            st.info(f"{metric} 指标都缺失，暂不绘图。")
            continue
        try:
            figure = comparison_figure(names, values, metric=metric, theme=chart_theme)
            st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})
        except ImportError:
            st.error("当前环境未安装 Plotly；请按 frontend/requirements.txt 安装依赖。")


render()

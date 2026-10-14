from __future__ import annotations

import streamlit as st

from frontend.api.errors import APIError
from frontend.api.factory import get_api_client
from frontend.charts.comparisons import comparison_figure
from frontend.components.feedback import display_value, render_api_error
from frontend.components.page_header import render_page_header
from frontend.state.keys import STATE_KEYS


def _open_repository(repository_id: int) -> None:
    st.session_state[STATE_KEYS["repository_id"]] = repository_id
    st.switch_page("pages/repository.py", query_params={"repository_id": str(repository_id)})


def _selected_ids_from_result(result: object) -> list[int]:
    if result is None:
        return []
    return [item.repository_id for item in result.repositories]


def render() -> None:
    render_page_header(
        "仓库对比",
        "选择已有基础快照的仓库；搜索和分页可以访问分析库中的全部项目。",
    )
    client, _ = get_api_client()

    with st.form("comparison-search"):
        query = st.text_input(
            "搜索分析库",
            key=STATE_KEYS["comparison_query"],
            placeholder="仓库名或简介",
        )
        search_submitted = st.form_submit_button("搜索")
    if search_submitted:
        st.session_state[STATE_KEYS["comparison_page"]] = 1

    try:
        response = client.list_library(
            q=query.strip() or None,
            page=st.session_state[STATE_KEYS["comparison_page"]],
            per_page=20,
        )
    except APIError as error:
        render_api_error(error)
        return

    current_repositories = [
        item
        for item in response.data.items
        if item.analysis_status in {"completed", "partial"} and (item.stars is not None or item.forks is not None)
    ]
    selected_names = st.session_state[STATE_KEYS["comparison_selected_names"]]
    selected_names.update({item.repository_id: item.full_name for item in current_repositories})
    st.session_state[STATE_KEYS["comparison_selected_names"]] = selected_names

    page_names = {item.repository_id: item.full_name for item in current_repositories}
    stored_ids = list(st.session_state[STATE_KEYS["selected_repository_ids"]])
    options = [*page_names, *(repository_id for repository_id in stored_ids if repository_id not in page_names)]
    selected_ids = st.multiselect(
        "选择 2–5 个仓库；切换搜索或分页时会保留已选项",
        options=options,
        format_func=lambda repository_id: selected_names.get(repository_id, f"仓库 ID {repository_id}"),
        max_selections=5,
        key=STATE_KEYS["selected_repository_ids"],
    )
    depth = st.selectbox(
        "分析深度",
        options=("basic", "deep"),
        format_func=lambda value: "基础" if value == "basic" else "深度",
        key=STATE_KEYS["comparison_depth"],
    )
    if not 2 <= len(selected_ids) <= 5:
        st.caption("请选择至少 2 个、最多 5 个可比较仓库。")

    result = st.session_state[STATE_KEYS["comparison_result"]]
    if result is not None and (
        selected_ids != _selected_ids_from_result(result) or result.comparison_basis.depth != depth
    ):
        st.session_state[STATE_KEYS["comparison_result"]] = None
        result = None

    if st.button("比较仓库", type="primary", disabled=not 2 <= len(selected_ids) <= 5):
        try:
            result = client.compare(selected_ids, depth=depth).data
        except APIError as error:
            render_api_error(error)
            return
        st.session_state[STATE_KEYS["comparison_result"]] = result

    pagination = response.meta.pagination
    if pagination and (pagination.page > 1 or pagination.has_next):
        previous, label, next_page = st.columns([1, 2, 1])
        if previous.button("上一页", disabled=pagination.page <= 1):
            st.session_state[STATE_KEYS["comparison_page"]] = pagination.page - 1
            st.rerun()
        label.caption(
            f"第 {pagination.page} 页 · 共 {pagination.total if pagination.total is not None else '未知'} 个成员"
        )
        if next_page.button("下一页", disabled=not pagination.has_next):
            st.session_state[STATE_KEYS["comparison_page"]] = pagination.page + 1
            st.rerun()

    if not current_repositories:
        total = pagination.total if pagination else None
        if total == 0:
            st.info("分析库为空。先到发现仓库添加公开项目。")
        else:
            st.info("这一页没有可比较的基础快照；尚未采集的仓库不会被当成零值。")
    else:
        st.caption("本页可选仓库")
        for repository in current_repositories:
            left, right = st.columns([5, 1])
            left.write(repository.full_name)
            left.caption(
                f"Stars {display_value(repository.stars)} · Forks {display_value(repository.forks)} · "
                f"{repository.last_successful_collection_at.isoformat() if repository.last_successful_collection_at else '采集时间未知'}"
            )
            if right.button("查看详情", key=f"comparison-detail-{repository.repository_id}"):
                _open_repository(repository.repository_id)

    result = st.session_state[STATE_KEYS["comparison_result"]]
    if result is None:
        st.info("选择仓库后运行比较。指标分别展示，不计算综合质量分。")
        return

    basis = result.comparison_basis
    st.caption(f"比较深度：{'深度' if basis.depth == 'deep' else '基础'} · 时间口径：{basis.metric_window}")
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
                "近 90 天 Commit": display_value(metrics.commits_90d),
                "近 90 天关闭 Issue": display_value(metrics.issues_closed_90d),
                "近 90 天合并 PR": display_value(metrics.pr_merged_90d),
                "近一年 Release": display_value(metrics.release_count_365d),
                "数据覆盖": repository.coverage,
            }
        )
    st.dataframe(metric_rows, hide_index=True, width="stretch")

    chart_theme = st.session_state[STATE_KEYS["chart_theme"]]
    names = [item.full_name for item in result.repositories]
    for metric in ("stars", "forks"):
        values = [getattr(item.metrics, metric) for item in result.repositories]
        if all(value is None for value in values):
            st.info(f"{metric} 指标都缺失，暂不绘图。")
            continue
        try:
            figure = comparison_figure(names, values, metric=metric, theme=chart_theme)
            st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
        except ImportError:
            st.error("当前环境未安装 Plotly；请按项目安装说明安装前端依赖。")


render()

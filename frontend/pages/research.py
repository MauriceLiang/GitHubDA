import streamlit as st

from frontend.api.errors import APIError
from frontend.api.factory import get_api_client
from frontend.charts.distributions import distribution_figure
from frontend.charts.theme import language_color
from frontend.components.feedback import render_api_error, render_provenance
from frontend.state.keys import STATE_KEYS


def render() -> None:
    st.header("数据研究")
    client, _ = get_api_client()
    try:
        datasets = [dataset for dataset in client.datasets().data.items if dataset.type == "research"]
    except APIError as error:
        render_api_error(error)
        return
    if not datasets:
        st.info("暂无固定研究样本。个人分析库不会自动并入研究数据集。")
        return

    dataset_ids = [dataset.dataset_id for dataset in datasets]
    selected_id = st.session_state[STATE_KEYS["research_dataset_id"]]
    if selected_id not in dataset_ids:
        selected_id = dataset_ids[0]
        st.session_state[STATE_KEYS["research_dataset_id"]] = selected_id
    with st.form("research-filters"):
        dataset_id = st.selectbox(
            "固定数据集",
            options=dataset_ids,
            format_func=lambda value: next((item.name for item in datasets if item.dataset_id == value), value),
            key=STATE_KEYS["research_dataset_id"],
        )
        group_by = st.selectbox(
            "分组方式",
            options=("language", "star_tier", "age_tier"),
            format_func={"language": "语言", "star_tier": "Star 区间", "age_tier": "仓库年龄"}.get,
            key=STATE_KEYS["research_group_by"],
        )
        language = st.text_input("语言筛选（可选）", key=STATE_KEYS["research_language"], placeholder="Python")
        st.form_submit_button("更新研究结果", type="primary")

    dataset = next(item for item in datasets if item.dataset_id == dataset_id)
    try:
        statistics = client.research_statistics(dataset_id, language=language.strip() or None, group_by=group_by).data
    except APIError as error:
        render_api_error(error)
        return
    try:
        quality = client.research_data_quality(dataset_id).data
    except APIError as error:
        quality = None
        st.warning(f"数据质量报告暂不可用：{error.user_message}")

    st.caption(
        f"样本版本：{dataset.dataset_id} · 规则：{dataset.rules_version or '未提供'} · 冻结：{dataset.frozen_at.isoformat() if dataset.frozen_at else '未冻结'}"
    )
    st.caption(f"样本成员 n={dataset.sample_size} · 可分析 n={statistics.valid_sample_size}")
    if dataset.sample_size == 0 or statistics.valid_sample_size == 0:
        st.info("当前研究样本没有可分析记录；不会生成统计图表或用 0 填补缺失值。")

    descriptive, distribution, groups, correlations, quality_tab = st.tabs(
        ["描述统计", "特征分布", "分组比较", "相关性", "数据质量"]
    )
    with descriptive:
        star = statistics.summary.get("stars")
        forks = statistics.summary.get("forks")
        left, right = st.columns(2)
        if star:
            left.metric("Star 中位数", "未知" if star.median is None else f"{star.median:,.1f}")
            left.caption(f"n={star.count} · 均值 {star.mean if star.mean is not None else '未知'} · 标准差 {star.std if star.std is not None else '未知'}")
        if forks:
            right.metric("Fork 中位数", "未知" if forks.median is None else f"{forks.median:,.1f}")
            right.caption(f"n={forks.count} · 均值 {forks.mean if forks.mean is not None else '未知'} · 标准差 {forks.std if forks.std is not None else '未知'}")
        st.caption("开源样本统计不能代表 GitHub 全体仓库；相关性不代表因果关系。")
        render_provenance(statistics.source_metadata)

    with distribution:
        valid_groups = [item for item in statistics.groups if item.stars_median is not None]
        if valid_groups:
            try:
                figure = distribution_figure(
                    [item.group for item in valid_groups],
                    [item.stars_median for item in valid_groups],
                    title="分组 Star 中位数",
                    theme=st.session_state[STATE_KEYS["chart_theme"]],
                    colors=(
                        [language_color(item.group, st.session_state[STATE_KEYS["chart_theme"]]) for item in valid_groups]
                        if group_by == "language"
                        else None
                    ),
                )
                figure.update_layout(yaxis_title="Star 中位数")
                st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
                st.caption(f"研究数据集 {dataset_id} · 有效样本 n={statistics.valid_sample_size}")
            except ImportError:
                st.error("当前环境未安装 Plotly；请按项目安装说明安装前端依赖。")
        else:
            st.info("当前筛选没有可绘制的有效数值。")

    with groups:
        if statistics.groups:
            st.dataframe(
                [item.model_dump(mode="json") for item in statistics.groups],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("没有可用分组。")

    with correlations:
        if not statistics.correlations:
            st.info("当前样本没有可用的相关性结果。")
        for correlation in statistics.correlations:
            st.subheader(f"{correlation.method.title()}：{correlation.x} 与 {correlation.y}")
            if correlation.coefficient is None or correlation.p_value is None:
                st.info(correlation.note or "无法计算，可能是样本不足或变量没有变化。")
            else:
                st.write(
                    f"系数 {correlation.coefficient:.3f} · p 值 {correlation.p_value:.5g} · 有效样本 n={correlation.n}"
                )
            st.caption("相关性不代表因果关系。")

    with quality_tab:
        if quality is None:
            st.info("数据质量报告当前不可用。")
        else:
            st.caption("数据质量报告按整个固定数据集计算，不随语言筛选改变。")
            first, second, third = st.columns(3)
            first.metric("样本总数", quality.records_total)
            second.metric("可分析记录", quality.records_analyzable)
            third.metric("过期记录", quality.stale_count)
            st.caption(f"采样规则：{quality.sampling_rules_version} · 缺失率分母为样本总数 {quality.records_total}。")
            if quality.missing_fields:
                st.subheader("缺失字段")
                st.dataframe(
                    [
                        {
                            "字段": item.field,
                            "缺失数": item.count,
                            "缺失率": "—（无有效分母）" if item.rate is None else f"{item.rate:.1%}",
                        }
                        for item in quality.missing_fields
                    ],
                    hide_index=True,
                )
            if quality.excluded_by_reason:
                st.subheader("排除原因")
                st.dataframe([item.model_dump(mode="json") for item in quality.excluded_by_reason], hide_index=True)
            for note in quality.coverage_notes:
                st.caption(note)


render()

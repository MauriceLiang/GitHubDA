from __future__ import annotations

import streamlit as st

from frontend.api.errors import APIError
from frontend.api.factory import get_api_client
from frontend.charts.distributions import distribution_figure
from frontend.charts.theme import language_color
from frontend.components.empty_state import render_empty_state
from frontend.components.feedback import render_api_error
from frontend.components.metadata_panel import render_metadata_panel
from frontend.components.page_header import render_page_header
from frontend.state.keys import STATE_KEYS


RESEARCH_SECTIONS = ("概览", "分布", "分组", "相关性", "数据质量")


def _render_export(client: object, dataset_id: str) -> None:
    with st.expander("导出研究数据"):
        st.caption("导出范围仅为当前固定研究数据集，不包含个人分析库。")
        language = st.text_input("导出语言筛选（可选）", key=STATE_KEYS["export_language"])
        if st.button("准备研究数据 CSV", key="prepare-research-csv"):
            try:
                st.session_state[STATE_KEYS["research_export_payload"]] = client.export_repositories_csv(
                    "research",
                    dataset_id=dataset_id,
                    language=language.strip() or None,
                )
            except APIError as error:
                render_api_error(error)
        payload = st.session_state[STATE_KEYS["research_export_payload"]]
        if payload:
            st.download_button(
                "下载研究数据 CSV",
                data=payload.content,
                file_name=payload.filename,
                mime=payload.content_type,
                key="download-research-csv",
            )


def _render_quality(quality: object | None) -> None:
    if quality is None:
        st.info("数据质量报告当前不可用。")
        return

    st.caption("数据质量报告按整个固定数据集计算，不随语言筛选改变。")
    first, second, third = st.columns(3)
    first.metric("样本总数", quality.records_total)
    second.metric("可分析记录", quality.records_analyzable)
    third.metric("过期记录", quality.stale_count)
    st.caption(
        f"采样规则：{quality.sampling_rules_version or '未提供'} · "
        f"缺失率分母为样本总数 {quality.records_total}。"
    )
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


def render() -> None:
    render_page_header(
        "研究分析",
        "研究数据集与个人分析库是两类不同来源；个人分析库不会自动混入研究样本。",
    )
    client, _ = get_api_client()
    try:
        datasets = [dataset for dataset in client.datasets().data.items if dataset.type == "research"]
    except APIError as error:
        render_api_error(error)
        return
    if not datasets:
        render_empty_state(
            "暂无固定研究数据集",
            "研究分析只读取明确版本的研究样本。个人分析库中的仓库不会被用来填充研究数据。",
        )
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
    st.caption(
        f"样本版本：{dataset.dataset_id} · 规则：{dataset.rules_version or '未提供'} · "
        f"冻结：{dataset.frozen_at.isoformat() if dataset.frozen_at else '尚未冻结'}"
    )
    if dataset.frozen_at is None:
        st.warning("该数据集尚未冻结；结果用于检查当前样本，不应作为固定版本研究结论。")
    if dataset.sample_size == 0:
        render_empty_state(
            "研究样本为空",
            "先检查研究数据集的来源与采样规则。系统不会用个人分析库替代研究样本。",
        )
        render_metadata_panel(None, title="数据集来源说明")
        _render_export(client, dataset_id)
        return

    try:
        statistics = client.research_statistics(
            dataset_id,
            language=language.strip() or None,
            group_by=group_by,
        ).data
    except APIError as error:
        render_api_error(error)
        return
    try:
        quality = client.research_data_quality(dataset_id).data
    except APIError as error:
        quality = None
        st.warning(f"数据质量报告暂不可用：{error.user_message}")

    first, second, third = st.columns(3)
    first.metric("样本成员", dataset.sample_size)
    second.metric("当前可分析样本", statistics.valid_sample_size)
    third.metric("冻结状态", "已冻结" if dataset.frozen_at else "未冻结")
    if statistics.valid_sample_size == 0:
        st.info("当前筛选没有可分析记录；不会生成统计图表或用 0 填补缺失值。")

    section = st.selectbox("查看内容", RESEARCH_SECTIONS, key=STATE_KEYS["research_section"])
    if section == "概览":
        for metric_name, label in (("stars", "Stars"), ("forks", "Forks")):
            summary = statistics.summary.get(metric_name)
            if summary is None:
                continue
            st.subheader(f"{label} 描述统计")
            first, second, third = st.columns(3)
            first.metric("中位数", "—" if summary.median is None else f"{summary.median:,.1f}")
            second.metric("均值", "—" if summary.mean is None else f"{summary.mean:,.1f}")
            third.metric("有效样本", summary.count)
        with st.expander("如何解读研究结果"):
            st.caption("样本统计不能代表 GitHub 全部仓库；样本筛选和缺失情况会影响结果。")
            st.caption("相关性不代表因果关系。")
        render_metadata_panel(statistics.source_metadata)

    elif section == "分布":
        valid_groups = [item for item in statistics.groups if item.stars_median is not None]
        if statistics.valid_sample_size == 0:
            st.info("当前样本没有可绘制的有效数值。")
        elif valid_groups:
            try:
                theme = st.session_state[STATE_KEYS["chart_theme"]]
                figure = distribution_figure(
                    [item.group for item in valid_groups],
                    [item.stars_median for item in valid_groups],
                    title="分组 Star 中位数",
                    theme=theme,
                    colors=(
                        [language_color(item.group, theme) for item in valid_groups]
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

    elif section == "分组":
        if statistics.groups:
            st.dataframe(
                [item.model_dump(mode="json") for item in statistics.groups],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("没有可用分组。")

    elif section == "相关性":
        if not statistics.correlations:
            st.info("当前样本没有可用的相关性结果。")
        for correlation in statistics.correlations:
            st.subheader(f"{correlation.method.title()}：{correlation.x} 与 {correlation.y}")
            if correlation.coefficient is None or correlation.p_value is None:
                st.info(correlation.note or "无法计算，可能是样本不足或变量没有变化。")
            else:
                st.write(
                    f"系数 {correlation.coefficient:.3f} · p 值 {correlation.p_value:.5g} · "
                    f"有效样本 n={correlation.n}"
                )
            st.caption("相关性不代表因果关系。")

    else:
        _render_quality(quality)

    _render_export(client, dataset_id)


render()

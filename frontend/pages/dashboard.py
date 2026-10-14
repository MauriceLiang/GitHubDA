import streamlit as st

from frontend.api.errors import APIError
from frontend.api.factory import get_api_client
from frontend.charts.distributions import distribution_figure
from frontend.charts.theme import language_color, theme_options
from frontend.components.feedback import render_api_error, render_provenance
from frontend.state.keys import STATE_KEYS


def render() -> None:
    st.header("数据概览")
    client, _ = get_api_client()
    try:
        datasets = client.datasets().data.items
    except APIError as error:
        render_api_error(error)
        return

    research_datasets = [dataset for dataset in datasets if dataset.type == "research"]
    with st.form("overview-filters"):
        scope = st.selectbox(
            "统计范围",
            options=("research", "library"),
            format_func={"research": "固定研究样本", "library": "我的分析库"}.get,
            key=STATE_KEYS["scope"],
        )
        dataset_id = None
        if scope == "research":
            if not research_datasets:
                st.warning("当前没有可用的研究型数据集。")
            else:
                ids = [dataset.dataset_id for dataset in research_datasets]
                if st.session_state[STATE_KEYS["dataset_id"]] not in ids:
                    st.session_state[STATE_KEYS["dataset_id"]] = ids[0]
                dataset_id = st.selectbox(
                    "研究样本版本",
                    options=ids,
                    format_func=lambda value: next((item.name for item in research_datasets if item.dataset_id == value), value),
                    key=STATE_KEYS["dataset_id"],
                )
        language = st.text_input("语言筛选（可选）", key=STATE_KEYS["dashboard_language"], placeholder="Python")
        st.form_submit_button("刷新概览", type="primary")

    if scope == "research" and dataset_id is None:
        st.info("请先准备研究型数据集。")
        return
    try:
        overview = client.overview(scope, dataset_id=dataset_id, language=language.strip() or None).data
    except APIError as error:
        render_api_error(error)
        return

    kpis = overview.kpis
    member_label = "数据集成员数" if scope == "research" else "分析库成员数"
    member_scope = "数据集" if scope == "research" else "分析库"
    first, second, third, fourth = st.columns(4)
    first.metric(member_label, kpis.repositories_total)
    second.metric("已分析仓库", kpis.repositories_analyzed)
    third.metric("Star 中位数", "未知" if kpis.stars_median is None else f"{kpis.stars_median:,.1f}")
    fourth.metric(
        "90 天内有推送",
        "未知" if kpis.recently_pushed_90d_count is None else kpis.recently_pushed_90d_count,
    )

    source_sample = overview.source_metadata.sample_size
    if source_sample is not None:
        st.caption(
            f"有可用基础快照的成员 n={source_sample}；{member_scope}成员 n={kpis.repositories_total}。未采集成员不会计入前者。"
        )
    if not overview.language_distribution and not overview.stars_distribution:
        st.info("尚无可分析仓库。前往“仓库发现”添加项目。")
    else:
        left, right = st.columns(2)
        theme = st.session_state[STATE_KEYS["chart_theme"]]
        options = theme_options(theme)
        if overview.language_distribution:
            with left:
                try:
                    figure = distribution_figure(
                        [item.language for item in overview.language_distribution],
                        [item.count for item in overview.language_distribution],
                        title="语言样本分布",
                        theme=theme,
                        colors=[language_color(item.language, theme) for item in overview.language_distribution],
                    )
                    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
                    st.caption(f"有效分析样本 n={kpis.repositories_analyzed}")
                except ImportError:
                    st.error("当前环境未安装 Plotly；请按项目安装说明安装前端依赖。")
        if overview.stars_distribution:
            with right:
                try:
                    figure = distribution_figure(
                        [item.bucket for item in overview.stars_distribution],
                        [item.count for item in overview.stars_distribution],
                        title="Star 区间分布",
                        theme=theme,
                    )
                    figure.update_traces(marker_color=options["palette"][0])
                    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
                    st.caption(f"有效分析样本 n={kpis.repositories_analyzed}")
                except ImportError:
                    st.error("当前环境未安装 Plotly；请按项目安装说明安装前端依赖。")

    render_provenance(overview.source_metadata)


render()

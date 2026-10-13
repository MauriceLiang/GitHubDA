"""Metric-by-metric comparison chart; no composite score is calculated."""

from __future__ import annotations

from typing import Any

from frontend.charts.theme import apply_theme, theme_options


def comparison_figure(
    names: list[str], values: list[int | float | None], *, metric: str, theme: str
) -> Any:
    import plotly.graph_objects as go

    options = theme_options(theme)
    figure = go.Figure(
        go.Bar(x=names, y=values, marker_color=options["accent"])
    )
    figure.update_layout(title=metric, xaxis_title="仓库", yaxis_title=metric)
    return apply_theme(figure, theme)

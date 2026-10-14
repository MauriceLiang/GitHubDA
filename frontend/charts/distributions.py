"""Distribution charts built only from values returned by the API."""

from __future__ import annotations

from typing import Any

from frontend.charts.theme import apply_theme, theme_options


def distribution_figure(
    labels: list[str],
    values: list[int | float],
    *,
    title: str,
    theme: str,
    x_title: str | None = None,
    colors: list[str] | None = None,
) -> Any:
    import plotly.graph_objects as go

    options = theme_options(theme)
    figure = go.Figure(go.Bar(x=labels, y=values, marker_color=colors or options["accent"]))
    figure.update_layout(title=title, xaxis_title=x_title, yaxis_title="仓库数")
    return apply_theme(figure, theme)

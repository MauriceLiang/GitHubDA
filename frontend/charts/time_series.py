"""Observed-only time-series charts."""

from __future__ import annotations

from typing import Any

from frontend.charts.theme import apply_theme, theme_options


def time_series_figure(points: list[tuple[str, int]], *, metric: str, theme: str) -> Any:
    import plotly.graph_objects as go

    options = theme_options(theme)
    figure = go.Figure(
        go.Scatter(
            x=[point[0] for point in points],
            y=[point[1] for point in points],
            mode="lines+markers",
            connectgaps=False,
            line={"color": options["accent"]},
            name=metric,
        )
    )
    figure.update_layout(title=f"{metric} 实际观测", xaxis_title="采集日期", yaxis_title=metric)
    return apply_theme(figure, theme)

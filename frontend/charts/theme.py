"""Consistent Plotly styling for the dark and light display themes."""

from __future__ import annotations

import hashlib
from typing import Any


THEMES = {
    "dark": {
        "template": "plotly_dark",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font_color": "#E6EDF3",
        "grid_color": "#30363D",
        "accent": "#58A6FF",
        "palette": ["#58A6FF", "#3FB950", "#D29922", "#F85149", "#A371F7", "#39C5CF"],
    },
    "light": {
        "template": "plotly_white",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font_color": "#1F2328",
        "grid_color": "#D0D7DE",
        "accent": "#0969DA",
        "palette": ["#0969DA", "#1A7F37", "#9A6700", "#CF222E", "#8250DF", "#0A8995"],
    },
}


def theme_options(theme: str) -> dict[str, Any]:
    return THEMES["light" if theme == "light" else "dark"]


def language_color(language: str, theme: str) -> str:
    palette = theme_options(theme)["palette"]
    digest = hashlib.sha256(language.casefold().encode("utf-8")).digest()
    return palette[int.from_bytes(digest[:4], "big") % len(palette)]


def apply_theme(figure: Any, theme: str) -> Any:
    options = theme_options(theme)
    figure.update_layout(
        template=options["template"],
        paper_bgcolor=options["paper_bgcolor"],
        plot_bgcolor=options["plot_bgcolor"],
        font={"color": options["font_color"]},
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    figure.update_xaxes(gridcolor=options["grid_color"])
    figure.update_yaxes(gridcolor=options["grid_color"])
    return figure

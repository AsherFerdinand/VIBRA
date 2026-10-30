"""Presentation-only palettes; geometry, values, contour semantics and frames stay intact."""

from dataclasses import dataclass
from typing import Any, Literal

import plotly.graph_objects as go

Theme = Literal["Light", "Dark"]
THEMES: tuple[Theme, ...] = ("Light", "Dark")


@dataclass(frozen=True)
class Palette:
    background: str
    surface: str
    text: str
    muted: str
    border: str
    accent: str
    grid: str


PALETTES: dict[Theme, Palette] = {
    "Light": Palette("#ffffff", "#edf3f6", "#193442", "#465f6c", "#a7bcc8", "#126e76", "#dce5eb"),
    "Dark": Palette("#111b25", "#1c2b39", "#edf3f8", "#c1cfda", "#668295", "#64ded4", "#344c5e"),
}
DARK_COLORS = {
    "#44647b": "#afcfe0",
    "#1f3e50": "#bad9e9",
    "#142c3e": "#e2edf5",
    "#147d75": "#65dfcd",
    "#007f88": "#64dcd5",
    "#777": "#b5c5d0",
    "#718895": "#a3b8c8",
    "#8d9ca9": "#a9bac7",
    "#acb9c4": "#a9bac7",
    "#ba4b37": "#ff9e86",
    "#9b3e2e": "#ffc0a8",
    "#bd7139": "#ffbd7b",
    "#9b5b2a": "#ffbd7b",
    "#e06a2a": "#ffb576",
    "#b9cbd3": "#8ba6b7",
}


def themed_figure(figure: Any, theme: Theme) -> Any:
    """Copy and style a Plotly figure; never edit the caller's result/figure arrays."""
    if theme not in PALETTES:
        raise ValueError("Choose Light or Dark.")
    output = go.Figure(figure)
    p = PALETTES[theme]
    output.update_layout(
        template="plotly_dark" if theme == "Dark" else "plotly_white",
        paper_bgcolor=p.background,
        plot_bgcolor=p.background,
        font=dict(color=p.text),
        title_font_color=p.text,
        legend=dict(font=dict(color=p.text), bgcolor=p.background),
        hoverlabel=dict(bgcolor=p.surface, font_color=p.text, bordercolor=p.border),
    )
    if theme == "Dark":
        output.update_layout(
            colorway=["#64ded4", "#ffbd7b", "#c9a8ff", "#ff9bac", "#b6de79", "#99c8ff"]
        )
    output.update_xaxes(
        gridcolor=p.grid, zerolinecolor=p.border, tickfont_color=p.muted, title_font_color=p.text
    )
    output.update_yaxes(
        gridcolor=p.grid, zerolinecolor=p.border, tickfont_color=p.muted, title_font_color=p.text
    )

    colors = DARK_COLORS if theme == "Dark" else {v: k for k, v in DARK_COLORS.items()}

    def style(layout: Any, traces: Any) -> None:
        if layout.title is not None:
            layout.title.font.color = p.text
        for annotation in layout.annotations:
            annotation.font.color = p.text
            if annotation.arrowcolor in colors:
                annotation.arrowcolor = colors[annotation.arrowcolor]
        for menu in layout.updatemenus:
            menu.bgcolor = p.surface
            menu.bordercolor = p.border
            menu.font.color = p.text
        for slider in layout.sliders:
            slider.bgcolor = p.surface
            slider.bordercolor = p.border
            slider.font.color = p.muted
            slider.currentvalue.font.color = p.text
            slider.activebgcolor = p.accent
        for trace in traces:
            for name in ("line", "marker"):
                obj = getattr(trace, name, None)
                color = getattr(obj, "color", None)
                if obj is not None and isinstance(color, str) and color.lower() in colors:
                    obj.color = colors[color.lower()]
            if theme == "Dark" and getattr(trace, "fillcolor", None) == "rgba(68,100,123,.08)":
                trace.fillcolor = "rgba(150,195,220,.12)"
        # Preserve numeric color limits and signed meaning; brighten the dark blue/red ramp.
        for key in layout:
            if key.startswith("coloraxis"):
                axis = layout[key]
                if theme == "Dark" and axis.cmid == 0 and axis.cmin is not None and axis.cmin < 0:
                    axis.colorscale = ((0.0, "#67b7ef"), (0.5, "#edf3f8"), (1.0, "#ff8d86"))
                layout[key].colorbar.tickfont.color = p.muted
                layout[key].colorbar.title.font.color = p.text

    style(output.layout, output.data)
    for frame in output.frames:
        style(frame.layout, frame.data)
    return output

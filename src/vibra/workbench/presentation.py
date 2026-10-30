"""Session-local interface themes and a single rendering path for all Plotly views."""

from typing import Any

import streamlit as st

from vibra.visualization.theme import PALETTES, Theme, themed_figure


def interface_theme(theme: Theme) -> None:
    """CSS is session-local; Streamlit's server-wide theme config is not mutated."""
    p = PALETTES[theme]
    st.session_state["plot_theme"] = theme
    st.html(f"""<style>
    [data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stHeader"] {{
        background:{p.background} !important;
 color:{p.text} !important;

    }}
    [data-testid="stMainBlockContainer"] {{padding-top:4rem; max-width:1600px;}}
    [data-testid="stMainBlockContainer"] h1 {{font-size:2rem;
letter-spacing:.06em; margin-bottom:0; padding:0 0 .5rem;}}
    [data-testid="stMainBlockContainer"] h2 {{font-size:1.45rem;}}
    [data-testid="stMainBlockContainer"] h3 {{font-size:1.15rem;}}
    [data-testid="stSidebar"] {{min-width:18rem; max-width:22rem;}}
    [data-testid="stMetricValue"] {{font-size:1.65rem;}}
    [data-testid="stPlotlyChart"] {{border-radius:8px;}}
    [data-testid="stVerticalBlock"] {{gap:.8rem;}}
    [data-testid="stTable"] th, [data-testid="stTable"] td {{
        background:{p.background} !important; color:{p.text} !important;
        border-color:{p.grid} !important; padding:.45rem .6rem;
    }}
    [data-testid="stTable"] thead th {{background:{p.surface} !important;}}
    [data-testid="stSidebar"],
[data-testid="stSidebarContent"] {{background:{p.surface} !important;
color:{p.text} !important;
}}
    [data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
    [data-testid="stAppViewContainer"] h3,
[data-testid="stAppViewContainer"] h4,
    [data-testid="stMarkdownContainer"],
[data-testid="stWidgetLabel"],
    [data-testid="stWidgetLabel"] p,
label,
[data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
[data-testid="stMetricDelta"] {{color:{p.text} !important;
}}
    [data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {{color:{p.muted} !important;
}}
    [data-testid="stNumberInputContainer"],
[data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
textarea,
[data-baseweb="select"] > div {{
        background:{p.background} !important;
color:{p.text} !important;
border-color:{p.border} !important;

    }}
    input,
[data-baseweb="select"] input {{color:{p.text} !important;
caret-color:{p.accent} !important;
}}
    [data-baseweb="select"] svg {{fill:{p.text} !important;
}}
    [data-baseweb="popover"],
[role="listbox"],
[role="option"],
    [data-baseweb="menu"],
[data-baseweb="menu"] li {{background:{p.surface} !important;
color:{p.text} !important;
}}
    [role="option"]:hover {{background:{p.background} !important;
}}
    [data-testid="stExpander"] details {{border:1px solid {p.border};
background:{p.surface};
color:{p.text};}}
    [data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p {{color:{p.text} !important;
}}
    [data-testid="stForm"] {{border-color:{p.border};}}
    [data-testid="stAlert"] {{background:{p.surface};
color:{p.text};
border-left:3px solid {p.accent};}}
    button[kind="secondary"],
button[kind="secondaryFormSubmit"],
    [data-testid="stNumberInput"] button {{background:{p.surface} !important;
color:{p.text} !important;
border-color:{p.border} !important;
}}
    button[kind="primary"],
button[kind="primaryFormSubmit"] {{background:{p.accent} !important;
color:{p.background} !important;
border-color:{p.accent} !important;
}}
    [data-testid="stAppViewContainer"] a {{color:{p.accent};}}
    [data-testid="stTooltipContent"],
[data-baseweb="tooltip"] {{background:{p.surface};
color:{p.text};}}
    button[kind="primary"] *,
    button[kind="primaryFormSubmit"] * {{color:{p.background} !important;}}
    [data-baseweb="select"] span, [data-baseweb="select"] div {{color:{p.text} !important;}}
    [data-testid="stHeader"] button, [data-testid="stToolbar"] * {{color:{p.text} !important;}}
    .react-aria-ComboBox [role="group"],
    .react-aria-ComboBox input, .react-aria-ComboBox button,
    [data-testid="stMultiSelect"] [role="group"],
    [data-testid="stMultiSelect"] input {{
        background:{p.background} !important; color:{p.text} !important;
        border-color:{p.border} !important;
    }}
    [data-testid="stExpander"] summary {{background:{p.surface} !important;}}
    [data-testid="stCaptionContainer"] {{opacity:1 !important;}}
    [role="option"] * {{color:{p.text} !important;}}
    [data-testid="stTooltipHoverTarget"] svg,
    [data-testid="stTooltipIcon"],
    [data-testid="stTooltipHoverTarget"] [data-testid="stIconMaterial"] {{
        color:{p.muted} !important; fill:{p.muted} !important;
    }}
    [data-testid="stSidebarCollapseButton"] button,
    [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"] {{
        color:{p.text} !important;
    }}
    </style>""")


def plot(figure: Any, **kwargs: Any) -> Any:
    theme: Theme = st.session_state.get("plot_theme", "Light")
    kwargs["theme"] = None
    return st.plotly_chart(themed_figure(figure, theme), **kwargs)


def comparison_table(rows: list[dict[str, str | float]]) -> None:
    """Small accessible, theme-consistent tables; full precision remains in exports."""
    st.table(
        [
            {key: value if isinstance(value, str) else f"{value:.6g}" for key, value in row.items()}
            for row in rows
        ],
        hide_index=True,
        border="horizontal",
        width="stretch",
    )

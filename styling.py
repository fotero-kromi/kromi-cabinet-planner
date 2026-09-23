"""Improved KROMI corporate styling for the Cabinet Planner.

Use exactly like the current file:
    from styling import apply_kromi_theme
    apply_kromi_theme(page_title="Cabinet Planner", tagline="Internal tool", version="1.1")

Important: this version does NOT hide the Streamlit header completely, because
that can hide the sidebar reopen control. It hides only the toolbar chrome.
"""

from __future__ import annotations

from pathlib import Path
import base64
import html

import streamlit as st


# Brand colors from the KROMI style guides.
KROMI_GREEN = "#006C52"
KROMI_LIGHT_GREEN = "#4EAE33"
KROMI_TEXT = "#4A4A49"
KROMI_DARK = "#063B31"
KROMI_MUTED = "#6F7774"
KROMI_LINE = "#DCE7E2"
KROMI_SOFT = "#F4F8F5"
KROMI_SOFT_2 = "#EAF4EC"
KROMI_WARNING = "#B7791F"
KROMI_ERROR = "#B42318"
KROMI_SUCCESS = "#0F7A55"

ASSETS_DIR = Path(__file__).parent / "assets"
LOGO_PATHS = [
    ASSETS_DIR / "kromi_logo.png",
    ASSETS_DIR / "kromi_logo.svg",
    ASSETS_DIR / "logo.png",
    ASSETS_DIR / "logo.svg",
]


def _asset_as_base64(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception:
        return None


def _find_logo() -> tuple[str, str] | None:
    for path in LOGO_PATHS:
        b64 = _asset_as_base64(path)
        if b64:
            suffix = path.suffix.lower().lstrip(".")
            mime = "image/svg+xml" if suffix == "svg" else f"image/{suffix}"
            return b64, mime
    return None


def _logo_html(size_px: int = 42) -> str:
    logo = _find_logo()
    if logo:
        b64, mime = logo
        return f'<img src="data:{mime};base64,{b64}" alt="KROMI" style="height:{size_px}px; width:auto;" />'
    return '<span class="kromi-wordmark">KROMI</span>'


def _hide_streamlit_chrome() -> None:
    """Remove Streamlit branding while keeping the sidebar reopen button visible."""
    st.markdown(
        """
        <style>
        /* Keep the header mounted but minimal. */
        header[data-testid="stHeader"] {
            background: transparent !important;
            height: 2.25rem !important;
        }

        /* Hide app chrome, not the sidebar. */
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        .stDeployButton { display: none !important; }
        [data-testid="stToolbar"] { display: none !important; }
        [data-testid="stDecoration"] { display: none !important; }

        /* Prevent the sidebar from being collapsed: hide the collapse arrow.
           Users reported clicking it, losing the sidebar, and being unable to
           bring it back. The sidebar always starts expanded (set_page_config),
           and with the arrow hidden it stays visible. Multiple selectors cover
           Streamlit version differences in the control's markup. */
        [data-testid="stSidebarCollapseButton"],
        [data-testid="collapsedControl"],
        button[aria-label="Close sidebar"],
        button[title="Close sidebar"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _inject_corporate_css() -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            --kromi-green: {KROMI_GREEN};
            --kromi-light-green: {KROMI_LIGHT_GREEN};
            --kromi-text: {KROMI_TEXT};
            --kromi-dark: {KROMI_DARK};
            --kromi-muted: {KROMI_MUTED};
            --kromi-line: {KROMI_LINE};
            --kromi-soft: {KROMI_SOFT};
            --kromi-soft-2: {KROMI_SOFT_2};
        }}

        html, body {{
            color: var(--kromi-text);
        }}

        .stApp {{
            background:
                radial-gradient(circle at top left, rgba(78,174,51,0.12), transparent 34rem),
                linear-gradient(180deg, #FFFFFF 0%, #FAFCFA 45%, #F7FAF8 100%);
        }}

        .block-container {{
            max-width: 1500px;
            padding-top: 1.0rem !important;
            padding-left: 2.2rem;
            padding-right: 2.2rem;
            padding-bottom: 4.5rem;
        }}

        /* Sidebar */
        section[data-testid="stSidebar"] {{
            background:
                linear-gradient(180deg, #F8FBF8 0%, #EEF6EF 100%);
            border-right: 1px solid var(--kromi-line);
            box-shadow: 6px 0 24px rgba(0, 108, 82, 0.08);
        }}
        /* The sidebar header used to hold the collapse arrow (now hidden).
           Collapse the empty space it leaves so the content sits at the top. */
        [data-testid="stSidebarHeader"] {{
            padding: 0 !important;
            height: 0 !important;
            min-height: 0 !important;
        }}
        [data-testid="stSidebarUserContent"] {{
            padding-top: 0.5rem !important;
        }}
        section[data-testid="stSidebar"] > div {{
            padding-top: 0.25rem !important;
        }}
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {{
            color: var(--kromi-green) !important;
            letter-spacing: 0.01em;
        }}
        section[data-testid="stSidebar"] .stMarkdown p,
        section[data-testid="stSidebar"] label {{
            color: #3F4744 !important;
        }}
        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > [style*="flex-direction: column"] {{
            gap: 0.55rem;
        }}

        /* Header hero */
        .kromi-header {{
            display: grid;
            grid-template-columns: auto 1fr auto;
            gap: 18px;
            align-items: center;
            min-height: 82px;
            margin: 0.2rem 0 1.4rem 0;
            padding: 18px 22px;
            border: 1px solid rgba(0,108,82,0.16);
            border-radius: 18px;
            background:
                linear-gradient(135deg, rgba(0,108,82,0.98) 0%, rgba(6,59,49,0.98) 54%, rgba(78,174,51,0.88) 100%);
            box-shadow: 0 18px 45px rgba(0, 74, 55, 0.16);
            overflow: hidden;
            position: relative;
        }}
        .kromi-header::after {{
            content: "";
            position: absolute;
            width: 240px;
            height: 240px;
            right: -80px;
            top: -120px;
            background: rgba(255,255,255,0.10);
            border-radius: 50%;
        }}
        .kromi-header-logo {{
            background: rgba(255,255,255,0.96);
            border-radius: 12px;
            padding: 10px 12px;
            box-shadow: 0 10px 26px rgba(0,0,0,0.16);
            z-index: 1;
        }}
        .kromi-header-main {{ z-index: 1; }}
        .kromi-header-title {{
            color: white;
            font-weight: 760;
            font-size: clamp(1.35rem, 2vw, 2.0rem);
            line-height: 1.05;
            letter-spacing: -0.025em;
        }}
        .kromi-header-subtitle {{
            color: rgba(255,255,255,0.82);
            font-size: 0.92rem;
            margin-top: 7px;
        }}
        .kromi-header-tag {{
            z-index: 1;
            color: white;
            background: rgba(255,255,255,0.12);
            border: 1px solid rgba(255,255,255,0.22);
            border-radius: 999px;
            padding: 8px 12px;
            font-size: 0.78rem;
            font-weight: 650;
            white-space: nowrap;
        }}

        .kromi-wordmark {{
            display: inline-block;
            color: var(--kromi-green);
            font-weight: 850;
            letter-spacing: 0.10em;
            font-size: 1.15rem;
            line-height: 1;
        }}

        /* Typography */
        h1 {{
            color: var(--kromi-green) !important;
            font-weight: 750 !important;
            letter-spacing: -0.03em;
        }}
        h2 {{
            color: var(--kromi-green) !important;
            font-weight: 720 !important;
            letter-spacing: -0.015em;
            padding-bottom: 0.38rem;
            border-bottom: 2px solid var(--kromi-light-green);
            margin-top: 2.0rem !important;
        }}
        h3 {{
            color: var(--kromi-text) !important;
            font-weight: 680 !important;
        }}
        p, li, div {{
            line-height: 1.48;
        }}

        /* Inputs */
        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        textarea,
        [data-baseweb="textarea"] {{
            border-radius: 10px !important;
            border-color: #C9D8D2 !important;
            background: rgba(255,255,255,0.96) !important;
        }}
        div[data-baseweb="input"]:focus-within > div,
        div[data-baseweb="select"]:focus-within > div,
        textarea:focus {{
            border-color: var(--kromi-green) !important;
            box-shadow: 0 0 0 3px rgba(78,174,51,0.17) !important;
        }}

        /* Buttons */
        .stButton > button,
        .stDownloadButton > button,
        button[data-testid="baseButton-secondary"],
        button[data-testid="baseButton-primary"] {{
            border-radius: 999px !important;
            min-height: 2.55rem;
            font-weight: 680 !important;
            letter-spacing: 0.005em;
            transition: transform 120ms ease, box-shadow 120ms ease, background 120ms ease;
        }}
        .stButton > button:hover,
        .stDownloadButton > button:hover {{
            transform: translateY(-1px);
            box-shadow: 0 8px 18px rgba(0,108,82,0.16);
        }}
        .stButton > button[kind="primary"],
        button[data-testid="baseButton-primary"],
        .stDownloadButton > button {{
            /* v34.51: solid brand green. White text on the light end of the
               old gradient was 2.83:1, below the 4.5:1 WCAG minimum. */
            background: var(--kromi-green) !important;
            color: white !important;
            border: 0 !important;
        }}
        .stButton > button[kind="secondary"],
        button[data-testid="baseButton-secondary"] {{
            background: white !important;
            color: var(--kromi-green) !important;
            border: 1px solid rgba(0,108,82,0.35) !important;
        }}

        /* Cards / containers */
        [data-testid="stMetric"],
        div[data-testid="stExpander"] details,
        .kromi-card {{
            background: rgba(255,255,255,0.96);
            border: 1px solid var(--kromi-line);
            border-radius: 16px;
            box-shadow: 0 10px 30px rgba(30, 70, 55, 0.08);
        }}
        [data-testid="stMetric"] {{
            padding: 16px 18px;
            border-left: 4px solid var(--kromi-light-green);
        }}
        [data-testid="stMetricLabel"] {{
            color: var(--kromi-muted) !important;
            text-transform: uppercase;
            letter-spacing: 0.055em;
            font-size: 0.74rem !important;
            font-weight: 720;
        }}
        [data-testid="stMetricValue"] {{
            color: var(--kromi-green) !important;
            font-weight: 800 !important;
            letter-spacing: -0.02em;
        }}
        [data-testid="stMetricDelta"] {{
            color: var(--kromi-muted) !important;
        }}

        /* Expanders */
        div[data-testid="stExpander"] details {{
            padding: 0.25rem 0.55rem;
        }}
        div[data-testid="stExpander"] summary {{
            color: var(--kromi-green) !important;
            font-weight: 700;
        }}

        /* Alerts */
        .stAlert {{
            border-radius: 14px !important;
            border-left-width: 5px !important;
            box-shadow: 0 8px 20px rgba(0,0,0,0.04);
        }}

        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 0.4rem;
            border-bottom: 1px solid var(--kromi-line);
        }}
        .stTabs [data-baseweb="tab"] {{
            border-radius: 999px 999px 0 0;
            padding: 0.7rem 1rem;
            color: var(--kromi-muted);
            font-weight: 650;
        }}
        .stTabs [aria-selected="true"] {{
            color: var(--kromi-green) !important;
            border-bottom: 3px solid var(--kromi-light-green) !important;
            background: rgba(78,174,51,0.08);
        }}

        /* Dataframes */
        [data-testid="stDataFrame"] {{
            border: 1px solid var(--kromi-line);
            border-radius: 14px;
            overflow: hidden;
            box-shadow: 0 8px 24px rgba(0, 74, 55, 0.06);
        }}
        .stDataFrame thead tr th {{
            background-color: var(--kromi-green) !important;
            color: white !important;
            font-weight: 720 !important;
        }}

        /* Progress */
        .stProgress > div > div > div > div {{
            background: linear-gradient(90deg, var(--kromi-green), var(--kromi-light-green)) !important;
        }}

        /* File uploader */
        [data-testid="stFileUploader"] section {{
            border: 1.5px dashed rgba(0,108,82,0.35);
            border-radius: 16px;
            background: rgba(244,248,245,0.8);
        }}

        /* Corporate footer */
        .kromi-footer {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: linear-gradient(90deg, var(--kromi-dark), var(--kromi-green));
            color: rgba(255,255,255,0.92);
            padding: 7px 20px;
            font-size: 11px;
            text-align: center;
            z-index: 999;
            box-shadow: 0 -8px 20px rgba(0,0,0,0.08);
        }}

        /* Optional helper components. */
        .kromi-section-card {{
            background: white;
            border: 1px solid var(--kromi-line);
            border-left: 5px solid var(--kromi-green);
            border-radius: 16px;
            padding: 16px 18px;
            box-shadow: 0 10px 30px rgba(0, 74, 55, 0.07);
            margin: 0.65rem 0 1rem 0;
        }}
        .kromi-section-card-title {{
            color: var(--kromi-green);
            font-weight: 800;
            font-size: 1.02rem;
            margin-bottom: 4px;
        }}
        .kromi-section-card-body {{
            color: var(--kromi-muted);
            font-size: 0.92rem;
        }}

        @media (max-width: 900px) {{
            .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
            .kromi-header {{ grid-template-columns: 1fr; gap: 10px; }}
            .kromi-header-tag {{ width: fit-content; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header(title: str, tagline: str) -> None:
    st.markdown(
        f"""
        <div class="kromi-header">
            <div class="kromi-header-logo">{_logo_html(44)}</div>
            <div class="kromi-header-main">
                <div class="kromi-header-title">{html.escape(title)}</div>
                <div class="kromi-header-subtitle">Calculates the number of supply points and cabinets needed for a given tool list</div>
            </div>
            <div class="kromi-header-tag">{html.escape(tagline)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar_logo() -> None:
    with st.sidebar:
        st.markdown(
            f"""
            <div style="text-align:center; padding: 4px 0 14px 0;">
                <div style="display:inline-flex; align-items:center; justify-content:center; background:white; border:1px solid {KROMI_LINE}; border-radius:14px; padding:10px 14px; box-shadow:0 8px 22px rgba(0,108,82,0.09);">
                    {_logo_html(42)}
                </div>
                <div style="font-size:11px; color:{KROMI_MUTED}; margin-top:8px; letter-spacing:.04em; text-transform:uppercase;">Cabinet Planner</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_footer(version: str) -> None:
    st.markdown(
        f"""
        <div class="kromi-footer">
            &copy; Kromi Logistik GmbH 2026 &middot; Build {html.escape(version)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def kromi_section(title: str, body: str = "") -> None:
    """Optional helper for a clean section intro card."""
    st.markdown(
        f"""
        <div class="kromi-section-card">
            <div class="kromi-section-card-title">{html.escape(title)}</div>
            <div class="kromi-section-card-body">{html.escape(body)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def apply_kromi_theme(
    page_title: str = "Cabinet Planner",
    tagline: str = "",
    version: str = "",
    include_footer: bool = True,
    include_sidebar_logo: bool = False,
) -> None:
    """Apply the KROMI visual theme once, after st.set_page_config().

    ``tagline`` / ``version`` must be passed by the caller (typically from
    ``engine.build_info``); leaving them empty avoids stamping a stale label.
    """
    _hide_streamlit_chrome()
    _inject_corporate_css()
    if include_sidebar_logo:
        _render_sidebar_logo()
    _render_header(title=page_title, tagline=tagline)
    if include_footer:
        _render_footer(version=version)

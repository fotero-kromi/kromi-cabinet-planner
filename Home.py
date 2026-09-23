"""Welcome page for the Cabinet Planner suite.

This is the landing page when the app first loads. It presents two large
choice cards — Kromi Cabinet Planner and EGC Cabinet Planner — and routes
the user to the appropriate planner via Streamlit's multi-page navigation.
"""

import streamlit as st
from engine.build_info import BUILD, build_stamp

st.set_page_config(
    page_title="Cabinet Planner",
    page_icon="assets/kromi_favicon.png",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "Cabinet Planner Suite — Kromi Logistik GmbH",
    },
)

from styling import apply_kromi_theme

apply_kromi_theme(
    page_title="Cabinet Planner Suite",
    tagline=build_stamp(),
    version=BUILD,
    include_sidebar_logo=False,
)


# Welcome page CSS — landing-page specific styles (large picker cards,
# centered layout, hide the auto-generated multi-page nav titles).
st.markdown(
    """
    <style>
    /* Hide the sidebar's auto-generated page nav on the welcome page itself.
       Users will navigate via the big cards. */
    [data-testid="stSidebarNav"] { display: none; }

    /* Centered intro section. */
    .welcome-intro {
        max-width: 760px;
        margin: 1rem auto 2.5rem auto;
        text-align: center;
    }
    .welcome-intro h1 {
        font-size: 2.4rem;
        font-weight: 750;
        letter-spacing: -0.03em;
        color: #006C52;
        margin-bottom: 0.6rem;
    }
    .welcome-intro p {
        font-size: 1.05rem;
        color: #6F7774;
        line-height: 1.5;
    }

    /* Card grid. */
    .pick-card {
        background: white;
        border: 1px solid #DCE7E2;
        border-left: 6px solid #006C52;
        border-radius: 18px;
        padding: 32px 28px;
        box-shadow: 0 14px 38px rgba(0, 74, 55, 0.08);
        transition: transform 160ms ease, box-shadow 160ms ease;
        height: 100%;
    }
    .pick-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 22px 48px rgba(0, 74, 55, 0.14);
    }
    .pick-card.egc {
        border-left-color: #4EAE33;
    }
    .pick-card h2 {
        color: #006C52 !important;
        font-size: 1.6rem !important;
        font-weight: 720 !important;
        letter-spacing: -0.02em;
        margin-top: 0 !important;
        margin-bottom: 0.5rem !important;
        border-bottom: none !important;
        padding-bottom: 0 !important;
    }
    .pick-card.egc h2 {
        color: #4EAE33 !important;
    }
    .pick-card .pick-subtitle {
        color: #6F7774;
        font-size: 0.95rem;
        margin-bottom: 1.0rem;
    }
    .pick-card .pick-bullets {
        color: #4A4A49;
        font-size: 0.92rem;
        line-height: 1.7;
        margin-bottom: 1.2rem;
    }
    .pick-card .pick-bullets li {
        margin-bottom: 0.15rem;
    }
    .pick-card .pick-cta {
        display: inline-block;
        padding: 0.6rem 1.2rem;
        background: linear-gradient(135deg, #006C52, #4EAE33);
        color: white;
        border-radius: 999px;
        font-weight: 680;
        text-decoration: none;
        font-size: 0.95rem;
        margin-top: 0.4rem;
    }

    /* Status badges. */
    .status-pill {
        display: inline-block;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        padding: 3px 10px;
        border-radius: 999px;
        margin-left: 8px;
        vertical-align: middle;
    }
    .status-ready {
        background: #EAF4EC;
        color: #0F7A55;
        border: 1px solid #B6DCC2;
    }
    .status-preview {
        background: #FFF6E5;
        color: #B7791F;
        border: 1px solid #F0D49B;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Intro
st.markdown(
    """
    <div class="welcome-intro">
        <h1>Pick a planner</h1>
        <p>Both planners calculate the number of supply points and cabinets needed
        for a given tool list. Each is tuned to a specific hardware platform.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

col_kromi, col_egc = st.columns(2, gap="large")

with col_kromi:
    st.markdown(
        """
        <div class="pick-card">
            <h2>Kromi <span class="status-pill status-ready">Ready</span></h2>
            <div class="pick-subtitle">Helix, Carousel, Locker A/B/C</div>
            <ul class="pick-bullets">
                <li>Helix: 70 spirals per cabinet</li>
                <li>Carousel: 720 slots per cabinet</li>
                <li>Lockers A/B/C: 48 / 72 / 96 compartments</li>
                <li>Programme&rarr;supply-point routing</li>
                <li>30-day default coverage, KTC / Kanban split</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Open Kromi planner", key="open_kromi", type="primary", width="stretch"):
        st.switch_page("pages/1_Kromi_Planner.py")

with col_egc:
    st.markdown(
        """
        <div class="pick-card egc">
            <h2>EGC <span class="status-pill status-preview">Preview</span></h2>
            <div class="pick-subtitle">Cribmaster Prostock, Autocrib TX750</div>
            <ul class="pick-bullets">
                <li>Cribmaster Prostock: 560 modular slots, items 1&ndash;13 slots wide</li>
                <li>Autocrib TX750: bin-based, S / M / L / XL / Filler</li>
                <li>User picks Prostock-only, TX750-only, or both</li>
                <li>7-day default coverage, Crib / vending split</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Open EGC planner", key="open_egc", width="stretch"):
        st.switch_page("pages/2_EGC_Planner.py")

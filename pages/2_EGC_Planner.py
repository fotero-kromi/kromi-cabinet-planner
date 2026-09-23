"""EGC Cabinet Planner — preview page.

Phase 1: shows the hardware spec we've agreed on with the EGC team and a
"coming soon" banner. The planning math (Prostock slot packing, TX750
bin allocation) is implemented in Phase 2.

Until then, this page is informational — it documents the hardware contract
so anyone landing here knows what's coming and what to expect.
"""

import streamlit as st
from engine.build_info import BUILD

st.set_page_config(
    page_title="EGC Planner",
    page_icon="assets/kromi_favicon.png",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "EGC Cabinet Planner — preview build",
    },
)

from styling import apply_kromi_theme

# Same Kromi theme for now — EGC brand colors come later.
apply_kromi_theme(
    page_title="EGC Cabinet Planner",
    tagline="Preview build",
    version=BUILD,
)


# Preview banner
st.warning(
    "**Preview build.** This planner is under active development. "
    "The hardware spec below is final; the planning math is being implemented. "
    "Use the Kromi planner for any production sizing in the meantime."
)

# Sidebar — minimal for now, just a back link
with st.sidebar:
    st.markdown("### Controls")
    st.caption("Planning controls will appear here once the EGC math is wired up.")
    if st.button("Back to picker", width="stretch"):
        st.switch_page("Home.py")

# Hardware spec — visible documentation of what's been agreed
st.subheader("Hardware spec")

st.markdown(
    """
    EGC operates two vending machine types. The planner will let users pick
    Prostock-only, TX750-only, or both configurations per run.
    """
)

spec_col_left, spec_col_right = st.columns(2, gap="large")

with spec_col_left:
    st.markdown(
        """
        #### Cribmaster Prostock

        Modular slot-based machine.

        - **Capacity per cabinet**: 560 slots
        - **Item width**: 1 to 13 slots per item
        - **Slot-width per item**: inferred from product category (lookup table,
          tunable per customer)
        - **Sizing**: simple bin-packing &mdash; sum slots per item, divide by 560

        **Typical category &rarr; slot-width mapping** *(initial values, to tune)*:

        | Category | Slots |
        |---|---|
        | Inserts | 1 |
        | Screws | 1 |
        | Drills (small) | 2 |
        | Drills (large) | 4 |
        | Mills | 4 |
        | Reamers | 3 |
        | Holders | 8 |
        | Boring bars | 10 |
        | Accessories | 2 |
        """
    )

with spec_col_right:
    st.markdown(
        """
        #### Autocrib TX750

        Bin-based machine. Four bin types per cabinet plus an XL option that
        doubles up in the Large compartment.

        - **Small compartment**: 720 inches total
        - **Medium compartment**: 535 inches
        - **Large compartment**: 360 inches
        - **Filler compartment**: 360 inches
        - **Extra Large bins**: live in the Large compartment, count as 2&times;
          their height
        - **Bin height range**: 2&ndash;60 inches

        **Typical category &rarr; bin type mapping** *(initial values, to tune)*:

        | Category | Bin type |
        |---|---|
        | Inserts | Small |
        | Screws | Small |
        | Drills (small) | Small |
        | Drills (large) | Medium |
        | Mills | Medium |
        | Reamers | Medium |
        | Holders | Large |
        | Boring bars | XL |
        | PPE | Filler |
        """
    )

st.divider()

st.subheader("Stock model")
st.markdown(
    """
    EGC distinguishes two stock tiers, equivalent to Kromi's KTC / Kanban split:

    - **Vending** &mdash; items held physically in the Prostock or TX750
      machine. Sized for **7 days of consumption** by default (configurable
      per customer).
    - **Crib** &mdash; warehouse-only inventory. Not in the machine.
      Replenishment flows from Crib to Vending on a weekly cadence.

    The same classification, override library, and audit features already in
    the Kromi planner will apply to EGC. The only difference is the cabinet
    sizing math.
    """
)

st.divider()

st.subheader("Phase plan")
st.markdown(
    """
    **Phase 1 (now)** &mdash; This preview page documenting the spec.

    **Phase 2 (next)** &mdash; Implement Prostock slot-packing and TX750 bin
    allocation in a shared engine module. Build the category &rarr;
    slot-width / bin-type lookup tables with sensible defaults.

    **Phase 3** &mdash; Wire the EGC planner to the engine. Sidebar controls
    for cabinet-config picker (Prostock-only / TX750-only / both), 7-day
    coverage default, EGC-specific category lookups.

    **Phase 4 (later)** &mdash; EGC corporate branding (logo, colors) once
    we have the brand guide.
    """
)

"""
OKR Planning App — entry point and navigation router.

This file does ONE thing: it defines the sidebar navigation structure and hands
off to whichever page is selected. The actual page content lives in `views/`.

Why this pattern (st.navigation) instead of Streamlit's auto-discovered `pages/`
directory:
  * Pages can be grouped into named sections in the sidebar.
  * Page order is explicit, not driven by filename prefixes.
  * Display titles are decoupled from filenames — no "3_Manage_Org_Units" labels.
  * Adding/reordering/renaming pages is one line of code instead of a file rename.

st.set_page_config is called ONCE here. View files must not call it again.
"""

import streamlit as st


# Global page config — applies to every page in the app.
st.set_page_config(
    page_title="OKR Planning",
    page_icon="🎯",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Define pages
# ---------------------------------------------------------------------------
# Plan (workflow) pages
annual_strategy = st.Page(
    "views/annual_strategy.py",
    title="Annual Strategy & Objectives",
    icon="📜",
)
plan_quarter = st.Page(
    "views/plan_quarter.py",
    title="Plan a Quarter",
    icon="✏️",
    default=True,  # the primary working surface
)
checkins = st.Page(
    "views/checkins.py",
    title="Check-ins",
    icon="📈",
)

# View (read-only) pages
overview = st.Page(
    "views/overview.py",
    title="Overview",
    icon="🎯",
)
summary = st.Page(
    "views/summary.py",
    title="Summary",
    icon="📄",
)
objectives = st.Page(
    "views/objectives.py",
    title="Objectives & KRs",
    icon="🧭",
)
initiatives = st.Page(
    "views/initiatives.py",
    title="Initiatives",
    icon="🚀",
)
flow = st.Page(
    "views/flow.py",
    title="Flow",
    icon="🌊",
)

# Manage (CRUD) pages
manage_org = st.Page(
    "views/manage_org_units.py",
    title="Org Units",
    icon="🏛️",
)
manage_krs = st.Page(
    "views/manage_key_results.py",
    title="Key Results",
    icon="📊",
)


# ---------------------------------------------------------------------------
# Grouped navigation
# ---------------------------------------------------------------------------
nav = st.navigation(
    {
        "Plan": [annual_strategy, plan_quarter],
        "Track": [checkins],
        "Views": [overview, summary, objectives, initiatives, flow],
        "Manage": [manage_org, manage_krs],
    }
)

nav.run()

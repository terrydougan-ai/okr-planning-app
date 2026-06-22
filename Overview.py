"""
OKR Planning App — entry point and navigation router.

This file does ONE thing: it defines the sidebar navigation structure and
hands off to whichever page is selected. The actual page content lives in
`views/`.
"""

import streamlit as st


st.set_page_config(
    page_title="OKR Planning",
    page_icon="🎯",
    layout="wide",
)


# Plan (workflow) pages
plan_objective = st.Page(
    "views/plan_objective.py",
    title="Plan an Objective",
    icon="✏️",
    default=True,
)

# View (read-only) pages
overview = st.Page(
    "views/overview.py",
    title="Overview",
    icon="🎯",
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
manage_strategy_obj = st.Page(
    "views/manage_strategy_objectives.py",
    title="Strategy & Objectives",
    icon="🗺️",
)
manage_krs = st.Page(
    "views/manage_key_results.py",
    title="Key Results",
    icon="📊",
)


nav = st.navigation(
    {
        "Plan": [plan_objective],
        "Views": [overview, objectives, initiatives, flow],
        "Manage": [manage_org, manage_strategy_obj, manage_krs],
    }
)

nav.run()

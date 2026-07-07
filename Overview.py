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
# About / context page — the landing page for demo visitors
about_page = st.Page(
    "views/about.py",
    title="About this project",
    icon="👋",
    default=True,  # what a first-time visitor sees on landing
)

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
)
checkins = st.Page(
    "views/key_result_updates.py",
    title="Key Result Updates",
    icon="📈",
)
initiative_updates = st.Page(
    "views/initiative_updates.py",
    title="Initiative Updates",
    icon="📊",
)

# View (read-only) pages
hotspots = st.Page(
    "views/hotspots.py",
    title="Hotspots",
    icon="🔥",
)
initiatives = st.Page(
    "views/initiatives.py",
    title="Initiatives",
    icon="🚀",
)
summary = st.Page(
    "views/plan_narrative.py",
    title="Plan Narrative",
    icon="📄",
)
objectives = st.Page(
    "views/objectives.py",
    title="Objectives & KRs",
    icon="🧭",
)
flow = st.Page(
    "views/flow.py",
    title="Plan Flow",
    icon="🌊",
)

# Manage (CRUD) pages
manage_org = st.Page(
    "views/manage_org_units.py",
    title="Org Units",
    icon="🏛️",
)
manage_krs_decommissioned = None  # Manage Key Results page retired; KR editing
# happens on Plan a Quarter and Annual Strategy. Schema columns
# parent_key_result_id and contribution_weight stay in the DB as latent
# infrastructure in case rollup is ever wanted.

create_initiative = st.Page(
    "views/create_initiative.py",
    title="Create Initiative",
    icon="🚀",
)


# ---------------------------------------------------------------------------
# Grouped navigation
# ---------------------------------------------------------------------------
nav = st.navigation(
    {
        "About": [about_page],
        "Plan": [annual_strategy, plan_quarter, flow],
        "Track": [checkins, initiative_updates],
        "Views": [hotspots, summary, objectives, initiatives],
        "Manage": [manage_org, create_initiative],
    }
)


# ---------------------------------------------------------------------------
# Sidebar scope indicator
# ---------------------------------------------------------------------------
# Shows the currently-active org/period scope so the user always knows what
# the page-level filters are pinned to, even after navigating between pages.
# Reads from session state keys 'scope_org_name' and 'scope_period' that the
# individual pages keep up to date when their pickers change.
with st.sidebar:
    st.divider()
    _scope_org = st.session_state.get("scope_org_name")
    _scope_period = st.session_state.get("scope_period")
    _parts = []
    if _scope_org:
        _parts.append(f"📍 {_scope_org}")
    else:
        _parts.append("📍 All org units")
    if _scope_period:
        _parts.append(_scope_period)
    st.caption("**Current scope**")
    st.caption(" · ".join(_parts))
    # Only show the reset button when there's actually something to reset
    if _scope_org or _scope_period:
        if st.button(
            "↻ Reset scope",
            use_container_width=True,
            help=(
                "Clear the remembered org unit and period. Each page will "
                "fall back to its built-in default the next time you visit."
            ),
        ):
            for _k in ("scope_org_id", "scope_org_name", "scope_period"):
                st.session_state.pop(_k, None)
            st.rerun()

    # --- Footer link block ---------------------------------------------
    # A discreet always-visible anchor pointing to the repo. Deliberately
    # small — the About page carries the real context. This just makes
    # sure the link is one click away from wherever the user happens to
    # be in the app.
    st.divider()
    st.markdown(
        "<div style='font-size:0.8em;color:#6B7280;line-height:1.5'>"
        "🌐 Demo · <a href='https://github.com/terrydougan-ai/okr-planning-app' "
        "target='_blank' style='color:#6B7280;text-decoration:underline'>"
        "view repo</a>"
        "</div>",
        unsafe_allow_html=True,
    )


nav.run()

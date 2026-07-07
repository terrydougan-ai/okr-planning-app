"""
About — context page for demo visitors (hiring managers, portfolio browsers).

Answers three questions in ~90 seconds:
  1. What is this?
  2. Why is the code worth looking at? (the distinctive modeling decisions)
  3. Where do I look next? (repo link, LinkedIn, suggested pages to explore)

Not a resume. Not a feature list. Not a sales pitch. A short framing that
lets a reader make an informed decision about how deep to go.

Kept deliberately terse — the app pages themselves ARE the substance; this
page just gives them the context to be read as such.
"""

import streamlit as st


REPO_URL = "https://github.com/terrydougan-ai/okr-planning-app"
LINKEDIN_URL = "https://www.linkedin.com/in/terrydougan/"
PROFILE_REPO_URL = "https://github.com/terrydougan-ai"


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("👋 About this project")

st.markdown(
    """
    This is a personal portfolio project — a sketch in code of what an OKR
    system that respected the distinctions between delivery, impact, and
    intent might look like. Built to make a few specific modeling decisions
    visible, then to show what changes when those decisions are treated as
    first-class instead of collapsed into a single "progress" bar.

    It's also a small sample of what it looks like when AI tooling meets
    the work of strategic planning and execution — a working system built at a
    pace only possible when architecture is your job and implementation is
    delegated to an AI collaborator. The modeling decisions and structural
    choices are mine; the implementation velocity comes from working with
    Claude Code as a partner rather than a code generator.

    The public repo has the full README, the schema, and the design
    rationale behind each decision. This app is the working artifact.
    """
)


# -----------------------------------------------------------------------------
# The design thesis — five distilled decisions
# -----------------------------------------------------------------------------
st.divider()
st.subheader("What's distinctive about it")

st.markdown(
    """
    Most OKR tools optimize for a polished UI on top of a thin data model, or
    depth aimed at large enterprises. This project sits somewhere else — a
    substrate for the modeling choices most tools fudge.

    **Delivery, impact, and ROI are three different measurements.** An
    initiative can ship 100% and move 0% of its target KR. Both facts are
    kept visible, not collapsed into a single bar.

    **Milestone status (team view) and Exec RAG (exec view) are separate
    fields.** When they diverge, that's itself a signal — surfaced inline on
    Hotspots as *"exec 🚧 blocked / team 🟡 at risk"*.

    **KRs get updated directly; initiatives don't update KRs.** A KR is a
    measurement of reality — the world moves it whether or not your bet
    shipped. Actual attribution to specific initiatives is a separate,
    retrospective claim.

    **Leading vs lagging is a declarative tag, not a rollup tree.** The
    causal hypothesis is visible without forcing weights that inevitably
    become noise. Schema retains the parent-KR infrastructure as latent
    optionality.

    **Initiatives belong to a team, not just to the KRs they move.** A
    platform team can run an initiative that moves a revenue team's KR —
    the right model for cross-functional work.
    """
)


# -----------------------------------------------------------------------------
# Suggested tour — the two most demonstrative pages
# -----------------------------------------------------------------------------
st.divider()
st.subheader("What to look at")

st.markdown(
    """
    Two pages carry most of the design intent:

    - **🔥 Hotspots** shows how the modeling produces a triage view — each
      team's health rolled up as a card, expandable to show the specific
      problems that need attention. Note the exec-vs-team divergence
      surfaced inline where they disagree.

    - **🧭 Objectives & KRs** shows the causal cascade, KR by KR — each
      Key Result renders with its supporting initiatives as a small
      table underneath. Note the ownership vs. contribution distinction
      when an initiative from one team moves another team's KR.

    Plan Flow, Plan Narrative, and the Initiatives page provide different
    reads on the same data — a Sankey, a document, and a portfolio view.
    """
)


# -----------------------------------------------------------------------------
# Links + author
# -----------------------------------------------------------------------------
st.divider()
st.subheader("Where to go from here")

lc1, lc2 = st.columns(2)
with lc1:
    st.markdown(
        f"""
        **The code, README, and schema**
        [github.com/terrydougan-ai/okr-planning-app]({REPO_URL})
        """
    )
with lc2:
    st.markdown(
        f"""
        **The author**
        [Terry Dougan on LinkedIn]({LINKEDIN_URL})
        More work at [github.com/terrydougan-ai]({PROFILE_REPO_URL})
        """
    )


# -----------------------------------------------------------------------------
# Data disclaimer
# -----------------------------------------------------------------------------
st.divider()
st.caption(
    "The data in this demo is **fictional** — a scenario built around "
    "*Acme Analytics*, a made-up analytics SaaS company in mid-Q3 2026. "
    "Any resemblance to real companies, KRs, or initiatives is coincidental. "
    "The demo database is periodically reset, so changes made through the "
    "app may not persist."
)

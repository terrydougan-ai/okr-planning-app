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
LINKEDIN_URL = "https://www.linkedin.com/in/terry-dougan-0aa8565/"
PROFILE_REPO_URL = "https://github.com/terrydougan-ai"


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("👋 About this project")

st.markdown(
    f"""
    I've spent a lot of my career watching planning processes and tools 
    flatten distinctions that matter. A team reports "we're 80% done shipping"
    — but the scope quietly changed halfway through, so 80% of a smaller
    thing doesn't mean what it did last month. A dashboard reports
    "on track against our release" — but nobody notices we're nowhere
    close to the outcomes the release was supposed to drive, and often
    nobody wrote those outcomes down in the first place. Exec dashboards
    show green while the team on the ground knows something is wrong. Or
    Exec dashboards that highlight everything and the important things get
    lost in the noise.

    This app is my take on what an OKR system that respects the
    distinctions between outputs and outcomes and what might happen 
    if delivery, impact, and intent were all important. A small, working 
    portfolio piece — not a product — built to demonstrate a specific set
    of modeling decisions.

    This has been a fun exercise for me — exploring current AI capabilities
    while designing something that fits a real need many companies have and
    few tools meet directly. The concept, design, architectural calls and
    modeling decisions are mine; Claude Code did a lot of the heavy lifting
    on the implementation. Send me your feedback via [LinkedIn]({LINKEDIN_URL})
    — I'm always looking to improve, and eager to learn about your use cases
    and how something like this might address them.
    """
)


# -----------------------------------------------------------------------------
# The framework — visual of Strategy → Objectives → KRs → Initiatives
# -----------------------------------------------------------------------------
st.divider()
st.subheader("How the framework maps")

st.markdown(
    """
    The cascade the app models, top to bottom:
    """
)

# Inline SVG diagram — four horizontal bands showing the cascade
FRAMEWORK_SVG = """
<svg viewBox="0 0 800 460" xmlns="http://www.w3.org/2000/svg"
     style="width:100%;max-width:800px;height:auto;">

  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10"
            refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#9CA3AF" />
    </marker>
  </defs>

  <!-- Layer 1: Strategy -->
  <rect x="250" y="15" width="300" height="60" rx="6"
        fill="#EDE9FE" stroke="#7C3AED" stroke-width="2"/>
  <text x="400" y="40" text-anchor="middle"
        font-family="system-ui" font-size="14" font-weight="700" fill="#5B21B6">
    Strategy
  </text>
  <text x="400" y="60" text-anchor="middle"
        font-family="system-ui" font-size="11" fill="#5B21B6">
    Top-level strategic bets · multi-year framing
  </text>

  <!-- Arrow 1 -->
  <line x1="400" y1="78" x2="400" y2="102" stroke="#9CA3AF"
        stroke-width="1.5" marker-end="url(#arrowhead)"/>

  <!-- Layer 2: Objectives (two sub-boxes: yearly + quarterly) -->
  <rect x="80" y="107" width="640" height="80" rx="6"
        fill="#DBEAFE" stroke="#2563EB" stroke-width="2"/>
  <text x="400" y="130" text-anchor="middle"
        font-family="system-ui" font-size="14" font-weight="700" fill="#1E3A8A">
    Objectives
  </text>
  <!-- Yearly sub-box -->
  <rect x="120" y="140" width="270" height="38" rx="4"
        fill="#EFF6FF" stroke="#60A5FA" stroke-width="1"/>
  <text x="255" y="158" text-anchor="middle"
        font-family="system-ui" font-size="12" font-weight="600" fill="#1E3A8A">
    Yearly Objectives
  </text>
  <text x="255" y="172" text-anchor="middle"
        font-family="system-ui" font-size="10" fill="#1E40AF">
    Annual outcomes · aspirational KRs
  </text>
  <!-- Quarterly sub-box -->
  <rect x="410" y="140" width="270" height="38" rx="4"
        fill="#EFF6FF" stroke="#60A5FA" stroke-width="1"/>
  <text x="545" y="158" text-anchor="middle"
        font-family="system-ui" font-size="12" font-weight="600" fill="#1E3A8A">
    Quarterly Objectives
  </text>
  <text x="545" y="172" text-anchor="middle"
        font-family="system-ui" font-size="10" fill="#1E40AF">
    This-quarter goals · roll up to yearly
  </text>

  <!-- Arrow 2 -->
  <line x1="400" y1="190" x2="400" y2="214" stroke="#9CA3AF"
        stroke-width="1.5" marker-end="url(#arrowhead)"/>

  <!-- Layer 3: Key Results (with leading/lagging annotation) -->
  <rect x="80" y="219" width="640" height="100" rx="6"
        fill="#D1FAE5" stroke="#059669" stroke-width="2"/>
  <text x="400" y="242" text-anchor="middle"
        font-family="system-ui" font-size="14" font-weight="700" fill="#064E3B">
    Key Results
  </text>
  <text x="400" y="258" text-anchor="middle"
        font-family="system-ui" font-size="11" fill="#065F46">
    Measurable outcomes · tagged by indicator type
  </text>
  <!-- Lagging tag -->
  <rect x="140" y="272" width="240" height="38" rx="4"
        fill="#FEE2E2" stroke="#DC2626" stroke-width="1"/>
  <text x="260" y="290" text-anchor="middle"
        font-family="system-ui" font-size="12" font-weight="600" fill="#991B1B">
    🎯 Lagging
  </text>
  <text x="260" y="304" text-anchor="middle"
        font-family="system-ui" font-size="10" fill="#991B1B">
    The outcome you care about · measured after the fact
  </text>
  <!-- Leading tag -->
  <rect x="420" y="272" width="240" height="38" rx="4"
        fill="#DBEAFE" stroke="#2563EB" stroke-width="1"/>
  <text x="540" y="290" text-anchor="middle"
        font-family="system-ui" font-size="12" font-weight="600" fill="#1E3A8A">
    📡 Leading
  </text>
  <text x="540" y="304" text-anchor="middle"
        font-family="system-ui" font-size="10" fill="#1E3A8A">
    An early signal · predicts the lagging outcome
  </text>

  <!-- Arrow 3 (curved feedback showing initiatives move KRs) -->
  <line x1="400" y1="322" x2="400" y2="346" stroke="#9CA3AF"
        stroke-width="1.5" marker-end="url(#arrowhead)"/>

  <!-- Layer 4: Initiatives -->
  <rect x="250" y="351" width="300" height="80" rx="6"
        fill="#FEF3C7" stroke="#D97706" stroke-width="2"/>
  <text x="400" y="378" text-anchor="middle"
        font-family="system-ui" font-size="14" font-weight="700" fill="#78350F">
    Initiatives
  </text>
  <text x="400" y="396" text-anchor="middle"
        font-family="system-ui" font-size="11" fill="#92400E">
    The bets you're making to move the KRs
  </text>
  <text x="400" y="414" text-anchor="middle"
        font-family="system-ui" font-size="10" fill="#92400E" font-style="italic">
    Delivery, impact, and business case are tracked separately
  </text>
</svg>
"""

# Render the SVG via st.components.v1.html. Streamlit's markdown renderer
# strips SVG tags for security, so components.v1.html (which uses an iframe)
# is the reliable path for inline vector graphics. Height is set to the
# SVG's viewBox height plus a small margin so it doesn't get clipped.
import streamlit.components.v1 as components
components.html(FRAMEWORK_SVG, height=480, scrolling=False)


# -----------------------------------------------------------------------------
# The design thesis — five distilled decisions
# -----------------------------------------------------------------------------
st.divider()
st.subheader("The specific modeling decisions")

st.markdown(
    """
    **Delivery, impact, and ROI are three different measurements.** An
    initiative can ship 100% and move 0% of its target KR. Both facts are
    kept visible, not collapsed into a single "progress" number.

    **Milestone status (team view) and Exec RAG (exec view) are separate
    fields.** When they diverge, that's itself a signal — surfaced inline on
    Hotspots as *"exec 🚧 blocked / team 🟡 at risk"*. When they agree,
    both sides of the org can trust the picture.

    **KRs get updated directly; initiatives don't update KRs.** A KR is a
    measurement of reality. The world moves it whether or not your bet
    shipped. Attribution to specific initiatives is a separate,
    retrospective claim — recorded on Initiative Updates, not inferred from
    KR movement.

    **Leading vs lagging is a declarative tag, not a rollup tree.** Weighted
    rollups turn into noise fast — nobody really knows if qualified pipeline
    drives ARR at 0.4 or 0.6. So each KR gets tagged 🎯 Lagging, 📡 Leading,
    or standalone. The causal hypothesis is visible without the false
    precision.

    **Initiatives belong to a team, not just to the KRs they move.** A
    platform team can run an initiative that moves a revenue team's KR.
    That's the right model for cross-functional work, and the schema
    treats team ownership and KR contribution as independent relationships.
    """
)


# -----------------------------------------------------------------------------
# Suggested tour — the two most demonstrative pages
# -----------------------------------------------------------------------------
st.divider()
st.subheader("What to look at first")

st.markdown(
    """
    Two pages carry most of the design intent:

    - **🔥 Hotspots** shows how the modeling produces a triage view — each
      team's health rolled up as a card, expandable to show the specific
      problems that need attention. Note the exec-vs-team divergence
      surfaced inline where they disagree.

    - **🧭 Objectives & KRs** shows the causal cascade, KR by KR — each
      Key Result renders with its supporting initiatives as a small table
      underneath. Note the ownership vs. contribution distinction when an
      initiative from one team moves another team's KR.

    Plan Flow, Plan Narrative, and the Initiatives page give three different
    reads on the same data: a Sankey, a document, and a portfolio view.
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
# Data disclaimer + invitation to explore
# -----------------------------------------------------------------------------
st.divider()
st.caption(
    "Feel free to poke around — edit KRs, add initiatives, break things. "
    "The data is **fictional** (a scenario built around *Acme Analytics*, "
    "a made-up analytics SaaS company in mid-Q3 2026), and the database "
    "is periodically reset from a versioned seed script in the repo, so "
    "you can't break anything permanent."
)

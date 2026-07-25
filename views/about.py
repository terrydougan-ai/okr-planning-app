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

# Analytics — silently no-op when POSTHOG_API_KEY isn't configured
from views._analytics import track_page


REPO_URL = "https://github.com/terrydougan-ai/okr-planning-app"
LINKEDIN_URL = "https://www.linkedin.com/in/terrydougan/"
PROFILE_REPO_URL = "https://github.com/terrydougan-ai"


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
track_page("About")
st.title("👋 About this project")

st.markdown(
    f"""
    Earlier in my career I ran the kind of program office work you'd
    expect — I spent real time consolidating status reports across
    projects into consistent templates, so a VP wasn't reading ten
    different formats a week. That work matters. But once it was done,
    it exposed a deeper problem: consistent format doesn't mean relevant
    content. What actually needed a VP's attention on any given Monday
    kept shifting — new customer pressure, a hiring decision, something
    from a board conversation — and my read on what would rise to the
    top could be off, because their view of the week ahead was often
    ahead of mine.

    The other pattern I saw: writing for executives is a specific skill
    many PMs haven't developed. When something needed a nuanced update,
    some PMs could produce it well and some couldn't — not because they
    didn't have the information, but because the exec-writing muscle is
    different from the ops-writing one.

    This app is my take on what an OKR system that took those two
    problems seriously might look like. It lets strategy flow into
    objectives and the key results that define them, then tracks how
    initiatives contribute to those key results, objectives, and
    strategy. Outputs and outcomes both, measured against the plan.
    I've used AI along the way — to help define and measure, and to
    find signals in the data that surface risks earlier than a team
    would normally catch them on their own. There are a few different
    axes on which AI shows up in the workflow, and I've tried to be
    deliberate about which ones move first.

    Feedback is welcome via [LinkedIn]({LINKEDIN_URL}).
    """
)


# -----------------------------------------------------------------------------
# Three problems this app addresses
# -----------------------------------------------------------------------------
st.divider()
st.subheader("Three problems this app addresses")

st.markdown(
    """
    **Connect work to outcomes, and outcomes to strategy.**
    Teams do work. Leaders set goals. But too often the connection between
    them is implicit, verbal, or lost in the gap between project trackers
    and OKR tools. This app treats the chain — strategy → yearly objective
    → quarterly objective → KR → initiative — as first-class, visible on
    every page. An initiative names which KRs it moves and by how much
    (predicted). Later, retrospective attribution names what actually
    moved (actual). The through-line stays visible.

    **Give leaders a focused view of what matters, not a firehose of data.**
    Executive dashboards drown people in numbers when what they need is
    *judgment about where to look*. Hotspots reads the same underlying
    data an operational team looks at, and produces an AI-generated
    summary at the top: three sentences on what needs attention, what's
    escalating, what's healthy — including cross-functional patterns
    where one team's work is moving another team's KR. The dashboard is
    still there below, but you don't have to work through it to know
    where to focus.

    **Help PMs write updates that actually help.**
    Having spent years reading status updates from project and product
    managers, I know the pattern: a busy PM writes a vague "on track" or
    a generic "some blockers," and a leader has to reply with clarifying
    questions to get the picture. The app addresses this two ways. If a
    PM has the context to write the update, the AI review scores it
    against Clarity, Consistency, Completeness, and Realism — flagging
    what a leader would ask before the leader has to ask. If the PM
    would benefit from a starting point, the AI drafts a first version
    from the initiative's current state, prior narrative, linked KRs,
    and ambient signals (simulated Jira, Slack, and calendar activity
    in this demo) — the PM edits from there. Two modes, chosen per
    update. Both are coaching, not gatekeeping.
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

# Analytics — silently no-op when POSTHOG_API_KEY isn't configured

components.html(FRAMEWORK_SVG, height=480, scrolling=False)


# -----------------------------------------------------------------------------
# The design thesis — the distilled modeling decisions
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
    treats team ownership and KR contribution as independent
    relationships. The Hotspots page has a dedicated panel that surfaces
    these cross-team patterns — where TPM coordination usually lives.

    **Ambient signals feed the AI, not just what humans typed in.** In
    the demo, each initiative has a **📡 Recent activity** panel that
    shows simulated Jira / Slack / calendar signals. The AI drafting
    feature reads these when producing a check-in — which is what lets
    the AI catch things the previous exec narrative missed. In
    production this would be real integrations; the shape of what the
    AI consumes is what a production version would look like.

    **AI shows up in more than one shape.** The app uses Claude Sonnet
    and Haiku across a few different moments: proposing KR drafts on the
    planning surface (Suggest KRs), summarizing Hotspots for exec review,
    reviewing check-ins against a Clarity / Consistency / Completeness /
    Realism rubric, and drafting check-ins from ambient signals when the
    PM wants a starting point. Some of these are the human-writes / AI-
    reviews pattern; others are the AI-drafts / human-reviews pattern.
    Both patterns are valid; the app makes the choice per-update
    explicit rather than picking one.
    """
)


# -----------------------------------------------------------------------------
# Suggested tour — the two most demonstrative pages
# -----------------------------------------------------------------------------
st.divider()
st.subheader("What to look at first")

st.markdown(
    """
    A short tour, if you have five minutes:

    - **🔥 Hotspots** — the exec view. An AI-generated summary sits at
      the top; below it, a **Cross-functional patterns** panel shows
      where one team's work is moving another team's KR. Then per-team
      roll-up cards, expandable to specific problems. Look for the
      exec-vs-team divergence flagged inline.

    - **📊 Initiative Check-ins** → **Query engine caching layer** —
      the AI-native piece. Expand the initiative, open the
      **📡 Recent activity** expander to see the simulated Jira /
      Slack / calendar signals, then click **✨ Draft with AI**. The
      AI reads the ambient signals, prior narrative, and current state,
      and produces a first draft that names specific tickets,
      incidents, and rescheduled meetings — surfacing what the previous
      narrative was smoothing over. This is where the workflow inverts:
      the PM edits an AI-drafted update rather than writing from a
      blank field.

    - **🧭 Objectives & KRs** — the causal cascade. Strategy → Yearly
      Objectives → Quarterly Objectives → KRs → Initiatives with their
      contribution to each KR. Note the ownership vs contribution
      distinction when an initiative from one team moves another
      team's KR.

    Planning Flow, Executive Narrative, and Initiatives give three
    additional reads on the same data: a Sankey, a document, and a
    portfolio view. On **✏️ Plan a Quarter**, each objective has an
    **✨ Suggest KRs** button that asks Claude to propose two or three
    draft KRs given the objective's context.
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

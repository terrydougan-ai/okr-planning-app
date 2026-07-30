"""
Prioritization — Impact × Effort matrix for initiatives.

The classic PM prioritization artifact, built into the app so it draws on
the data already there: predicted KR impact, effort estimate, ambient
signal load, business case ROI, cross-functional links. AI proposes an
initial scoring with reasoning; the human adjusts. Same pattern as the
check-in drafts — AI does the synthesis from context, the human owns
the decision.

Two views on one page:
  - Impact × Effort matrix (2x2 quadrant chart, bubble per initiative)
  - Ranked list below (score decomposition + AI reasoning per axis)

Design decision worth naming: no full RICE or ICE score. Strategic weight
is already carried by the OKR structure — initiatives that don't ladder
up to a meaningful KR don't need a score to be deprioritized. This page
sequences among initiatives that already ladder up.

Scoring model:
  Impact (1-5):
    Signal from — linked KR gap severity, number of KRs linked (breadth),
    whether cross-functional (moving another team's KR), predicted KR
    impact size, business case predicted value.
  Effort (1-5):
    Signal from — effort_estimate T-shirt size, delivery % remaining,
    ambient signal load (blockers raise effort), milestone status (blocked
    or at_risk raises effort).

Both axes have a deterministic Python computation as the baseline. Users
can accept the baseline, tune it manually, or click "Suggest with AI" to
have Claude propose scores with reasoning per initiative.
"""

import json
import streamlit as st
import pandas as pd
from supabase import create_client, Client
import plotly.graph_objects as go

# Optional imports — degrade gracefully if these helpers aren't present.
try:
    from views._analytics import track_page
    track_page("Prioritization")
except Exception:
    pass

try:
    from views._ai_helpers import is_ai_enabled, MODEL_SONNET
except Exception:
    def is_ai_enabled():
        return False
    MODEL_SONNET = "claude-sonnet-4-6"


# Initialize the Anthropic client directly (mirrors the pattern in
# _ai_helpers.py so we don't need a helper import that may not exist).
def _get_claude_client():
    """Return an Anthropic client instance, or None if not available."""
    try:
        import anthropic
        api_key = st.secrets.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        return anthropic.Anthropic(api_key=api_key)
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Supabase
# -----------------------------------------------------------------------------
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


sb = get_supabase()


# -----------------------------------------------------------------------------
# Data loading
# -----------------------------------------------------------------------------
def _try_load(table_name: str, required: bool = False) -> pd.DataFrame:
    """Load a table from Supabase.

    - If required=True, surfaces the exception to the caller (via st.error).
    - If required=False, returns empty DataFrame on failure (used for
      optional tables like the ambient signals).
    """
    try:
        result = sb.table(table_name).select("*").execute()
        return pd.DataFrame(result.data)
    except Exception as e:
        if required:
            st.error(f"Failed to load `{table_name}` from Supabase: {e}")
            raise
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_all():
    return {
        # Required tables — bail loudly if these can't load
        "initiatives": _try_load("initiative", required=True),
        "links": _try_load("initiative_key_result", required=True),
        "key_results": _try_load("key_result", required=True),
        "objectives": _try_load("objective", required=True),
        "org_units": _try_load("org_unit", required=True),
        # Optional tables — degrade gracefully
        "business_cases": _try_load("business_case"),
        "engineering_activity": _try_load("engineering_activity"),
        "team_message": _try_load("team_message"),
        "calendar_event": _try_load("calendar_event"),
    }


# -----------------------------------------------------------------------------
# Deterministic scoring — the baseline that AI (or a human) can adjust
# -----------------------------------------------------------------------------
# Effort T-shirt sizes map to numeric effort. Kept in the middle of the 1-5
# range so ambient signals and status can raise or lower.
EFFORT_SIZE_MAP = {
    "XS": 1.0, "S": 2.0, "M": 3.0, "L": 4.0, "XL": 5.0,
    "": 3.0, None: 3.0,
}


def _kr_progress(start, target, current) -> float:
    """Fraction of KR gap closed. Returns 0..1. Guards against nulls and
    zero-denominator."""
    if start is None or target is None or current is None:
        return 0.0
    try:
        if target == start:
            return 0.0
        return max(0.0, min(1.0, (current - start) / (target - start)))
    except (TypeError, ZeroDivisionError):
        return 0.0


def compute_impact_score(
    init, init_links, key_results_df, objectives_df, business_cases_df
) -> tuple:
    """Return (score_1_to_5, decomposition_dict).

    Impact scoring anchors on **annualized revenue impact × time horizon**
    (the lifetime impact figure), log-scaled so a $10M initiative doesn't
    dominate a $1M one by 10x. That's the apples-to-apples signal — the
    dollar amount, plus its horizon.

    Everything else — KR gap severity, cross-functional weight, breadth —
    are structural adjustments layered on top. They shift the anchor score
    by ±0.5 total, not more. If revenue impact isn't quantified for an
    initiative, we fall back to the structural signals alone and label it
    as "not quantified" honestly.

    The decomposition dict is used both in the ranked list display and as
    context passed to the AI proposal.
    """
    import math
    decomp = {}
    signals = []

    # -------------------------------------------------------------------
    # Anchor: lifetime revenue impact, log-scaled
    # -------------------------------------------------------------------
    bc_row = business_cases_df[business_cases_df["initiative_id"] == init["id"]]
    revenue_impact = None
    horizon_years = 1
    category = None

    if not bc_row.empty:
        bc = bc_row.iloc[0]
        # Prefer the new explicit field; fall back to predicted_value
        _new = bc.get("revenue_impact_usd_annual")
        _old = bc.get("predicted_value")
        revenue_impact = _new if _new not in (None, 0) else _old
        _horizon = bc.get("time_horizon_years")
        horizon_years = int(_horizon) if _horizon else 1
        category = bc.get("revenue_impact_category")

    if revenue_impact and revenue_impact > 0:
        lifetime_impact = float(revenue_impact) * horizon_years

        # Log scale: $100K → ~1.5, $1M → ~2.5, $10M → ~3.5, $100M → ~4.5
        # Formula: 1.5 + log10(lifetime_impact / 100_000)
        # Clamped to [1.0, 5.0].
        anchor = 1.5 + math.log10(max(lifetime_impact, 1) / 100_000)
        anchor = max(1.0, min(5.0, anchor))
        score = anchor

        decomp["revenue_impact_usd_annual"] = float(revenue_impact)
        decomp["time_horizon_years"] = horizon_years
        decomp["lifetime_impact"] = lifetime_impact
        decomp["revenue_impact_category"] = category or "unspecified"
        decomp["anchor_from_revenue"] = round(anchor, 2)
        decomp["quantified"] = True

        _cat_label = {
            "new_revenue": "new revenue",
            "retention": "retention",
            "cost_savings": "cost savings",
            "risk_mitigation": "risk mitigation",
        }.get(category, "revenue impact")
        signals.append(
            f"${revenue_impact/1_000_000:.1f}M/year {_cat_label}"
            f" over {horizon_years}y → ${lifetime_impact/1_000_000:.1f}M lifetime"
            f" (anchors score at {anchor:.1f})"
        )
    else:
        # No quantified revenue impact — fall back to a mid-scale anchor
        # and let structural signals move the score. Also mark as unquantified.
        score = 2.5
        decomp["quantified"] = False
        signals.append(
            "Revenue impact not quantified — score based on structural signals only"
        )

    # -------------------------------------------------------------------
    # Structural adjustments (total range: -0.5 to +0.5)
    # -------------------------------------------------------------------
    if init_links.empty:
        # Not linked to any KR — this is a real problem. Strong penalty.
        signals.append("No KR links — not laddered to strategy (-0.5)")
        score -= 0.5
        decomp["linked_krs"] = 0
    else:
        linked_kr_ids = init_links["key_result_id"].tolist()
        decomp["linked_krs"] = len(linked_kr_ids)

        # 1) KR gap severity — how far from target across linked KRs. Small boost
        #    because urgent KRs matter, but bounded so it doesn't overwhelm the
        #    revenue anchor.
        gaps = []
        for kr_id in linked_kr_ids:
            kr_row = key_results_df[key_results_df["id"] == kr_id]
            if kr_row.empty:
                continue
            kr = kr_row.iloc[0]
            progress = _kr_progress(
                kr.get("start_value"), kr.get("target_value"), kr.get("current_value")
            )
            gaps.append(1.0 - progress)

        if gaps:
            avg_gap = sum(gaps) / len(gaps)
            gap_boost = avg_gap * 0.3  # up to +0.3
            score += gap_boost
            decomp["avg_kr_gap"] = round(avg_gap, 2)
            if gap_boost > 0.05:
                signals.append(
                    f"linked KRs {avg_gap:.0%} gap-to-target (+{gap_boost:.1f})"
                )

        # 2) Cross-functional — moving another team's KR is amplified impact
        init_org_id = init.get("org_unit_id")
        cross_functional = False
        for kr_id in linked_kr_ids:
            kr_row = key_results_df[key_results_df["id"] == kr_id]
            if kr_row.empty:
                continue
            kr = kr_row.iloc[0]
            obj_row = objectives_df[objectives_df["id"] == kr.get("objective_id")]
            if obj_row.empty:
                continue
            obj = obj_row.iloc[0]
            kr_org_id = obj.get("org_unit_id")
            if kr_org_id and init_org_id and kr_org_id != init_org_id:
                cross_functional = True
                break
        decomp["cross_functional"] = cross_functional
        if cross_functional:
            score += 0.2
            signals.append("cross-functional (moves another team's KR) (+0.2)")

    # Clamp final score
    score = max(1.0, min(5.0, score))
    decomp["signals"] = signals
    return round(score, 1), decomp


def compute_effort_score(
    init, engineering_activity_df, team_message_df, calendar_event_df
) -> tuple:
    """Return (score_1_to_5, decomposition_dict). Higher = more effort remaining."""
    decomp = {}
    signals = []

    # Anchor on t-shirt size, which is the human estimate
    size = init.get("effort_estimate") or ""
    score = EFFORT_SIZE_MAP.get(size, 3.0)
    decomp["t_shirt_size"] = size or "unspecified"
    if size:
        signals.append(f"effort estimate: {size}")

    # Delivery % remaining — if 80% done, remaining effort is small
    progress = float(init.get("progress_pct") or 0)
    remaining = 1.0 - (progress / 100.0)
    # Scale the size by remaining. If 60% delivered, remaining effort is 40%
    # of the original.
    if remaining < 1.0:
        adjusted = score * remaining
        # Blend: 60% original size sense, 40% remaining. Full override felt
        # too aggressive in testing.
        score = (0.6 * score) + (0.4 * (adjusted + 1.0))
        signals.append(f"{progress:.0f}% delivered, remaining effort scaled")
        decomp["delivery_pct"] = progress

    # Milestone status — blocked or at_risk raises effort meaningfully
    ms = init.get("milestone_status")
    if ms == "blocked":
        score += 1.0
        signals.append("blocked milestone status (+1.0)")
    elif ms == "at_risk":
        score += 0.5
        signals.append("at-risk milestone status (+0.5)")
    decomp["milestone_status"] = ms or "not set"

    # Ambient signal load — blocker signals in engineering activity, escalation
    # sentiment in team messages, rescheduled meetings all suggest more effort
    # remaining than the size implies.
    init_id = init["id"]
    blocker_activity = 0
    if not engineering_activity_df.empty:
        init_eng = engineering_activity_df[
            engineering_activity_df["initiative_id"] == init_id
        ]
        blocker_activity = len(init_eng[init_eng["activity_type"] == "blocker_flagged"])

    escalation_messages = 0
    if not team_message_df.empty:
        init_msg = team_message_df[team_message_df["initiative_id"] == init_id]
        escalation_messages = len(
            init_msg[init_msg["sentiment"].isin(["concerned", "escalation"])]
        )

    rescheduled_events = 0
    if not calendar_event_df.empty:
        init_evt = calendar_event_df[calendar_event_df["initiative_id"] == init_id]
        rescheduled_events = len(
            init_evt[init_evt["outcome"].astype(str).str.contains(
                "RESCHEDULED", case=False, na=False
            )]
        )

    signal_load = blocker_activity + escalation_messages + rescheduled_events
    if signal_load > 0:
        boost = min(1.0, signal_load * 0.3)
        score += boost
        signals.append(
            f"ambient trouble signals: {signal_load} "
            f"({blocker_activity} blockers, {escalation_messages} escalations, "
            f"{rescheduled_events} rescheduled) (+{boost:.1f})"
        )
    decomp["signal_load"] = signal_load

    # Clamp
    score = max(1.0, min(5.0, score))
    decomp["signals"] = signals
    return round(score, 1), decomp


# -----------------------------------------------------------------------------
# AI proposal — asks Claude to review deterministic scores and propose
# adjustments with reasoning
# -----------------------------------------------------------------------------
def ai_propose_scores(initiatives_with_scores: list) -> dict:
    """Ask Claude Sonnet to review the deterministic scores and propose
    adjustments where its reading of the context suggests different.

    Returns {initiative_id: {"impact": float, "effort": float, "reasoning": str}}
    or {} on failure.
    """
    client = _get_claude_client()
    if client is None:
        return {}

    # Build compact context for the prompt
    lines = ["INITIATIVES TO SCORE:"]
    for row in initiatives_with_scores:
        lines.append(
            f"\n[{row['id']}] {row['title']}"
            f"\n  Owning team: {row['owning_team']}"
            f"\n  Status: {row['status']}, milestone: {row['milestone_status']}, "
            f"delivery: {row['progress_pct']}%"
            f"\n  Effort estimate: {row['effort_estimate']}"
            f"\n  Baseline impact score: {row['baseline_impact']}"
            f"\n  Baseline effort score: {row['baseline_effort']}"
            f"\n  Impact signals: {'; '.join(row['impact_signals']) or 'none'}"
            f"\n  Effort signals: {'; '.join(row['effort_signals']) or 'none'}"
        )
    context_block = "\n".join(lines)

    prompt = f"""You are helping a senior PM sequence initiatives on an Impact × Effort matrix.

A deterministic Python computation has already produced baseline scores from the app's structured data. Your job is to review each initiative and propose an adjustment when the qualitative context — the mix of signals, the team's position, the strategic weight of the linked KRs — suggests the baseline is meaningfully off.

For each initiative, decide:
  - Impact score (1.0 to 5.0): keep the baseline OR adjust by ±0.5 or ±1.0 max
  - Effort score (1.0 to 5.0): keep the baseline OR adjust by ±0.5 or ±1.0 max
  - Reasoning: 1-2 sentences naming the specific signal or context that justified adjustment (or "baseline is right" if unchanged)

Be conservative. Adjust only when a specific signal in the context justifies it. Do not adjust for "seems risky" or "feels important" — those are the PM's judgments to make, not yours.

{context_block}

Return ONLY a JSON object mapping initiative id to {{impact, effort, reasoning}}. No prose outside the JSON.

Example format:
{{
  "10000000-...": {{"impact": 4.0, "effort": 3.5, "reasoning": "Baseline impact 3.5 — raising to 4 because this is the only initiative moving a company-level KR that's at 12% of target. Effort baseline is right."}},
  ...
}}

Respond now."""

    try:
        response = client.messages.create(
            model=MODEL_SONNET,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw += block.text
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            return {}
        # Clamp to 1-5
        result = {}
        for k, v in parsed.items():
            if not isinstance(v, dict):
                continue
            result[k] = {
                "impact": max(1.0, min(5.0, float(v.get("impact", 3.0)))),
                "effort": max(1.0, min(5.0, float(v.get("effort", 3.0)))),
                "reasoning": str(v.get("reasoning", "")).strip(),
            }
        return result
    except Exception as e:
        print(f"[AI] ai_propose_scores failed: {e}")
        return {}


# -----------------------------------------------------------------------------
# AI page-level summary — a chief-of-staff-quality read on the whole portfolio
# -----------------------------------------------------------------------------
def ai_summarize_prioritization(summary_context: dict) -> str:
    """Ask Claude Sonnet to synthesize the whole prioritization page into a
    short exec brief: portfolio shape, standouts, data quality gaps, suspicious
    signals, human override patterns.

    Returns the summary text, or empty string on failure.
    """
    client = _get_claude_client()
    if client is None:
        return ""

    # Format the context for the prompt
    quadrants = summary_context.get("quadrant_counts", {})
    quadrant_lines = [
        f"  - Quick wins: {quadrants.get('quick_wins', 0)}",
        f"  - Big bets: {quadrants.get('big_bets', 0)}",
        f"  - Fill-ins: {quadrants.get('fill_ins', 0)}",
        f"  - Reconsider: {quadrants.get('reconsider', 0)}",
    ]

    top_lines = []
    for r in summary_context.get("top_ranked", []):
        top_lines.append(
            f"  - {r['title']} ({r['owning_team']}): "
            f"Impact {r['impact']:.1f} / Effort {r['effort']:.1f}, "
            f"revenue ${r['revenue']/1_000_000:.1f}M/yr × {r['horizon']}y "
            f"({r['category']})"
        )

    bottom_lines = []
    for r in summary_context.get("bottom_ranked", []):
        bottom_lines.append(
            f"  - {r['title']} ({r['owning_team']}): "
            f"Impact {r['impact']:.1f} / Effort {r['effort']:.1f}"
        )

    quality_lines = []
    dq = summary_context.get("data_quality", {})
    if dq.get("no_kr_link"):
        quality_lines.append(
            f"  - {len(dq['no_kr_link'])} initiative(s) without KR links: "
            f"{', '.join(dq['no_kr_link'][:4])}"
        )
    if dq.get("no_business_case"):
        quality_lines.append(
            f"  - {len(dq['no_business_case'])} initiative(s) without a business case: "
            f"{', '.join(dq['no_business_case'][:4])}"
        )
    if dq.get("unquantified_impact"):
        quality_lines.append(
            f"  - {len(dq['unquantified_impact'])} initiative(s) with unquantified revenue impact: "
            f"{', '.join(dq['unquantified_impact'][:4])}"
        )
    if dq.get("no_effort_size"):
        quality_lines.append(
            f"  - {len(dq['no_effort_size'])} initiative(s) with no effort estimate: "
            f"{', '.join(dq['no_effort_size'][:4])}"
        )

    suspicious_lines = []
    for s in summary_context.get("suspicious", []):
        suspicious_lines.append(f"  - {s}")

    override_lines = []
    for o in summary_context.get("overrides", []):
        override_lines.append(f"  - {o}")

    prompt = f"""You are a chief of staff writing a short exec brief on a portfolio prioritization page. A VP will read this to understand the shape of the portfolio and what warrants attention. You are NOT restating the ranked list; you are interpreting it.

PORTFOLIO CONTEXT

Total in-scope initiatives: {summary_context.get('total', 0)}

Quadrant distribution:
{chr(10).join(quadrant_lines)}

Top 3 by Impact/Effort ratio:
{chr(10).join(top_lines) if top_lines else '  (none)'}

Bottom 3 by Impact/Effort ratio:
{chr(10).join(bottom_lines) if bottom_lines else '  (none)'}

Data quality gaps:
{chr(10).join(quality_lines) if quality_lines else '  (none — data is clean)'}

Suspicious signals (initiative-level flags worth naming):
{chr(10).join(suspicious_lines) if suspicious_lines else '  (none)'}

Human override patterns:
{chr(10).join(override_lines) if override_lines else '  (no overrides in this view)'}

TASK

Write a 4-6 sentence brief. Cover in this order:

1. **Portfolio shape** — is it healthy or skewed? Name the shape in one sentence (e.g., "Portfolio skews toward Big Bets with limited Quick Win coverage" or "Balanced portfolio with meaningful spread across quadrants").

2. **What's worth noting at the top or bottom** — name specific initiatives, don't say "some initiatives." If the top-ranked bet is particularly strong or the bottom-ranked one raises questions, say why.

3. **Data quality concerns** — if there are meaningful gaps (unlinked initiatives, missing business cases, unquantified impact), flag them specifically. If not, do not manufacture concern.

4. **Suspicious signals or override patterns** — if any specific initiative is behaving strangely (rated Quick Win but with troubling ambient signals; heavy human override), name it. If not, skip.

WRITING PRINCIPLES

- Reference specific initiatives by name, not "one initiative" or "some teams."
- If the portfolio is genuinely healthy and data is clean, say so plainly. Do NOT invent drama.
- Do not restate the ranked list.
- Do not comment on the framework choice or the app itself.
- Prose only. No bullets, no headers.
- Under 130 words.

Write the brief now."""

    try:
        response = client.messages.create(
            model=MODEL_SONNET,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw += block.text
        return raw.strip()
    except Exception as e:
        print(f"[AI] ai_summarize_prioritization failed: {e}")
        return ""


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("⚖️ Prioritization")
st.caption(
    "Impact × Effort scoring anchored on the business case. **Impact** is "
    "primarily annualized revenue impact (new sales, retention, cost savings, "
    "or risk mitigation) over its time horizon, log-scaled and adjusted for "
    "KR gap severity and cross-functional reach. **Effort** reads from the "
    "T-shirt estimate, delivery %, milestone status, and ambient signal load. "
    "AI can propose adjustments; you always own the final scores. Strategic "
    "weight is carried by the OKR structure above."
)

try:
    data = load_all()
except Exception as e:
    st.error(f"Couldn't reach Supabase: {e}")
    st.stop()

initiatives = data["initiatives"]
links = data["links"]
key_results = data["key_results"]
objectives = data["objectives"]
org_units = data["org_units"]
business_cases = data["business_cases"]
engineering_activity = data["engineering_activity"]
team_message = data["team_message"]
calendar_event = data["calendar_event"]

if initiatives.empty:
    st.info("No initiatives in the database at all. Add some via Create Initiative or seed the data.")
    st.stop()

# -----------------------------------------------------------------------------
# Filters
# -----------------------------------------------------------------------------
# Derive available status values from the data itself so we don't assume a
# fixed set. Any status the app knows about should be selectable.
available_statuses = sorted([
    s for s in initiatives["status"].dropna().unique().tolist() if s
])

# Sensible defaults: exclude done/killed if they exist; otherwise include
# everything so the page isn't empty on first load.
default_statuses = [
    s for s in available_statuses if s not in ("done", "killed")
]
if not default_statuses:
    default_statuses = available_statuses  # fall back to all

fc1, fc2 = st.columns([2, 3])
with fc1:
    if available_statuses:
        status_filter = st.multiselect(
            "Include initiatives with status",
            options=available_statuses,
            default=default_statuses,
        )
    else:
        st.caption("No status values on initiatives — showing all.")
        status_filter = []

with fc2:
    org_options = ["All teams"] + (
        sorted(org_units["name"].dropna().unique().tolist())
        if not org_units.empty else []
    )
    org_filter = st.selectbox("Filter by owning team", options=org_options, index=0)

# Apply filters. If no status filter is set, include everything.
if status_filter:
    in_scope = initiatives[initiatives["status"].isin(status_filter)].copy()
else:
    in_scope = initiatives.copy()

if org_filter != "All teams" and not org_units.empty:
    org_id_map = org_units.set_index("name")["id"].to_dict()
    filter_org_id = org_id_map.get(org_filter)
    if filter_org_id:
        in_scope = in_scope[in_scope["org_unit_id"] == filter_org_id]

if in_scope.empty:
    _status_note = ""
    if status_filter and available_statuses:
        excluded = [s for s in available_statuses if s not in status_filter]
        if excluded:
            _status_note = (
                f" (statuses in data but not selected: {', '.join(excluded)})"
            )
    st.info(
        f"No initiatives match the current filters{_status_note}. "
        "Adjust the filters above to include more."
    )
    st.stop()

# -----------------------------------------------------------------------------
# Compute deterministic baseline scores for every in-scope initiative
# -----------------------------------------------------------------------------
org_name_by_id = (
    org_units.set_index("id")["name"].to_dict() if not org_units.empty else {}
)

scored_rows = []
for _, init in in_scope.iterrows():
    init_links = links[links["initiative_id"] == init["id"]] if not links.empty else pd.DataFrame()

    impact_score, impact_decomp = compute_impact_score(
        init, init_links, key_results, objectives, business_cases
    )
    effort_score, effort_decomp = compute_effort_score(
        init, engineering_activity, team_message, calendar_event
    )

    scored_rows.append({
        "id": init["id"],
        "title": init.get("title", "?"),
        "owning_team": org_name_by_id.get(init.get("org_unit_id"), "—"),
        "status": init.get("status"),
        "milestone_status": init.get("milestone_status") or "not set",
        "progress_pct": int(init.get("progress_pct") or 0),
        "effort_estimate": init.get("effort_estimate") or "unspecified",
        "baseline_impact": impact_score,
        "baseline_effort": effort_score,
        "impact_decomp": impact_decomp,
        "effort_decomp": effort_decomp,
        "impact_signals": impact_decomp.get("signals", []),
        "effort_signals": effort_decomp.get("signals", []),
    })

# -----------------------------------------------------------------------------
# AI proposal — session-cached to avoid re-running on every rerender
# -----------------------------------------------------------------------------
_ai_key = f"prioritization_ai_proposals_{org_filter}_{','.join(sorted(status_filter))}"
ai_proposals = st.session_state.get(_ai_key, {})

ai_c1, ai_c2 = st.columns([1, 3])
with ai_c1:
    if is_ai_enabled():
        if st.button(
            "✨ Suggest with AI",
            use_container_width=True,
            help=(
                "Ask Claude to review the calculated scores against the initiative "
                "context and propose adjustments with reasoning. Adjustments are "
                "capped at ±1.0; the AI is prompted to be conservative."
            ),
        ):
            with st.spinner("Reviewing scores..."):
                proposals = ai_propose_scores(scored_rows)
            if proposals:
                st.session_state[_ai_key] = proposals
                ai_proposals = proposals
                st.rerun()
            else:
                st.warning(
                    "AI didn't return valid proposals. Calculated scores still shown."
                )
    else:
        st.caption("AI unavailable")

with ai_c2:
    if ai_proposals:
        st.success(
            f"✨ AI proposed adjustments for {len(ai_proposals)} initiatives. "
            "Reasoning is shown per initiative in the ranked list below. "
            "You can override any score with the sliders."
        )

# -----------------------------------------------------------------------------
# Determine displayed scores: user-adjusted > AI-proposed > calculated
# -----------------------------------------------------------------------------
user_overrides_key = f"prioritization_user_overrides_{org_filter}_{','.join(sorted(status_filter))}"
user_overrides = st.session_state.get(user_overrides_key, {})

for row in scored_rows:
    iid = row["id"]
    # Effective impact
    if iid in user_overrides:
        _override = user_overrides[iid]
        row["display_impact"] = _override.get("impact", row["baseline_impact"])
        row["display_effort"] = _override.get("effort", row["baseline_effort"])
        row["score_source"] = "user"
        # Preserve what was there before the override (calculated or AI)
        row["prev_impact"] = _override.get("prev_impact")
        row["prev_effort"] = _override.get("prev_effort")
        row["prev_source"] = _override.get("prev_source", "calculated")
        row["override_reason"] = _override.get("reason", "")
    elif iid in ai_proposals:
        row["display_impact"] = ai_proposals[iid]["impact"]
        row["display_effort"] = ai_proposals[iid]["effort"]
        row["ai_reasoning"] = ai_proposals[iid]["reasoning"]
        row["score_source"] = "ai"
    else:
        row["display_impact"] = row["baseline_impact"]
        row["display_effort"] = row["baseline_effort"]
        row["score_source"] = "calculated"


# -----------------------------------------------------------------------------
# Quadrant assignment (used by summary, matrix, and ranked list)
# -----------------------------------------------------------------------------
def _quadrant_of(row) -> str:
    high_impact = row["display_impact"] >= 3.0
    high_effort = row["display_effort"] >= 3.0
    if high_impact and not high_effort:
        return "quick_wins"
    if high_impact and high_effort:
        return "big_bets"
    if not high_impact and not high_effort:
        return "fill_ins"
    return "reconsider"


for row in scored_rows:
    row["_quadrant"] = _quadrant_of(row)


# -----------------------------------------------------------------------------
# AI page-level summary — chief-of-staff read on the whole portfolio
# -----------------------------------------------------------------------------
def _build_summary_context(rows):
    """Assemble the compact context passed to the AI summary prompt."""
    # Rank all rows by ratio
    ranked = sorted(rows, key=lambda r: -(r["display_impact"] / max(r["display_effort"], 0.5)))

    quadrant_counts = {"quick_wins": 0, "big_bets": 0, "fill_ins": 0, "reconsider": 0}
    for r in rows:
        quadrant_counts[r["_quadrant"]] = quadrant_counts.get(r["_quadrant"], 0) + 1

    def _summarize_row(r):
        return {
            "title": r["title"],
            "owning_team": r["owning_team"],
            "impact": r["display_impact"],
            "effort": r["display_effort"],
            "revenue": r["impact_decomp"].get("revenue_impact_usd_annual") or 0,
            "horizon": r["impact_decomp"].get("time_horizon_years") or 1,
            "category": r["impact_decomp"].get("revenue_impact_category") or "unspecified",
        }

    top_ranked = [_summarize_row(r) for r in ranked[:3]]
    bottom_ranked = [_summarize_row(r) for r in ranked[-3:]] if len(ranked) > 3 else []

    # Data quality gaps
    data_quality = {
        "no_kr_link": [r["title"] for r in rows if r["impact_decomp"].get("linked_krs", 0) == 0],
        "no_business_case": [
            r["title"] for r in rows
            if not r["impact_decomp"].get("quantified") and
               r["impact_decomp"].get("linked_krs", 0) > 0
        ],
        "unquantified_impact": [
            r["title"] for r in rows if not r["impact_decomp"].get("quantified")
        ],
        "no_effort_size": [
            r["title"] for r in rows
            if r["effort_decomp"].get("t_shirt_size") in ("unspecified", "", None)
        ],
    }
    # Deduplicate: no_business_case is a subset of unquantified_impact
    _bc_set = set(data_quality["no_business_case"])
    data_quality["unquantified_impact"] = [
        t for t in data_quality["unquantified_impact"] if t not in _bc_set
    ]

    # Suspicious signals — initiative-level flags worth naming
    suspicious = []
    for r in rows:
        # Quick Win with troubling ambient signals
        if r["_quadrant"] == "quick_wins":
            signal_load = r["effort_decomp"].get("signal_load", 0)
            if signal_load >= 3:
                suspicious.append(
                    f"{r['title']} is rated Quick Win but has {signal_load} concerning ambient signals"
                )
        # Big Bet with blocked or at-risk milestone
        if r["_quadrant"] == "big_bets":
            ms = r["effort_decomp"].get("milestone_status")
            if ms in ("blocked", "at_risk"):
                suspicious.append(
                    f"{r['title']} is a Big Bet with milestone status '{ms}'"
                )
        # Cross-functional initiative at risk (touches another team's KR)
        if r["impact_decomp"].get("cross_functional") and r["effort_decomp"].get("milestone_status") in ("blocked", "at_risk"):
            suspicious.append(
                f"{r['title']} moves another team's KR and its own milestone is at risk"
            )

    # Human override patterns
    overrides = []
    for r in rows:
        if r["score_source"] == "user":
            _prev_i = r.get("prev_impact")
            _prev_e = r.get("prev_effort")
            _delta_i = r["display_impact"] - _prev_i if _prev_i is not None else 0
            _delta_e = r["display_effort"] - _prev_e if _prev_e is not None else 0
            _reason = r.get("override_reason") or "no reason given"
            if abs(_delta_i) >= 1.0 or abs(_delta_e) >= 1.0:
                overrides.append(
                    f"{r['title']}: manually adjusted "
                    f"(impact {_delta_i:+.1f}, effort {_delta_e:+.1f}) — {_reason}"
                )

    return {
        "total": len(rows),
        "quadrant_counts": quadrant_counts,
        "top_ranked": top_ranked,
        "bottom_ranked": bottom_ranked,
        "data_quality": data_quality,
        "suspicious": suspicious,
        "overrides": overrides,
    }


# Render the summary panel
with st.container(border=True):
    _summary_col, _btn_col = st.columns([6, 1])
    with _summary_col:
        st.markdown(
            "<div style='font-weight:600;font-size:1em;color:#374151'>"
            "✨ AI-generated summary</div>",
            unsafe_allow_html=True,
        )
    with _btn_col:
        _refresh_summary = st.button(
            "🔄 Refresh",
            key="refresh_prio_summary",
            use_container_width=True,
            help="Regenerate the summary against the current state of the page.",
        )

    _summary_key = f"prio_summary_{org_filter}_{','.join(sorted(status_filter))}"
    # Include a signature of what's user-overridden so refreshing after an
    # override picks up the change
    _override_sig = str(sorted(user_overrides.keys()))
    _sig_key = f"{_summary_key}__sig"

    if _refresh_summary or _summary_key not in st.session_state or st.session_state.get(_sig_key) != _override_sig:
        if is_ai_enabled():
            with st.spinner("Summarizing portfolio..."):
                _context = _build_summary_context(scored_rows)
                _summary = ai_summarize_prioritization(_context)
            if _summary:
                st.session_state[_summary_key] = _summary
                st.session_state[_sig_key] = _override_sig
            else:
                st.session_state[_summary_key] = (
                    "_Summary generation unavailable._"
                )
        else:
            st.session_state[_summary_key] = (
                "_AI is not enabled in this environment._"
            )

    st.markdown(st.session_state.get(_summary_key, ""))
    st.caption(
        "_Generated by Claude Sonnet from the same data shown below. "
        "Interpretation, not restatement._"
    )


# -----------------------------------------------------------------------------
# Matrix visualization — 2x2 quadrant chart
# -----------------------------------------------------------------------------
st.subheader(f"Impact × Effort matrix — {len(scored_rows)} initiatives")

# Pre-compute the rank so bubble numbers match the ranked list below
_pre_ranked = sorted(
    scored_rows,
    key=lambda r: -(r["display_impact"] / max(r["display_effort"], 0.5)),
)
rank_by_id = {r["id"]: idx for idx, r in enumerate(_pre_ranked, start=1)}

# Apply small deterministic jitter so overlapping bubbles don't stack.
# Deterministic (hash-based) means bubbles don't shuffle on every rerender.
import hashlib as _hashlib
def _jitter(iid: str, axis: str) -> float:
    """Return a small offset in [-0.15, +0.15] deterministic per (id, axis)."""
    _h = int(_hashlib.md5(f"{iid}_{axis}".encode()).hexdigest()[:8], 16)
    return ((_h % 1000) / 1000.0 - 0.5) * 0.30

# Build the plotly figure
fig = go.Figure()

# Quadrant background shading — subtle
fig.add_shape(
    type="rect", x0=1, y0=3, x1=3, y1=5,
    fillcolor="rgba(16,185,129,0.08)", line=dict(width=0), layer="below",
)  # Quick wins (low effort, high impact)
fig.add_shape(
    type="rect", x0=3, y0=3, x1=5, y1=5,
    fillcolor="rgba(59,130,246,0.06)", line=dict(width=0), layer="below",
)  # Big bets
fig.add_shape(
    type="rect", x0=1, y0=1, x1=3, y1=3,
    fillcolor="rgba(156,163,175,0.06)", line=dict(width=0), layer="below",
)  # Fill-ins
fig.add_shape(
    type="rect", x0=3, y0=1, x1=5, y1=3,
    fillcolor="rgba(239,68,68,0.08)", line=dict(width=0), layer="below",
)  # Reconsider (high effort, low impact)

# Quadrant labels — moved to the corners so they don't fight for space
fig.add_annotation(x=1.1, y=4.9, text="<b>Quick wins</b>", showarrow=False,
                   xanchor="left", font=dict(size=11, color="#059669"))
fig.add_annotation(x=4.9, y=4.9, text="<b>Big bets</b>", showarrow=False,
                   xanchor="right", font=dict(size=11, color="#2563EB"))
fig.add_annotation(x=1.1, y=1.1, text="<b>Fill-ins</b>", showarrow=False,
                   xanchor="left", font=dict(size=11, color="#6B7280"))
fig.add_annotation(x=4.9, y=1.1, text="<b>Reconsider</b>", showarrow=False,
                   xanchor="right", font=dict(size=11, color="#DC2626"))

# Color initiatives by owning team
team_names = sorted(set(r["owning_team"] for r in scored_rows))
palette = ["#3B82F6", "#10B981", "#F59E0B", "#8B5CF6", "#EC4899",
           "#14B8A6", "#F97316", "#6366F1"]
color_by_team = {name: palette[i % len(palette)] for i, name in enumerate(team_names)}

for team in team_names:
    team_rows = [r for r in scored_rows if r["owning_team"] == team]
    fig.add_trace(go.Scatter(
        x=[r["display_effort"] + _jitter(r["id"], "x") for r in team_rows],
        y=[r["display_impact"] + _jitter(r["id"], "y") for r in team_rows],
        mode="markers+text",
        name=team,
        marker=dict(
            size=[22 + (r["progress_pct"] / 100 * 10) for r in team_rows],
            color=color_by_team[team],
            opacity=0.80,
            line=dict(width=1.5, color="white"),
        ),
        # Show rank number on the bubble — matches the ranked list numbering
        text=[str(rank_by_id[r["id"]]) for r in team_rows],
        textposition="middle center",
        textfont=dict(size=11, color="white", family="Arial Black"),
        hovertemplate=(
            "<b>#%{text}: " +
            "%{customdata[0]}</b><br>" +
            "Impact: %{customdata[1]:.1f}<br>" +
            "Effort: %{customdata[2]:.1f}<br>" +
            "Team: %{customdata[3]}<br>" +
            "Delivery: %{customdata[4]}%" +
            "<extra></extra>"
        ),
        customdata=[
            [r["title"], r["display_impact"], r["display_effort"],
             r["owning_team"], r["progress_pct"]]
            for r in team_rows
        ],
    ))

fig.update_layout(
    xaxis=dict(
        title="Effort →", range=[0.7, 5.3],
        tickvals=[1, 2, 3, 4, 5],
        showgrid=True, gridcolor="rgba(0,0,0,0.05)",
    ),
    yaxis=dict(
        title="Impact ↑", range=[0.7, 5.3],
        tickvals=[1, 2, 3, 4, 5],
        showgrid=True, gridcolor="rgba(0,0,0,0.05)",
    ),
    height=640,
    plot_bgcolor="white",
    margin=dict(l=60, r=20, t=20, b=60),
    legend=dict(
        orientation="h", yanchor="bottom", y=-0.16, xanchor="center", x=0.5,
    ),
)
# Divider lines through middle
fig.add_hline(y=3, line=dict(color="#D1D5DB", width=1, dash="dot"))
fig.add_vline(x=3, line=dict(color="#D1D5DB", width=1, dash="dot"))

st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Bubbles are numbered to match the ranked list below. Bubble size represents "
    "delivery %. Bubble color represents owning team. Hover for full details. "
    "Small jitter is applied to prevent overlap; quadrants are guides, not rules."
)

# -----------------------------------------------------------------------------
# Ranked list — grouped by quadrant, sorted by ratio within each quadrant
# -----------------------------------------------------------------------------
st.subheader("Ranked list")
st.caption(
    "Grouped by quadrant, then sorted by Impact ÷ Effort ratio within each "
    "group. Quadrants are guides — a Reconsider initiative may be strategically "
    "necessary; a Quick win may be lower priority than a committed roadmap item. "
    "Numbers match the bubbles on the matrix above."
)


# Assign each row to a quadrant based on 3.0 midpoint split
# (Already computed above in the summary-context section.)

# Quadrant display order and metadata
QUADRANT_ORDER = [
    ("quick_wins", "🟢 Quick wins", "#059669",
     "High impact, low effort — these should happen."),
    ("big_bets", "🔵 Big bets", "#2563EB",
     "High impact, high effort — the strategic conversation."),
    ("fill_ins", "⚪ Fill-ins", "#6B7280",
     "Low impact, low effort — cheap to knock out but don't move the needle."),
    ("reconsider", "🔴 Reconsider", "#DC2626",
     "Low impact, high effort — worth questioning whether these belong on the roadmap."),
]

# Also pre-rank the whole list globally so numbers match the bubbles on the matrix
_global_ranked = sorted(
    scored_rows,
    key=lambda r: -(r["display_impact"] / max(r["display_effort"], 0.5)),
)
global_rank_by_id = {r["id"]: idx for idx, r in enumerate(_global_ranked, start=1)}

for quad_key, quad_label, quad_color, quad_desc in QUADRANT_ORDER:
    quad_rows = [r for r in scored_rows if r["_quadrant"] == quad_key]
    if not quad_rows:
        continue

    # Sort within quadrant by ratio (best first)
    quad_rows_sorted = sorted(
        quad_rows,
        key=lambda r: -(r["display_impact"] / max(r["display_effort"], 0.5)),
    )

    # Quadrant header
    st.markdown(
        f"<div style='margin:24px 0 8px;padding:6px 12px;"
        f"border-left:4px solid {quad_color};background:#F9FAFB;"
        f"font-size:1.05em;font-weight:600;color:{quad_color}'>"
        f"{quad_label} <span style='color:#6B7280;font-weight:400;font-size:0.9em'>"
        f"· {len(quad_rows_sorted)} initiative"
        f"{'s' if len(quad_rows_sorted) != 1 else ''} · {quad_desc}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    for row in quad_rows_sorted:
        # Source badge
        if row["score_source"] == "ai":
            source_badge = "✨ AI-adjusted"
        elif row["score_source"] == "user":
            source_badge = "👤 You adjusted"
        else:
            source_badge = "📊 Calculated"

        ratio = row["display_impact"] / max(row["display_effort"], 0.5)
        global_rank = global_rank_by_id[row["id"]]

        # Build the score display — annotate with "was X" when user overrode
        if row["score_source"] == "user" and row.get("prev_impact") is not None:
            impact_display = f"Impact {row['display_impact']:.1f} (was {row['prev_impact']:.1f})"
            effort_display = f"Effort {row['display_effort']:.1f} (was {row['prev_effort']:.1f})"
        else:
            impact_display = f"Impact {row['display_impact']:.1f}"
            effort_display = f"Effort {row['display_effort']:.1f}"

        header = (
            f"**#{global_rank}. {row['title']}**"
            f"  ·  {impact_display} / {effort_display}"
            f"  ·  Ratio {ratio:.2f}"
            f"  ·  {source_badge}"
        )

        with st.expander(header, expanded=False):
            _meta_col, _link_col = st.columns([4, 1])
            with _meta_col:
                st.markdown(
                    f"**Team:** {row['owning_team']}  ·  "
                    f"**Status:** {row['status']}  ·  "
                    f"**Milestone:** {row['milestone_status']}  ·  "
                    f"**Delivery:** {row['progress_pct']}%  ·  "
                    f"**T-shirt:** {row['effort_estimate']}"
                )
            with _link_col:
                # Link out to the initiative admin surface so a user can edit
                # description, KR links, business case, etc. Streamlit's
                # page_link jumps to the page but not to a specific initiative;
                # the user selects it there. Small friction, low risk.
                try:
                    st.page_link(
                        "views/create_initiative.py",
                        label="✏️ Edit",
                        icon=None,
                        help="Open Create Initiative page to edit this initiative's details.",
                    )
                except Exception:
                    # If create_initiative.py isn't in that path, degrade
                    # gracefully — link is a nice-to-have, not core to the page.
                    pass

            # Override history callout — visible when user has overridden
            if row["score_source"] == "user" and row.get("prev_impact") is not None:
                _prev_source_label = {
                    "calculated": "the calculated score",
                    "ai": "the AI-adjusted score",
                }.get(row.get("prev_source", "calculated"), "the prior score")
                _override_msg = (
                    f"**👤 Manually overridden.** Adjusted from "
                    f"Impact {row['prev_impact']:.1f} / Effort {row['prev_effort']:.1f} "
                    f"({_prev_source_label})."
                )
                if row.get("override_reason"):
                    _override_msg += f"  \n**Reason:** _{row['override_reason']}_"
                st.warning(_override_msg)

            # AI reasoning (if present and not overridden)
            if row.get("ai_reasoning") and row["score_source"] == "ai":
                st.info(f"**✨ AI reasoning:** {row['ai_reasoning']}")

            # Score decomposition
            dc1, dc2 = st.columns(2)
            with dc1:
                st.markdown("**Impact signals**")
                impact_signals = row["impact_decomp"].get("signals", [])
                if impact_signals:
                    for s in impact_signals:
                        st.markdown(f"- {s}")
                else:
                    st.caption("No impact signals detected.")
                if row["impact_decomp"].get("note"):
                    st.caption(f"_{row['impact_decomp']['note']}_")

            with dc2:
                st.markdown("**Effort signals**")
                effort_signals = row["effort_decomp"].get("signals", [])
                if effort_signals:
                    for s in effort_signals:
                        st.markdown(f"- {s}")
                else:
                    st.caption("No effort signals detected.")

            st.markdown("---")

            # -----------------------------------------------------------------
            # Manual override section
            # -----------------------------------------------------------------
            st.markdown("**Adjust scores manually**")
            st.caption(
                "Move the sliders and add a short reason so someone reading "
                "the update knows what context you had that the app didn't."
            )

            sc1, sc2 = st.columns(2)
            with sc1:
                new_impact = st.slider(
                    "Impact",
                    min_value=1.0, max_value=5.0,
                    value=float(row["display_impact"]),
                    step=0.5,
                    key=f"impact_slider_{row['id']}",
                )
            with sc2:
                new_effort = st.slider(
                    "Effort",
                    min_value=1.0, max_value=5.0,
                    value=float(row["display_effort"]),
                    step=0.5,
                    key=f"effort_slider_{row['id']}",
                )

            new_reason = st.text_input(
                "Reason for the override",
                value=row.get("override_reason", ""),
                placeholder=(
                    "e.g., \"revenue impact is soft on paper but this KR is "
                    "strategic to the exec team\" or \"team just picked up "
                    "additional dependency work\""
                ),
                key=f"reason_input_{row['id']}",
            )

            btn1, btn2, btn3 = st.columns(3)
            with btn1:
                if st.button(
                    "💾 Save override",
                    key=f"save_{row['id']}",
                    use_container_width=True,
                    type="primary",
                    disabled=(new_impact == row["display_impact"]
                              and new_effort == row["display_effort"]
                              and new_reason == row.get("override_reason", "")),
                ):
                    if user_overrides_key not in st.session_state:
                        st.session_state[user_overrides_key] = {}
                    # Capture what we're overriding *from* — either the
                    # calculated score or the AI-adjusted one, whichever
                    # was showing before this override.
                    if row["score_source"] == "user":
                        # Already overridden — keep the prior prev_* values
                        _prev_impact = row.get("prev_impact")
                        _prev_effort = row.get("prev_effort")
                        _prev_source = row.get("prev_source", "calculated")
                    elif row["score_source"] == "ai":
                        _prev_impact = row["display_impact"]
                        _prev_effort = row["display_effort"]
                        _prev_source = "ai"
                    else:
                        _prev_impact = row["baseline_impact"]
                        _prev_effort = row["baseline_effort"]
                        _prev_source = "calculated"
                    st.session_state[user_overrides_key][row["id"]] = {
                        "impact": new_impact,
                        "effort": new_effort,
                        "prev_impact": _prev_impact,
                        "prev_effort": _prev_effort,
                        "prev_source": _prev_source,
                        "reason": new_reason.strip(),
                    }
                    st.rerun()

            with btn2:
                # Rescore button — clears the user override and any cached AI
                # proposal for this specific initiative, forcing a fresh
                # calculation and (if the user chooses) fresh AI review.
                if st.button(
                    "🔄 Rescore from current data",
                    key=f"rescore_{row['id']}",
                    use_container_width=True,
                    help=(
                        "Discard any manual override and use the freshly "
                        "calculated score. Use this after you've updated the "
                        "initiative's business case, KR links, or effort estimate."
                    ),
                ):
                    # Clear user override for this initiative
                    overrides = st.session_state.get(user_overrides_key, {})
                    if row["id"] in overrides:
                        del overrides[row["id"]]
                        st.session_state[user_overrides_key] = overrides
                    # Clear AI proposal for this initiative so it's not
                    # reapplied on rerun
                    _ai_props = st.session_state.get(_ai_key, {})
                    if row["id"] in _ai_props:
                        del _ai_props[row["id"]]
                        st.session_state[_ai_key] = _ai_props
                    # Bust the load_all cache too so any DB-side changes
                    # to the initiative flow through
                    st.cache_data.clear()
                    st.rerun()

            with btn3:
                st.markdown("&nbsp;")  # spacer


# -----------------------------------------------------------------------------
# Footer note
# -----------------------------------------------------------------------------
st.divider()
st.caption(
    "**Note on the framework choice:** Impact anchors on annualized revenue "
    "impact × time horizon — the only apples-to-apples signal across "
    "initiatives with different underlying units. The four categories "
    "(new revenue / retention / cost savings / risk mitigation) all "
    "normalize into that single dollar figure. Structural adjustments "
    "(KR gap severity, cross-functional reach) shift the anchor by ±0.5 "
    "total. Initiatives without a quantified revenue impact score from "
    "structural signals only and are labeled honestly."
)

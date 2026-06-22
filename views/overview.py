"""
OKR Planning App — Overview page.

Read-only landing page. Pulls the joined Objective -> KR -> Initiative ->
Business Case view, with two honest status indicators per row:

  * KR Status (computed) — colored dot from the grade math
    (current - start) / (target - start), clamped 0-1. Answers:
    "is the outcome moving?"

  * Initiative Milestone Status (entered) — colored dot from the manually-set
    `milestone_status` field on the initiative. Answers:
    "is the work shipping?"

These two questions are different. Conflating them is the failure mode this
view deliberately avoids by displaying both.
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client


# -----------------------------------------------------------------------------
# Supabase
# -----------------------------------------------------------------------------
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


sb = get_supabase()


# -----------------------------------------------------------------------------
# Status helpers
# -----------------------------------------------------------------------------
def kr_grade_dot(start, current, target) -> str:
    """🟢/🟡/🔴 from KR progress math. Empty string when values are missing."""
    if start is None or current is None or target is None:
        return ""
    try:
        if target == start:
            return ""
        g = max(0.0, min(1.0, (current - start) / (target - start)))
    except (TypeError, ZeroDivisionError):
        return ""
    if g >= 0.7:
        return "🟢"
    if g >= 0.4:
        return "🟡"
    return "🔴"


def milestone_dot(status) -> str:
    """🟢/🟡/🔴 from the entered milestone_status. Em dash when unset."""
    if not status or (isinstance(status, float) and pd.isna(status)):
        return "—"
    return {
        "on_track": "🟢",
        "at_risk":  "🟡",
        "blocked":  "🔴",
    }.get(status, "—")


# -----------------------------------------------------------------------------
# Data loaders
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_overview() -> pd.DataFrame:
    """
    Pull every objective with its KRs, linked initiatives, and business cases.

    Join in pandas rather than a single Postgres view, so the read layer stays
    flexible while the schema is young. Once the shape is stable we can replace
    this with a SQL view.
    """
    objectives = pd.DataFrame(sb.table("objective").select("*").execute().data)
    key_results = pd.DataFrame(sb.table("key_result").select("*").execute().data)
    initiatives = pd.DataFrame(sb.table("initiative").select("*").execute().data)
    links = pd.DataFrame(sb.table("initiative_key_result").select("*").execute().data)
    business_cases = pd.DataFrame(sb.table("business_case").select("*").execute().data)
    org_units = pd.DataFrame(sb.table("org_unit").select("*").execute().data)

    if objectives.empty or key_results.empty:
        return pd.DataFrame()

    # objective + org unit
    df = objectives.merge(
        org_units[["id", "name", "level"]].rename(
            columns={"id": "org_unit_id", "name": "org_unit", "level": "org_level"}
        ),
        on="org_unit_id",
        how="left",
    )

    # + key result
    df = df.merge(
        key_results.rename(columns={"id": "key_result_id", "title": "key_result"}),
        left_on="id",
        right_on="objective_id",
        how="left",
        suffixes=("_obj", "_kr"),
    )

    # + initiative link (left join keeps KRs that have no initiative yet)
    if not links.empty:
        df = df.merge(links, on="key_result_id", how="left")
    else:
        df["initiative_id"] = None
        df["predicted_kr_impact"] = None

    # + initiative details — now including milestone_status so we can render the
    #   delivery-side status dot.
    if not initiatives.empty:
        df = df.merge(
            initiatives[["id", "title", "status", "milestone_status", "progress_pct"]].rename(
                columns={
                    "id": "initiative_id",
                    "title": "initiative",
                    "status": "initiative_status",
                }
            ),
            on="initiative_id",
            how="left",
        )

    # + business case (one per initiative)
    if not business_cases.empty:
        df = df.merge(
            business_cases[
                ["initiative_id", "predicted_value", "predicted_cost", "decision"]
            ],
            on="initiative_id",
            how="left",
        )

    return df


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("🎯 OKR Planning")
st.caption(
    "Strategy → Objectives → Key Results → Initiatives → Business Cases. "
    "Outcomes and output kept separate by design."
)

try:
    df = load_overview()
except Exception as e:
    st.error(f"Couldn't reach Supabase: {e}")
    st.info(
        "Check that `SUPABASE_URL` and `SUPABASE_KEY` are set in "
        "`.streamlit/secrets.toml`, and that RLS is off on all tables."
    )
    st.stop()

if df.empty:
    st.warning("No data yet. Run the seed block from `okr_schema.sql` to populate.")
    st.stop()


# -----------------------------------------------------------------------------
# Org-unit filter
# -----------------------------------------------------------------------------
# Pull org unit list directly from the table (not the join) so units in the
# middle of the cascade with no objectives still appear in the dropdown.
#
# Note: the filter lives inline (not in st.sidebar) on purpose — putting it
# in the sidebar interferes with st.navigation's rendering in some Streamlit
# versions, and putting it next to the data it controls is arguably better UX
# anyway.
@st.cache_data(ttl=60)
def list_org_units() -> list[str]:
    rows = sb.table("org_unit").select("name, level").execute().data
    # Sort company → segment → team, then by name
    level_order = {"company": 0, "segment": 1, "team": 2}
    rows.sort(key=lambda r: (level_order.get(r.get("level"), 99), r["name"]))
    return [r["name"] for r in rows]


# Inline filter — narrow column on the left so it doesn't dominate the layout
fc1, fc2 = st.columns([1, 3])
with fc1:
    org_unit_options = ["All org units"] + list_org_units()
    selected_ou = st.selectbox("Filter by org unit", options=org_unit_options, index=0)

# Apply filter
if selected_ou != "All org units":
    df = df[df["org_unit"] == selected_ou]

if df.empty:
    st.info(f"No data for **{selected_ou}** yet.")
    st.stop()


# -----------------------------------------------------------------------------
# Top-line counts
# -----------------------------------------------------------------------------
# Org units come from the table directly, not the join — an org unit in the
# middle of the cascade (a segment with no objectives of its own) would
# otherwise be invisible to a join-derived count.
@st.cache_data(ttl=60)
def count_org_units() -> int:
    return len(sb.table("org_unit").select("id").execute().data)


c1, c2, c3, c4 = st.columns(4)
# When filtered to one org unit, the org-units metric shows "1 of N"; otherwise
# the global count. Keeps the metric honest under filter.
total_ous = count_org_units()
c1.metric(
    "Org units",
    "1" if selected_ou != "All org units" else total_ous,
    delta=(f"of {total_ous}" if selected_ou != "All org units" else None),
    delta_color="off",
)
c2.metric("Objectives", df["objective_id"].nunique())
c3.metric("Key Results", df["key_result_id"].nunique())
c4.metric(
    "Initiatives",
    int(df["initiative_id"].dropna().nunique()) if "initiative_id" in df else 0,
)

st.divider()


# -----------------------------------------------------------------------------
# Compute status indicators
# -----------------------------------------------------------------------------
# Two genuinely different questions, two columns:
#   * Outcome:  is the KR moving toward its target?       (computed)
#   * Delivery: is the initiative shipping on track?      (entered)
df = df.copy()
df["kr_status"] = df.apply(
    lambda r: kr_grade_dot(
        r.get("start_value"), r.get("current_value"), r.get("target_value")
    ),
    axis=1,
)
df["delivery_status"] = df["milestone_status"].apply(milestone_dot) if "milestone_status" in df.columns else "—"


# -----------------------------------------------------------------------------
# Joined view
# -----------------------------------------------------------------------------
st.subheader("Joined view")
st.caption(
    "Every KR with its linked initiative(s) and business case. "
    "🟢🟡🔴 — outcome status reflects KR progress math; delivery status reflects "
    "the milestone status set on the initiative."
)

# Column order: status dot sits right next to the thing it's about.
display_cols = [
    "org_unit",
    "title_obj",
    "period",
    "key_result",
    "kr_status",
    "current_value",
    "target_value",
    "metric_unit",
    "initiative",
    "delivery_status",
    "initiative_status",
    "progress_pct",
    "predicted_kr_impact",
    "predicted_value",
    "predicted_cost",
    "decision",
]
display_cols = [c for c in display_cols if c in df.columns]

# Friendlier headers — title case, descriptive, no underscores.
rename_map = {
    "org_unit":            "Org Unit",
    "title_obj":           "Objective",
    "period":              "Period",
    "key_result":          "Key Result",
    "kr_status":           "Outcome",
    "current_value":       "Current",
    "target_value":        "Target",
    "metric_unit":         "Unit",
    "initiative":          "Initiative",
    "delivery_status":     "Delivery",
    "initiative_status":   "Init. State",
    "progress_pct":        "Delivery %",
    "predicted_kr_impact": "Predicted KR Impact",
    "predicted_value":     "Predicted $ Value",
    "predicted_cost":      "Predicted $ Cost",
    "decision":            "Decision",
}

st.dataframe(
    df[display_cols].rename(columns=rename_map),
    use_container_width=True,
    hide_index=True,
)

# Compact legend right under the table — easier than scrolling to find an explainer.
st.caption(
    "**Outcome** 🟢 ≥70% to target · 🟡 ≥40% · 🔴 <40% · blank when start/target unset.  "
    "**Delivery** 🟢 on track · 🟡 at risk · 🔴 blocked · — when not set on the initiative."
)


with st.expander("Raw rows (debug)"):
    st.dataframe(df, use_container_width=True, hide_index=True)

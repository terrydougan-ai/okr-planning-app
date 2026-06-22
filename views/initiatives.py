"""
Initiatives — initiative-centric view.

Flips the lens from the Objectives page. Each initiative shows:
  * delivery health (its own progress / status — output)
  * the KR(s) it claims to move, with predicted vs actual impact per link
  * its business case ROI (predicted value / cost, with planned ROI computed)

Three measurement layers visible side by side, never collapsed into one number:
  delivery (is the work getting done) ≠
  impact   (is the outcome moving)    ≠
  ROI      (was the bet worth it)
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client


# Supabase client
# -----------------------------------------------------------------------------
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


sb = get_supabase()


# -----------------------------------------------------------------------------
# Data
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_all():
    return {
        "initiatives": pd.DataFrame(sb.table("initiative").select("*").execute().data),
        "links": pd.DataFrame(sb.table("initiative_key_result").select("*").execute().data),
        "key_results": pd.DataFrame(sb.table("key_result").select("*").execute().data),
        "objectives": pd.DataFrame(sb.table("objective").select("*").execute().data),
        "org_units": pd.DataFrame(sb.table("org_unit").select("*").execute().data),
        "business_cases": pd.DataFrame(sb.table("business_case").select("*").execute().data),
    }


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def status_badge(status: str) -> str:
    return {
        "proposed": "💭 proposed",
        "active":   "🟢 active",
        "done":     "✅ done",
        "killed":   "🪦 killed",
    }.get(status, status or "—")


def milestone_badge(ms: str) -> str:
    return {
        "on_track": "🟢 on track",
        "at_risk":  "🟡 at risk",
        "blocked":  "🔴 blocked",
    }.get(ms, ms or "—")


def fmt_money(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"${v:,.0f}"


def fmt_ratio(num, denom) -> str:
    """Predicted ROI ratio. Returns '—' if either side is missing or zero."""
    if num is None or denom is None or pd.isna(num) or pd.isna(denom) or denom == 0:
        return "—"
    return f"{num / denom:.1f}x"


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("🚀 Initiatives")
st.caption(
    "Each bet, what it's moving, and what it's worth. "
    "Delivery, impact, and ROI shown as three distinct measurements — never collapsed."
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

if initiatives.empty:
    st.warning("No initiatives yet.")
    st.stop()

# Lookups
kr_by_id = key_results.set_index("id").to_dict("index") if not key_results.empty else {}
obj_by_id = objectives.set_index("id").to_dict("index") if not objectives.empty else {}
ou_by_id = org_units.set_index("id")["name"].to_dict() if not org_units.empty else {}
bc_by_init = (
    business_cases.set_index("initiative_id").to_dict("index")
    if not business_cases.empty
    else {}
)


# --- Sidebar filters ---------------------------------------------------------
with st.sidebar:
    st.header("Filter")
    statuses = ["all"] + sorted(initiatives["status"].dropna().unique().tolist())
    status_filter = st.radio("Status", options=statuses, index=0)

visible = initiatives.copy()
if status_filter != "all":
    visible = visible[visible["status"] == status_filter]

if visible.empty:
    st.info(f"No initiatives with status **{status_filter}**.")
    st.stop()


# --- Summary strip -----------------------------------------------------------
total_predicted_value = 0.0
total_predicted_cost = 0.0
for _, init in visible.iterrows():
    bc = bc_by_init.get(init["id"])
    if bc:
        v = bc.get("predicted_value") or 0
        c = bc.get("predicted_cost") or 0
        total_predicted_value += v
        total_predicted_cost += c

c1, c2, c3, c4 = st.columns(4)
c1.metric("Initiatives shown", len(visible))
c2.metric("Predicted value", fmt_money(total_predicted_value))
c3.metric("Predicted cost", fmt_money(total_predicted_cost))
c4.metric("Portfolio ROI", fmt_ratio(total_predicted_value, total_predicted_cost))

st.caption(
    "_Portfolio ROI is a naive sum across business cases — "
    "see note on attribution at the bottom._"
)

st.divider()


# --- Per-initiative cards ----------------------------------------------------
for _, init in visible.iterrows():
    header = (
        f"{status_badge(init['status'])}  ·  "
        f"{milestone_badge(init.get('milestone_status'))}  —  **{init['title']}**"
    )

    with st.expander(header, expanded=True):
        # Description and ownership
        if init.get("description"):
            st.caption(init["description"])
        st.caption(
            f"Owner: {init.get('owner') or '—'}  ·  "
            f"Effort: {init.get('effort_estimate') or '—'}  ·  "
            f"Delivery: {init.get('progress_pct') or 0}%"
        )
        st.progress((init.get("progress_pct") or 0) / 100)

        # KR links (impact layer)
        st.markdown("**Moves these key results**")
        init_links = links[links["initiative_id"] == init["id"]] if not links.empty else pd.DataFrame()

        if init_links.empty:
            st.info("No KRs linked yet — this initiative isn't aimed at a measurable outcome.")
        else:
            rows = []
            for _, lk in init_links.iterrows():
                kr = kr_by_id.get(lk["key_result_id"], {})
                obj = obj_by_id.get(kr.get("objective_id"), {})
                ou_name = ou_by_id.get(obj.get("org_unit_id"), "—")
                rows.append({
                    "key result": kr.get("title", "?"),
                    "scope": ou_name,
                    "unit": kr.get("metric_unit") or "",
                    "predicted impact": lk.get("predicted_kr_impact"),
                    "actual impact": lk.get("actual_kr_impact"),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # Business case (ROI layer)
        st.markdown("**Business case**")
        bc = bc_by_init.get(init["id"])
        if not bc:
            st.info("No business case attached. This bet isn't justified with predicted value vs cost yet.")
        else:
            roi_predicted = fmt_ratio(bc.get("predicted_value"), bc.get("predicted_cost"))
            roi_actual = fmt_ratio(bc.get("actual_value"), bc.get("actual_cost"))

            bc_cols = st.columns(5)
            bc_cols[0].metric("Predicted value", fmt_money(bc.get("predicted_value")))
            bc_cols[1].metric("Predicted cost", fmt_money(bc.get("predicted_cost")))
            bc_cols[2].metric("Planned ROI", roi_predicted)
            bc_cols[3].metric("Actual value", fmt_money(bc.get("actual_value")))
            bc_cols[4].metric("Realized ROI", roi_actual)

            unit = bc.get("target_metric_unit") or ""
            metric = bc.get("target_metric") or "—"
            decision = bc.get("decision") or "pending"
            st.caption(
                f"Denominated in **{metric}** ({unit})  ·  Decision: **{decision}**"
            )
            if bc.get("summary"):
                st.caption(bc["summary"])


# --- Footnote on attribution -------------------------------------------------
st.divider()
with st.expander("ℹ️ Note on portfolio ROI and attribution"):
    st.markdown(
        """
The **Portfolio ROI** at the top is a naive sum of predicted value over predicted cost
across every visible business case. That's a fine quick scan, but it has two known
limitations worth keeping in mind:

1. **Multi-KR initiatives can imply double-counting** if you ever sum impact across
   the KR links (which we deliberately don't do here — value/ROI lives on the
   business case, not the joins, specifically to avoid this).
2. **Attribution gets philosophical** when multiple initiatives feed one KR.
   Who gets credit for the realized value? This app records each bet's *claimed*
   contribution but doesn't try to resolve the overlap automatically. That's a
   modeling decision rather than something the data can answer.

Both are flagged-but-deferred design points in the schema, the same way KR
roll-up is wired but dormant.
        """
    )

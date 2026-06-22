"""
Objectives & Key Results — hierarchical view.

Pick an org unit (or 'All') from the sidebar. For the selection, render every
objective as an expandable section showing its KRs with progress bars, the
ladder-up link to a parent KR if one exists, and the initiatives moving each KR.

Pure read for now — CRUD lands in a later page.
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client


# Supabase client (cached)
# -----------------------------------------------------------------------------
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


sb = get_supabase()


# -----------------------------------------------------------------------------
# Data loaders
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_all():
    """Load every table once; we'll filter/join in Python."""
    return {
        "org_units": pd.DataFrame(sb.table("org_unit").select("*").execute().data),
        "objectives": pd.DataFrame(sb.table("objective").select("*").execute().data),
        "key_results": pd.DataFrame(sb.table("key_result").select("*").execute().data),
        "initiatives": pd.DataFrame(sb.table("initiative").select("*").execute().data),
        "links": pd.DataFrame(
            sb.table("initiative_key_result").select("*").execute().data
        ),
        "business_cases": pd.DataFrame(
            sb.table("business_case").select("*").execute().data
        ),
    }


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def build_org_tree(org_units: pd.DataFrame) -> list[tuple[str, str, int]]:
    """
    Walk org_unit by parent_unit_id and return [(id, indented_label, depth), ...]
    in display order. Recursive so it handles arbitrary depth, not just 3 levels.
    """
    if org_units.empty:
        return []

    by_parent: dict = {}
    for _, row in org_units.iterrows():
        by_parent.setdefault(row["parent_unit_id"], []).append(row)

    out: list[tuple[str, str, int]] = []

    def walk(parent_id, depth: int):
        children = by_parent.get(parent_id, [])
        # Stable ordering: company > segment > team, then by name
        level_order = {"company": 0, "segment": 1, "team": 2}
        children.sort(key=lambda r: (level_order.get(r["level"], 99), r["name"]))
        for row in children:
            prefix = "↳ " * depth
            out.append((row["id"], f"{prefix}{row['name']}", depth))
            walk(row["id"], depth + 1)

    walk(None, 0)  # roots have parent_unit_id = None
    return out


def kr_progress(start, target, current) -> float:
    """Google-style 0.0-1.0 grade: clamped linear progress start -> target."""
    if start is None or target is None or current is None:
        return 0.0
    try:
        if target == start:
            return 0.0
        return max(0.0, min(1.0, (current - start) / (target - start)))
    except (TypeError, ZeroDivisionError):
        return 0.0


def grade_color(g: float) -> str:
    """Google's sweet spot is 0.6-0.7. Below 0.4 = at risk; above 0.7 = strong."""
    if g >= 0.7:
        return "🟢"
    if g >= 0.4:
        return "🟡"
    return "🔴"


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("🎯 Objectives & Key Results")
st.caption("The cascade made visible: org unit → objectives → KRs → initiatives.")

try:
    data = load_all()
except Exception as e:
    st.error(f"Couldn't reach Supabase: {e}")
    st.stop()

org_units = data["org_units"]
objectives = data["objectives"]
key_results = data["key_results"]
initiatives = data["initiatives"]
links = data["links"]

if org_units.empty:
    st.warning("No org units yet — run the seed SQL first.")
    st.stop()

# --- Sidebar: org unit picker ------------------------------------------------
tree = build_org_tree(org_units)
options = [("__ALL__", "All org units", -1)] + tree
label_to_id = {label: uid for uid, label, _ in options}

with st.sidebar:
    st.header("Filter")
    selected_label = st.radio(
        "Org unit",
        options=[label for _, label, _ in options],
        index=0,
    )
selected_id = label_to_id[selected_label]

# --- Filter objectives by org unit selection ---------------------------------
if selected_id == "__ALL__":
    visible_objectives = objectives.copy()
else:
    visible_objectives = objectives[objectives["org_unit_id"] == selected_id].copy()

if visible_objectives.empty:
    st.info(
        f"**{selected_label}** has no objectives of its own. "
        "Org units in the middle of the cascade (like a segment) often act as "
        "structural parents without owning objectives directly."
    )
    st.stop()

# Lookup tables for fast joins
ou_by_id = org_units.set_index("id")["name"].to_dict()
kr_by_id = key_results.set_index("id").to_dict("index") if not key_results.empty else {}
obj_by_id = objectives.set_index("id").to_dict("index")
init_by_id = (
    initiatives.set_index("id").to_dict("index") if not initiatives.empty else {}
)

# --- Render objectives -------------------------------------------------------
for _, obj in visible_objectives.iterrows():
    org_name = ou_by_id.get(obj["org_unit_id"], "?")
    parent_obj = obj_by_id.get(obj.get("parent_objective_id"))
    parent_note = (
        f" — ↑ aligns to: *{parent_obj['title']}*" if parent_obj else ""
    )

    header = (
        f"**{org_name} · {obj['period']}** — {obj['title']}{parent_note}"
    )

    with st.expander(header, expanded=True):
        if obj.get("description"):
            st.caption(obj["description"])
        st.caption(
            f"Owner: {obj.get('owner') or '—'}  ·  Status: {obj.get('status') or '—'}"
        )

        # KRs for this objective
        obj_krs = (
            key_results[key_results["objective_id"] == obj["id"]]
            if not key_results.empty
            else pd.DataFrame()
        )

        if obj_krs.empty:
            st.info("No KRs defined for this objective yet.")
            continue

        for _, kr in obj_krs.iterrows():
            grade = kr_progress(
                kr.get("start_value"), kr.get("target_value"), kr.get("current_value")
            )
            unit = kr.get("metric_unit") or ""
            parent_kr = kr_by_id.get(kr.get("parent_key_result_id"))

            # KR header row
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.markdown(f"{grade_color(grade)} **{kr['title']}**")
                if parent_kr:
                    parent_obj_name = obj_by_id.get(parent_kr["objective_id"], {}).get(
                        "title", ""
                    )
                    weight = kr.get("contribution_weight")
                    weight_str = (
                        f" (weight {weight:.2f})" if weight is not None else ""
                    )
                    st.caption(
                        f"↑ rolls up to: *{parent_kr['title']}*{weight_str} "
                        f"  ·  under *{parent_obj_name}*"
                    )
            with col_b:
                st.metric(
                    label="Progress",
                    value=f"{grade:.0%}",
                    label_visibility="collapsed",
                )

            # Numeric line
            st.caption(
                f"Start {kr.get('start_value')} → Current "
                f"**{kr.get('current_value')}** → Target {kr.get('target_value')} "
                f"{unit}"
            )
            st.progress(grade)

            # Initiatives moving this KR
            if not links.empty:
                kr_links = links[links["key_result_id"] == kr["id"]]
                if not kr_links.empty:
                    rows = []
                    for _, lk in kr_links.iterrows():
                        init = init_by_id.get(lk["initiative_id"], {})
                        rows.append(
                            {
                                "initiative": init.get("title", "?"),
                                "status": init.get("status", ""),
                                "delivery %": init.get("progress_pct", 0),
                                "predicted impact": lk.get("predicted_kr_impact"),
                                "actual impact": lk.get("actual_kr_impact"),
                            }
                        )
                    st.dataframe(
                        pd.DataFrame(rows),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.caption("_No initiatives attached to this KR yet._")

            st.write("")  # small spacer between KRs

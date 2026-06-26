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
        # Coerce pandas NaN to Python None so root rows (null parent) group under
        # the same key the walk() call uses.
        pid = row["parent_unit_id"]
        if pid != pid:  # NaN check (NaN != NaN is the only value true here)
            pid = None
        by_parent.setdefault(pid, []).append(row)

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

# --- In-page filter: org unit (tree-indented), with sticky-scope integration ---
ou_by_id = org_units.set_index("id")["name"].to_dict()

level_order = {"company": 0, "segment": 1, "team": 2}
children_by_parent: dict = {}
for _, row in org_units.iterrows():
    pid = row["parent_unit_id"]
    if pid != pid:  # NaN
        pid = None
    children_by_parent.setdefault(pid, []).append(row)

tree_labels: list[str] = []
tree_label_to_id: dict = {}


def _walk_org_tree(parent_id, depth: int):
    siblings = sorted(
        children_by_parent.get(parent_id, []),
        key=lambda r: (level_order.get(r.get("level"), 99), r["name"]),
    )
    for r in siblings:
        prefix = "↳ " * depth
        label = f"{prefix}{r['name']}"
        tree_labels.append(label)
        tree_label_to_id[label] = r["id"]
        _walk_org_tree(r["id"], depth + 1)


_walk_org_tree(None, 0)

ALL_ORGS_LABEL = "All org units"
org_dropdown_options = [ALL_ORGS_LABEL] + tree_labels

# Sticky-scope default
_saved_org_id = st.session_state.get("scope_org_id")
_default_org_idx = 0
if _saved_org_id:
    for _i, _lbl in enumerate(org_dropdown_options):
        if tree_label_to_id.get(_lbl) == _saved_org_id:
            _default_org_idx = _i
            break

selected_org_label = st.selectbox(
    "**Working on**",
    options=org_dropdown_options,
    index=_default_org_idx,
    help=(
        "Pick an org unit to see its objectives. Indented entries (↳) sit "
        "under the unit above them. 'All org units' shows everything. "
        "Persists across pages."
    ),
)

# Persist scope (specific org only — "All" stays local)
if selected_org_label != ALL_ORGS_LABEL:
    _scope_id = tree_label_to_id.get(selected_org_label)
    if _scope_id:
        st.session_state["scope_org_id"] = _scope_id
        st.session_state["scope_org_name"] = ou_by_id.get(_scope_id, selected_org_label)

# --- Filter objectives by org unit selection ---------------------------------
if selected_org_label == ALL_ORGS_LABEL:
    visible_objectives = objectives.copy()
else:
    selected_id = tree_label_to_id.get(selected_org_label)
    visible_objectives = objectives[objectives["org_unit_id"] == selected_id].copy()

if visible_objectives.empty:
    st.info(
        f"**{selected_org_label}** has no objectives of its own. "
        "Org units in the middle of the cascade (like a segment) often act as "
        "structural parents without owning objectives directly."
    )
    st.stop()

# Lookup tables for fast joins
kr_by_id = key_results.set_index("id").to_dict("index") if not key_results.empty else {}
obj_by_id = objectives.set_index("id").to_dict("index")
init_by_id = (
    initiatives.set_index("id").to_dict("index") if not initiatives.empty else {}
)


# Exec health emoji for initiatives (matches Initiative Updates page convention)
EXEC_RAG_ICONS = {
    "on_track":  "🟢",
    "at_risk":   "🟡",
    "off_track": "🔴",
    "blocked":   "🚧",
}


def exec_health_display(rag) -> str:
    """One-character display for the initiative's exec RAG."""
    if not isinstance(rag, str):
        return "—"
    return EXEC_RAG_ICONS.get(rag, "—")

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
                        owner_val = init.get("owner")
                        rows.append(
                            {
                                "initiative": init.get("title", "?"),
                                "owner": owner_val if isinstance(owner_val, str) and owner_val.strip() else "—",
                                "status": init.get("status", ""),
                                "exec health": exec_health_display(init.get("exec_rag")),
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

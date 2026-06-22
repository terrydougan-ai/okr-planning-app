"""
Manage Key Results — the measurable outcomes layer.

New patterns introduced on this page:
  * Numeric fields (start / target / current) with metric-unit picker
  * Cross-level parent_key_result_id picker (a team KR points at a company KR)
  * contribution_weight is only meaningful when a parent is set — the field
    hides itself otherwise to reduce noise
  * Live grade preview: as you type current_value, the computed grade updates
    in the form so you can see whether your numbers make sense before saving

Leading vs lagging KRs both live in this same table — the only structural
difference is whether `parent_key_result_id` is set. A leading indicator that
contributes to a lagging KR sets the parent link; a standalone KR doesn't.
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client


# Supabase
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
        "org_units": pd.DataFrame(sb.table("org_unit").select("*").execute().data),
        "objectives": pd.DataFrame(sb.table("objective").select("*").execute().data),
        "key_results": pd.DataFrame(sb.table("key_result").select("*").execute().data),
    }


def clear_cache():
    load_all.clear()


# -----------------------------------------------------------------------------
# Constants & helpers
# -----------------------------------------------------------------------------
# Common metric units. Free-text is allowed too via "other (specify)".
COMMON_UNITS = ["%", "count", "USD", "min", "hours", "days", "score", "NPS"]


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
    if g >= 0.7:
        return "🟢"
    if g >= 0.4:
        return "🟡"
    return "🔴"


def period_sort_key(period: str) -> tuple:
    if not period:
        return (9999, 9, period or "")
    try:
        q_part, y_part = period.split("-")
        return (int(y_part), int(q_part.lstrip("Q")), "")
    except (ValueError, AttributeError):
        return (9999, 9, period)


def build_org_tree_position(org_units: pd.DataFrame) -> dict:
    """Return {org_unit_id: tree_position_int} for stable sorting."""
    if org_units.empty:
        return {}
    by_parent: dict = {}
    for _, row in org_units.iterrows():
        # Coerce pandas NaN to Python None so root rows (null parent) group under
        # the same key the walk() call uses.
        pid = row["parent_unit_id"]
        if pid != pid:  # NaN check (NaN != NaN is the only value true here)
            pid = None
        by_parent.setdefault(pid, []).append(row)

    position = {}
    counter = [0]

    def walk(parent_id):
        children = by_parent.get(parent_id, [])
        level_order = {"company": 0, "segment": 1, "team": 2}
        children.sort(key=lambda r: (level_order.get(r["level"], 99), r["name"]))
        for row in children:
            position[row["id"]] = counter[0]
            counter[0] += 1
            walk(row["id"])

    walk(None)
    return position


def descendants_of_kr(kr_id: str, key_results: pd.DataFrame) -> set:
    """Set of KR ids that have kr_id (or one of its descendants) as parent."""
    if key_results.empty:
        return set()
    descendants = {kr_id}
    changed = True
    while changed:
        changed = False
        for _, kr in key_results.iterrows():
            if (
                kr.get("parent_key_result_id") in descendants
                and kr["id"] not in descendants
            ):
                descendants.add(kr["id"])
                changed = True
    return descendants


def eligible_parent_krs(
    key_results: pd.DataFrame,
    objectives: pd.DataFrame,
    org_units: pd.DataFrame,
    self_kr_id: str | None = None,
):
    """
    Return [(id, label)] of KRs that could be a parent of the KR being edited.
    Excludes the KR itself and its descendants (no cycles). Cross-level is the
    common case — a team KR pointing at a company KR — so we DON'T filter by
    level or org unit. The label shows enough context to pick the right one.
    """
    if key_results.empty:
        return []

    obj_by_id = objectives.set_index("id").to_dict("index")
    ou_name_by_id = org_units.set_index("id")["name"].to_dict()

    excluded = descendants_of_kr(self_kr_id, key_results) if self_kr_id else set()

    out = []
    for _, kr in key_results.iterrows():
        if kr["id"] in excluded:
            continue
        obj = obj_by_id.get(kr.get("objective_id"), {})
        ou_name = ou_name_by_id.get(obj.get("org_unit_id"), "?")
        unit = kr.get("metric_unit") or ""
        label = f"{ou_name} · {kr['title']} ({unit})"
        out.append((kr["id"], label))
    return out


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("📊 Manage Key Results")
st.caption(
    "Key Results are the measurable outcomes — 3 to 5 per objective. Leading "
    "and lagging indicators both live here; the difference is whether the KR "
    "has a parent KR it contributes to."
)

try:
    data = load_all()
except Exception as e:
    st.error(f"Couldn't reach Supabase: {e}")
    st.stop()

org_units = data["org_units"]
objectives = data["objectives"]
key_results = data["key_results"]

if objectives.empty:
    st.warning(
        "No objectives yet. Add one on the **Manage Strategy & Objectives** "
        "page before creating Key Results."
    )
    st.stop()

# Lookups
ou_name_by_id = org_units.set_index("id")["name"].to_dict()
obj_by_id = objectives.set_index("id").to_dict("index")
kr_by_id = key_results.set_index("id").to_dict("index") if not key_results.empty else {}

# Sorted objective options for the picker
tree_position = build_org_tree_position(org_units)
objs_for_dropdown = objectives.copy()
objs_for_dropdown["__pos"] = objs_for_dropdown["org_unit_id"].map(tree_position).fillna(999)
objs_for_dropdown["__period_key"] = objs_for_dropdown["period"].apply(period_sort_key)
objs_for_dropdown = objs_for_dropdown.sort_values(["__pos", "__period_key"])

objective_options = []
for _, o in objs_for_dropdown.iterrows():
    ou_name = ou_name_by_id.get(o["org_unit_id"], "?")
    label = f"{ou_name} · {o['period']} — {o['title']}"
    objective_options.append((o["id"], label))
objective_labels = [lbl for _, lbl in objective_options]
objective_id_by_label = {lbl: oid for oid, lbl in objective_options}


# ============================================================================
# CREATE
# ============================================================================
st.subheader("Add a new Key Result")

with st.expander("➕ Add a new KR", expanded=key_results.empty):
    with st.form("create_kr", clear_on_submit=True):
        c1, c2 = st.columns([3, 2])
        with c1:
            new_title = st.text_input(
                "Title", placeholder="e.g. Activation rate (team reaches first insight)"
            )
        with c2:
            new_obj_label = st.selectbox(
                "Belongs to objective", options=objective_labels, index=0
            )

        c3, c4, c5, c6 = st.columns(4)
        with c3:
            new_unit_choice = st.selectbox(
                "Metric unit", options=COMMON_UNITS + ["other (specify)"], index=0
            )
        with c4:
            new_start = st.number_input("Start value", value=0.0, step=1.0, format="%.2f")
        with c5:
            new_target = st.number_input(
                "Target value", value=100.0, step=1.0, format="%.2f"
            )
        with c6:
            new_current = st.number_input(
                "Current value", value=0.0, step=1.0, format="%.2f"
            )

        # Custom unit field shown only when "other" picked
        new_unit_custom = ""
        if new_unit_choice == "other (specify)":
            new_unit_custom = st.text_input(
                "Custom unit", placeholder="e.g. 'qualified demos'"
            )

        # Live grade preview while filling out the form
        preview_grade = kr_progress(new_start, new_target, new_current)
        st.caption(
            f"Preview grade: {grade_color(preview_grade)} **{preview_grade:.0%}** "
            f"({new_start} → {new_current} → {new_target})"
        )

        # Parent KR picker — cross-level is the common case
        eligible = eligible_parent_krs(key_results, objectives, org_units)
        parent_labels = ["— No parent (standalone KR) —"] + [lbl for _, lbl in eligible]
        parent_id_by_label = {lbl: kid for kid, lbl in eligible}

        c7, c8 = st.columns([3, 1])
        with c7:
            new_parent_label = st.selectbox(
                "Rolls up to (parent KR)",
                options=parent_labels,
                index=0,
                help=(
                    "Set this for leading indicators that contribute to a higher-level "
                    "KR (e.g. EMEA activation rolling up to global activation). Leave "
                    "as 'No parent' for standalone KRs."
                ),
            )
        with c8:
            new_weight = st.number_input(
                "Contribution weight",
                min_value=0.0,
                max_value=1.0,
                value=1.0,
                step=0.05,
                format="%.2f",
                help=(
                    "Only meaningful when a parent is set. 0.35 = this KR makes up "
                    "~35% of the parent's volume. Recorded now; not used in any "
                    "computation until roll-up math is turned on later."
                ),
            )

        submitted = st.form_submit_button("➕ Add KR", type="primary")
        if submitted:
            if not new_title.strip():
                st.error("Title is required.")
            elif new_unit_choice == "other (specify)" and not new_unit_custom.strip():
                st.error("Pick a unit or specify a custom one.")
            else:
                unit_value = (
                    new_unit_custom.strip()
                    if new_unit_choice == "other (specify)"
                    else new_unit_choice
                )
                parent_id = parent_id_by_label.get(new_parent_label)
                try:
                    sb.table("key_result").insert(
                        {
                            "objective_id": objective_id_by_label[new_obj_label],
                            "title": new_title.strip(),
                            "metric_unit": unit_value,
                            "start_value": new_start,
                            "target_value": new_target,
                            "current_value": new_current,
                            "parent_key_result_id": parent_id,
                            "contribution_weight": new_weight if parent_id else None,
                        }
                    ).execute()
                    clear_cache()
                    st.success(f"Added KR **{new_title}**.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Insert failed: {e}")


st.divider()


# ============================================================================
# LIST & EDIT
# ============================================================================
st.subheader("Existing Key Results")

if key_results.empty:
    st.info("No KRs yet — add one above.")
    st.stop()

# Build a parent → children map. Children appear immediately after their parent
# in the rendered list, with indentation. Cross-org-unit parents are fine — the
# cascade is the primary organizing principle here, not strict org-unit grouping.
all_kr_ids = set(key_results["id"].tolist())
children_by_parent: dict = {}
for _, kr_row in key_results.iterrows():
    parent_id = kr_row.get("parent_key_result_id")
    # Treat as a root if parent is missing or points to a KR not in our data
    # (defensive against orphans from direct DB deletes).
    if parent_id and parent_id in all_kr_ids:
        children_by_parent.setdefault(parent_id, []).append(kr_row)
    else:
        children_by_parent.setdefault(None, []).append(kr_row)


def sibling_sort_key(kr_row):
    """Order siblings by: org unit tree position, period, objective title, KR title."""
    obj = obj_by_id.get(kr_row["objective_id"], {})
    return (
        tree_position.get(obj.get("org_unit_id"), 999),
        period_sort_key(obj.get("period", "")),
        obj.get("title", ""),
        kr_row.get("title", ""),
    )


# Walk the tree, producing an ordered list of (kr_row, depth) pairs.
ordered_krs: list[tuple] = []


def walk_tree(parent_id, depth: int):
    siblings = sorted(children_by_parent.get(parent_id, []), key=sibling_sort_key)
    for child in siblings:
        ordered_krs.append((child, depth))
        walk_tree(child["id"], depth + 1)


walk_tree(None, 0)


for kr, depth in ordered_krs:
    obj = obj_by_id.get(kr["objective_id"], {})
    ou_name = ou_name_by_id.get(obj.get("org_unit_id"), "?")
    period = obj.get("period", "?")

    grade = kr_progress(kr.get("start_value"), kr.get("target_value"), kr.get("current_value"))
    parent_kr = kr_by_id.get(kr.get("parent_key_result_id"))

    # Indent children visually. The "↳ " arrow per depth level reads as a tree
    # branch. Streamlit collapses whitespace, so we use visible characters.
    prefix = "↳ " * depth

    # When indented, the parent is visually above — the "rolls up to" note
    # becomes redundant. Keep it only for orphan-root KRs (depth 0 + has a
    # parent_id pointing nowhere) so the dangling reference doesn't get hidden.
    parent_note = ""
    if depth == 0 and kr.get("parent_key_result_id") and not parent_kr:
        parent_note = "  ·  ⚠ parent KR not found"

    header = (
        f"{prefix}{grade_color(grade)} **{ou_name}** · {period} — "
        f"{kr['title']} ({grade:.0%}){parent_note}"
    )

    with st.expander(header, expanded=False):
        with st.form(f"edit_kr_{kr['id']}"):
            e1, e2 = st.columns([3, 2])
            with e1:
                et_title = st.text_input("Title", value=kr["title"])
            with e2:
                # Find current objective label
                cur_obj_label = next(
                    (lbl for oid, lbl in objective_options if oid == kr["objective_id"]),
                    objective_labels[0],
                )
                et_obj_label = st.selectbox(
                    "Belongs to objective",
                    options=objective_labels,
                    index=objective_labels.index(cur_obj_label),
                )

            # Unit handling — preserve custom values
            cur_unit = kr.get("metric_unit") or "%"
            if cur_unit in COMMON_UNITS:
                unit_options = COMMON_UNITS + ["other (specify)"]
                unit_default = unit_options.index(cur_unit)
                custom_default = ""
            else:
                unit_options = COMMON_UNITS + ["other (specify)"]
                unit_default = len(unit_options) - 1
                custom_default = cur_unit

            e3, e4, e5, e6 = st.columns(4)
            with e3:
                et_unit_choice = st.selectbox(
                    "Metric unit", options=unit_options, index=unit_default
                )
            with e4:
                et_start = st.number_input(
                    "Start value",
                    value=float(kr.get("start_value") or 0),
                    step=1.0,
                    format="%.2f",
                )
            with e5:
                et_target = st.number_input(
                    "Target value",
                    value=float(kr.get("target_value") or 100),
                    step=1.0,
                    format="%.2f",
                )
            with e6:
                et_current = st.number_input(
                    "Current value",
                    value=float(kr.get("current_value") or 0),
                    step=1.0,
                    format="%.2f",
                )

            et_unit_custom = ""
            if et_unit_choice == "other (specify)":
                et_unit_custom = st.text_input(
                    "Custom unit", value=custom_default
                )

            # Live grade preview
            preview_grade = kr_progress(et_start, et_target, et_current)
            st.caption(
                f"Preview grade: {grade_color(preview_grade)} **{preview_grade:.0%}** "
                f"({et_start} → {et_current} → {et_target})"
            )

            # Parent picker (excludes self + descendants)
            eligible = eligible_parent_krs(
                key_results, objectives, org_units, self_kr_id=kr["id"]
            )
            parent_labels = ["— No parent (standalone KR) —"] + [
                lbl for _, lbl in eligible
            ]
            parent_id_by_label = {lbl: kid for kid, lbl in eligible}

            cur_parent_label = "— No parent (standalone KR) —"
            if kr.get("parent_key_result_id"):
                for kid, lbl in eligible:
                    if kid == kr["parent_key_result_id"]:
                        cur_parent_label = lbl
                        break
            if cur_parent_label not in parent_labels:
                cur_parent_label = "— No parent (standalone KR) —"

            e7, e8 = st.columns([3, 1])
            with e7:
                et_parent_label = st.selectbox(
                    "Rolls up to (parent KR)",
                    options=parent_labels,
                    index=parent_labels.index(cur_parent_label),
                )
            with e8:
                et_weight = st.number_input(
                    "Contribution weight",
                    min_value=0.0,
                    max_value=1.0,
                    value=float(kr.get("contribution_weight") or 1.0),
                    step=0.05,
                    format="%.2f",
                )

            save = st.form_submit_button("💾 Save KR", type="primary")
            if save:
                if not et_title.strip():
                    st.error("Title is required.")
                elif et_unit_choice == "other (specify)" and not et_unit_custom.strip():
                    st.error("Pick a unit or specify a custom one.")
                else:
                    unit_value = (
                        et_unit_custom.strip()
                        if et_unit_choice == "other (specify)"
                        else et_unit_choice
                    )
                    new_parent_id = parent_id_by_label.get(et_parent_label)
                    try:
                        sb.table("key_result").update(
                            {
                                "objective_id": objective_id_by_label[et_obj_label],
                                "title": et_title.strip(),
                                "metric_unit": unit_value,
                                "start_value": et_start,
                                "target_value": et_target,
                                "current_value": et_current,
                                "parent_key_result_id": new_parent_id,
                                "contribution_weight": (
                                    et_weight if new_parent_id else None
                                ),
                            }
                        ).eq("id", kr["id"]).execute()
                        clear_cache()
                        st.success("Saved.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Update failed: {e}")

        st.caption(f"ID: `{kr['id']}`")


# --- Footnote ---------------------------------------------------------------
st.divider()
st.caption(
    "🗑️ **No delete in the UI.** KRs that have initiative links or are the "
    "parent of other KRs would cascade or orphan when removed — safer to handle "
    "in the Supabase SQL editor when you really need to delete one. To 'retire' "
    "a KR without deleting, you can set its objective's status to 'archived'."
)

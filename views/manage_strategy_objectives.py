"""
Manage Strategy & Objectives — the quarterly planning workhorse.

Strategy is annual and per-org-unit; Objectives are time-boxed (usually
quarterly) and belong to a Strategy. We edit them together because in practice
they're set together: "for this BU, this year's strategy, and the Q3 objectives
under it."

New wrinkle this page introduces: the parent_objective_id picker has to filter
sensibly. You can only align an objective UP to a parent objective whose period
is the same or comes earlier in the same year — you can't align a Q3 objective
to a hypothetical Q4 one, because the parent should already exist when the
child is being planned.
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
        "strategies": pd.DataFrame(sb.table("strategy").select("*").execute().data),
        "objectives": pd.DataFrame(sb.table("objective").select("*").execute().data),
    }


def clear_cache():
    load_all.clear()


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
OBJ_STATUSES = ["active", "closed", "archived"]


def period_sort_key(period: str) -> tuple:
    """
    Sort 'Q3-2026' style periods chronologically by (year, quarter).
    Unknown formats sort last but stably.
    """
    if not period:
        return (9999, 9, period or "")
    try:
        q_part, y_part = period.split("-")
        year = int(y_part)
        quarter = int(q_part.lstrip("Q"))
        return (year, quarter, "")
    except (ValueError, AttributeError):
        return (9999, 9, period)


def period_is_at_or_before(period_a: str, period_b: str) -> bool:
    """True if period_a is the same or earlier than period_b (chronologically)."""
    return period_sort_key(period_a) <= period_sort_key(period_b)


def build_org_tree(org_units: pd.DataFrame):
    """[(id, indented_label), ...] in display order."""
    if org_units.empty:
        return []

    by_parent: dict = {}
    for _, row in org_units.iterrows():
        by_parent.setdefault(row["parent_unit_id"], []).append(row)

    out: list[tuple[str, str]] = []

    def walk(parent_id, depth: int):
        children = by_parent.get(parent_id, [])
        level_order = {"company": 0, "segment": 1, "team": 2}
        children.sort(key=lambda r: (level_order.get(r["level"], 99), r["name"]))
        for row in children:
            prefix = "↳ " * depth
            out.append((row["id"], f"{prefix}{row['name']} ({row['level']})"))
            walk(row["id"], depth + 1)

    walk(None, 0)
    return out


def common_periods() -> list[str]:
    """A reasonable default period list — quarterly across nearby years."""
    return [
        "Q1-2025", "Q2-2025", "Q3-2025", "Q4-2025",
        "Q1-2026", "Q2-2026", "Q3-2026", "Q4-2026",
        "Q1-2027", "Q2-2027", "Q3-2027", "Q4-2027",
    ]


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("🧭 Manage Strategy & Objectives")
st.caption(
    "Strategy is the stable, annual layer. Objectives are the quarterly "
    "workhorses underneath it. Edit them together — they're rarely set apart."
)

try:
    data = load_all()
except Exception as e:
    st.error(f"Couldn't reach Supabase: {e}")
    st.stop()

org_units = data["org_units"]
strategies = data["strategies"]
objectives = data["objectives"]

if org_units.empty:
    st.warning(
        "No org units yet. Add at least one on the **Manage Org Units** page "
        "before creating a strategy."
    )
    st.stop()

# Lookups
ou_name_by_id = org_units.set_index("id")["name"].to_dict()
obj_by_id = objectives.set_index("id").to_dict("index") if not objectives.empty else {}
strategy_by_id = (
    strategies.set_index("id").to_dict("index") if not strategies.empty else {}
)

# Tree options for org-unit pickers
tree = build_org_tree(org_units)
tree_labels = [label for _, label in tree]
tree_id_by_label = {label: oid for oid, label in tree}


# ============================================================================
# STRATEGY
# ============================================================================
st.header("Strategy")
st.caption(
    "Each org unit has its own strategy. Company sets the top-level one; "
    "segments and teams set their own that align by sitting under it via the org tree."
)

# --- Create strategy ---------------------------------------------------------
with st.expander("➕ Add a new strategy", expanded=strategies.empty):
    with st.form("create_strategy", clear_on_submit=True):
        sc1, sc2, sc3 = st.columns([3, 3, 2])
        with sc1:
            s_title = st.text_input("Title", placeholder="e.g. Win mid-market by 2027")
        with sc2:
            s_ou_label = st.selectbox("Org unit", options=tree_labels, index=0)
        with sc3:
            s_year = st.number_input(
                "Fiscal year", min_value=2020, max_value=2035, value=2026, step=1
            )
        s_desc = st.text_area("Description (optional)", height=80)

        submitted = st.form_submit_button("➕ Add strategy", type="primary")

        if submitted:
            if not s_title.strip():
                st.error("Title is required.")
            else:
                try:
                    sb.table("strategy").insert(
                        {
                            "title": s_title.strip(),
                            "description": s_desc.strip() or None,
                            "org_unit_id": tree_id_by_label[s_ou_label],
                            "fiscal_year": int(s_year),
                        }
                    ).execute()
                    clear_cache()
                    st.success(f"Added strategy **{s_title}**.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Insert failed: {e}")

# --- List & edit strategies --------------------------------------------------
if strategies.empty:
    st.info("No strategies yet — add one above.")
else:
    # Sort by org unit (tree order) then by year desc
    tree_position = {oid: i for i, (oid, _) in enumerate(tree)}
    strategies_sorted = strategies.copy()
    strategies_sorted["__pos"] = strategies_sorted["org_unit_id"].map(tree_position).fillna(999)
    strategies_sorted = strategies_sorted.sort_values(["__pos", "fiscal_year"], ascending=[True, False])

    for _, strat in strategies_sorted.iterrows():
        ou_name = ou_name_by_id.get(strat["org_unit_id"], "?")
        header = f"**{ou_name}** · FY{strat['fiscal_year']} — {strat['title']}"

        with st.expander(header, expanded=False):
            with st.form(f"edit_strategy_{strat['id']}"):
                ec1, ec2, ec3 = st.columns([3, 3, 2])
                with ec1:
                    es_title = st.text_input("Title", value=strat["title"])
                with ec2:
                    cur_ou_label = next(
                        (lbl for oid, lbl in tree if oid == strat["org_unit_id"]),
                        tree_labels[0],
                    )
                    es_ou_label = st.selectbox(
                        "Org unit",
                        options=tree_labels,
                        index=tree_labels.index(cur_ou_label),
                    )
                with ec3:
                    es_year = st.number_input(
                        "Fiscal year",
                        min_value=2020,
                        max_value=2035,
                        value=int(strat["fiscal_year"]),
                        step=1,
                    )
                es_desc = st.text_area(
                    "Description", value=strat.get("description") or "", height=80
                )

                save = st.form_submit_button("💾 Save strategy", type="primary")
                if save:
                    if not es_title.strip():
                        st.error("Title is required.")
                    else:
                        try:
                            sb.table("strategy").update(
                                {
                                    "title": es_title.strip(),
                                    "description": es_desc.strip() or None,
                                    "org_unit_id": tree_id_by_label[es_ou_label],
                                    "fiscal_year": int(es_year),
                                }
                            ).eq("id", strat["id"]).execute()
                            clear_cache()
                            st.success("Saved.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Update failed: {e}")

            st.caption(f"ID: `{strat['id']}`")


st.divider()


# ============================================================================
# OBJECTIVES
# ============================================================================
st.header("Objectives")
st.caption(
    "Time-boxed, qualitative goals under a strategy. The `parent objective` "
    "picker is where the cascade alignment happens: a team objective points at "
    "the segment or company objective it supports."
)

if strategies.empty:
    st.info("Add a strategy first — objectives must belong to one.")
    st.stop()

# Strategy options for the objective form
strategy_options = []
tree_position = {oid: i for i, (oid, _) in enumerate(tree)}
strategies_for_dropdown = strategies.copy()
strategies_for_dropdown["__pos"] = strategies_for_dropdown["org_unit_id"].map(tree_position).fillna(999)
strategies_for_dropdown = strategies_for_dropdown.sort_values(["__pos", "fiscal_year"])

for _, srow in strategies_for_dropdown.iterrows():
    ou_name = ou_name_by_id.get(srow["org_unit_id"], "?")
    label = f"{ou_name} · FY{srow['fiscal_year']} — {srow['title']}"
    strategy_options.append((srow["id"], label, srow["org_unit_id"]))

strategy_labels = [lbl for _, lbl, _ in strategy_options]
strategy_id_by_label = {lbl: sid for sid, lbl, _ in strategy_options}
strategy_ou_by_id = {sid: ouid for sid, _, ouid in strategy_options}


def eligible_parents_for_period(child_period: str, child_obj_id: str | None = None):
    """
    Return [(id, label)] of objectives that could be a valid parent for an
    objective with the given period. Rules:
      * Parent's period must be the same or earlier than the child's.
      * Can't be the child itself.
      * Excludes descendants of the child (no cycles) — we walk parent_objective_id.
    """
    if objectives.empty:
        return []

    # Build descendant set to exclude
    descendants: set = set()
    if child_obj_id:
        # walk: who has child_obj_id (or one of its descendants) as their parent_objective_id?
        descendants.add(child_obj_id)
        changed = True
        while changed:
            changed = False
            for _, o in objectives.iterrows():
                if o.get("parent_objective_id") in descendants and o["id"] not in descendants:
                    descendants.add(o["id"])
                    changed = True

    out = []
    for _, o in objectives.iterrows():
        if o["id"] in descendants:
            continue
        if not period_is_at_or_before(o.get("period"), child_period):
            continue
        ou_name = ou_name_by_id.get(o["org_unit_id"], "?")
        out.append((o["id"], f"{ou_name} · {o['period']} — {o['title']}"))
    return out


# --- Create objective --------------------------------------------------------
with st.expander("➕ Add a new objective", expanded=objectives.empty):
    with st.form("create_objective", clear_on_submit=True):
        oc1, oc2 = st.columns([3, 2])
        with oc1:
            o_title = st.text_input(
                "Title", placeholder="e.g. Turn new signups into activated, paying teams"
            )
        with oc2:
            o_strategy_label = st.selectbox(
                "Strategy", options=strategy_labels, index=0
            )

        oc3, oc4, oc5 = st.columns([2, 2, 2])
        with oc3:
            periods = common_periods()
            o_period = st.selectbox("Period", options=periods, index=periods.index("Q3-2026") if "Q3-2026" in periods else 0)
        with oc4:
            o_owner = st.text_input("Owner", placeholder="e.g. VP Product")
        with oc5:
            o_status = st.selectbox("Status", options=OBJ_STATUSES, index=0)

        # Parent picker: filtered by period
        eligible = eligible_parents_for_period(o_period)
        parent_labels = ["— No parent (top of cascade) —"] + [lbl for _, lbl in eligible]
        parent_id_by_label = {lbl: oid for oid, lbl in eligible}
        o_parent_label = st.selectbox(
            "Aligns to (parent objective)",
            options=parent_labels,
            index=0,
            help="Only objectives in the same or an earlier period are shown.",
        )

        o_desc = st.text_area("Description (optional)", height=80)

        submitted = st.form_submit_button("➕ Add objective", type="primary")
        if submitted:
            if not o_title.strip():
                st.error("Title is required.")
            else:
                parent_id = parent_id_by_label.get(o_parent_label)
                strategy_id = strategy_id_by_label[o_strategy_label]
                try:
                    sb.table("objective").insert(
                        {
                            "title": o_title.strip(),
                            "description": o_desc.strip() or None,
                            "owner": o_owner.strip() or None,
                            "period": o_period,
                            "status": o_status,
                            "strategy_id": strategy_id,
                            "org_unit_id": strategy_ou_by_id[strategy_id],
                            "parent_objective_id": parent_id,
                        }
                    ).execute()
                    clear_cache()
                    st.success(f"Added objective **{o_title}**.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Insert failed: {e}")


# --- List & edit objectives --------------------------------------------------
if objectives.empty:
    st.info("No objectives yet — add one above.")
    st.stop()

# Sort: by org unit tree position, then period chronologically
objs_sorted = objectives.copy()
objs_sorted["__pos"] = objs_sorted["org_unit_id"].map(tree_position).fillna(999)
objs_sorted["__period_key"] = objs_sorted["period"].apply(period_sort_key)
objs_sorted = objs_sorted.sort_values(["__pos", "__period_key"])

for _, obj in objs_sorted.iterrows():
    ou_name = ou_name_by_id.get(obj["org_unit_id"], "?")
    parent_obj = obj_by_id.get(obj.get("parent_objective_id"))
    parent_note = f" — ↑ aligns to: *{parent_obj['title']}*" if parent_obj else ""

    status = obj.get("status", "active")
    status_icon = {"active": "🟢", "closed": "🔵", "archived": "⚪"}.get(status, "")
    header = f"{status_icon} **{ou_name}** · {obj['period']} — {obj['title']}{parent_note}"

    with st.expander(header, expanded=False):
        with st.form(f"edit_obj_{obj['id']}"):
            ec1, ec2 = st.columns([3, 2])
            with ec1:
                eo_title = st.text_input("Title", value=obj["title"])
            with ec2:
                # Find current strategy in dropdown
                cur_strat_label = next(
                    (lbl for sid, lbl, _ in strategy_options if sid == obj["strategy_id"]),
                    strategy_labels[0],
                )
                eo_strategy_label = st.selectbox(
                    "Strategy",
                    options=strategy_labels,
                    index=strategy_labels.index(cur_strat_label),
                )

            ec3, ec4, ec5 = st.columns([2, 2, 2])
            with ec3:
                periods = common_periods()
                cur_period = obj.get("period", "Q3-2026")
                if cur_period not in periods:
                    periods = [cur_period] + periods
                eo_period = st.selectbox(
                    "Period",
                    options=periods,
                    index=periods.index(cur_period),
                )
            with ec4:
                eo_owner = st.text_input("Owner", value=obj.get("owner") or "")
            with ec5:
                eo_status = st.selectbox(
                    "Status",
                    options=OBJ_STATUSES,
                    index=OBJ_STATUSES.index(status) if status in OBJ_STATUSES else 0,
                )

            # Parent picker with period-and-cycle filtering
            eligible = eligible_parents_for_period(eo_period, child_obj_id=obj["id"])
            parent_labels = ["— No parent (top of cascade) —"] + [lbl for _, lbl in eligible]
            parent_id_by_label = {lbl: oid for oid, lbl in eligible}

            cur_parent_label = "— No parent (top of cascade) —"
            if obj.get("parent_objective_id"):
                for oid, lbl in eligible:
                    if oid == obj["parent_objective_id"]:
                        cur_parent_label = lbl
                        break

            # Edge case: current parent is no longer eligible (e.g. period was changed)
            # — fall back to "no parent" rather than silently picking the wrong one
            if cur_parent_label not in parent_labels:
                cur_parent_label = "— No parent (top of cascade) —"

            eo_parent_label = st.selectbox(
                "Aligns to (parent objective)",
                options=parent_labels,
                index=parent_labels.index(cur_parent_label),
                help="Only objectives in the same or an earlier period are shown.",
            )

            eo_desc = st.text_area(
                "Description", value=obj.get("description") or "", height=80
            )

            save = st.form_submit_button("💾 Save objective", type="primary")
            if save:
                if not eo_title.strip():
                    st.error("Title is required.")
                else:
                    new_parent_id = parent_id_by_label.get(eo_parent_label)
                    new_strategy_id = strategy_id_by_label[eo_strategy_label]
                    try:
                        sb.table("objective").update(
                            {
                                "title": eo_title.strip(),
                                "description": eo_desc.strip() or None,
                                "owner": eo_owner.strip() or None,
                                "period": eo_period,
                                "status": eo_status,
                                "strategy_id": new_strategy_id,
                                "org_unit_id": strategy_ou_by_id[new_strategy_id],
                                "parent_objective_id": new_parent_id,
                            }
                        ).eq("id", obj["id"]).execute()
                        clear_cache()
                        st.success("Saved.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Update failed: {e}")

        st.caption(f"ID: `{obj['id']}`")


# --- Footnote ---------------------------------------------------------------
st.divider()
st.caption(
    "🗑️ **Soft-delete via status: 'archived'** rather than hard delete. "
    "Archived objectives stay queryable for historical analysis. Hard delete is "
    "available in the Supabase SQL editor when you really need to wipe a row."
)

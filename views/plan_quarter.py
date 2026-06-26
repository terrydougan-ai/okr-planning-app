"""
Plan a Quarter — the quarterly planning workspace.

Pick an org unit + quarterly period. The page shows every quarterly objective
in scope side by side, each fully editable inline (KRs, initiatives, business
cases). Above them sit two read-only context cards: the annual strategy and
yearly objectives, plus the previous quarter's results.

This page replaces the older 'Plan an Objective' page. The deep-dive workflow
is still available — just expand the objective card you want to focus on and
collapse the others.

How yearly vs quarterly are distinguished:
  Yearly objectives have period = "FY{year}" (e.g. "FY2026").
  Quarterly objectives have period = "Q3-2026".
  This page lists ONLY quarterly objectives; yearly ones appear in the
  context card. Both live in the `objective` table — the distinction is the
  period string.
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client


# -----------------------------------------------------------------------------
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
        "key_results": pd.DataFrame(sb.table("key_result").select("*").execute().data),
        "initiatives": pd.DataFrame(sb.table("initiative").select("*").execute().data),
        "links": pd.DataFrame(
            sb.table("initiative_key_result").select("*").execute().data
        ),
        "business_cases": pd.DataFrame(
            sb.table("business_case").select("*").execute().data
        ),
    }


def clear_cache():
    load_all.clear()


# -----------------------------------------------------------------------------
# Constants & helpers
# -----------------------------------------------------------------------------
COMMON_UNITS = ["%", "count", "USD", "min", "hours", "days", "score", "NPS"]
INIT_STATUSES = ["proposed", "active", "done", "killed"]
MILESTONE_STATUSES = ["on_track", "at_risk", "blocked"]
DECISIONS = ["pending", "approved", "rejected"]
EFFORT_SIZES = ["", "XS", "S", "M", "L", "XL"]
OBJ_STATUSES = ["active", "closed", "archived"]


def period_sort_key(period: str) -> tuple:
    if not period:
        return (9999, 9, period or "")
    if period.startswith("FY"):
        try:
            return (int(period[2:]), 0, "")  # yearly sorts before Q1 of same year
        except ValueError:
            return (9999, 9, period)
    try:
        q, y = period.split("-")
        return (int(y), int(q.lstrip("Q")), "")
    except (ValueError, AttributeError):
        return (9999, 9, period)


def year_from_period(period: str):
    if not period:
        return None
    if period.startswith("FY"):
        try:
            return int(period[2:])
        except ValueError:
            return None
    try:
        return int(period.split("-")[1])
    except (ValueError, AttributeError, IndexError):
        return None


def prior_quarterly_period(period: str, all_periods) -> str | None:
    """Find the quarterly period right before `period`. Skips yearly periods."""
    quarterly_only = [p for p in set(all_periods) if p and not p.startswith("FY")]
    sorted_periods = sorted(quarterly_only, key=period_sort_key)
    try:
        idx = sorted_periods.index(period)
        return sorted_periods[idx - 1] if idx > 0 else None
    except ValueError:
        return None


def kr_progress(start, target, current) -> float:
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


def fmt_money(v) -> str:
    if v is None or pd.isna(v) or v == 0:
        return "—"
    return f"${v:,.0f}"


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("✏️ Plan a Quarter")
st.caption(
    "The quarterly workshop. Pick an org unit and period; everything below is "
    "editable inline. Annual context sits at the top so the cascade stays visible."
)

try:
    data = load_all()
except Exception as e:
    st.error(f"Couldn't reach Supabase: {e}")
    st.stop()

org_units = data["org_units"]
strategies = data["strategies"]
objectives = data["objectives"]
key_results = data["key_results"]
initiatives = data["initiatives"]
links = data["links"]
business_cases = data["business_cases"]

if org_units.empty:
    st.warning("No org units yet. Add one on **Manage → Org Units**.")
    st.stop()


# -----------------------------------------------------------------------------
# Pickers: org unit + period
# -----------------------------------------------------------------------------
ou_name_by_id = org_units.set_index("id")["name"].to_dict()
ou_id_by_name = {v: k for k, v in ou_name_by_id.items()}

ou_sorted = org_units.copy()
level_order = {"company": 0, "segment": 1, "team": 2}
ou_sorted["__order"] = ou_sorted["level"].map(level_order).fillna(99)
ou_sorted = ou_sorted.sort_values(["__order", "name"])
ou_position = {row["id"]: i for i, (_, row) in enumerate(ou_sorted.iterrows())}

# Build the indented tree labels for the picker. Walk parent_unit_id from the
# roots downward so children appear right under their parents with a ↳ prefix
# per depth level.
children_by_parent: dict = {}
for _, row in org_units.iterrows():
    pid = row["parent_unit_id"]
    if pid != pid:  # NaN check
        pid = None
    children_by_parent.setdefault(pid, []).append(row)

tree_labels: list[str] = []
tree_label_to_id: dict = {}


def _walk_org_tree(parent_id, depth: int):
    siblings = sorted(
        children_by_parent.get(parent_id, []),
        key=lambda r: (level_order.get(r.get("level"), 99), r["name"]),
    )
    for row in siblings:
        prefix = "↳ " * depth
        label = f"{prefix}{row['name']}"
        tree_labels.append(label)
        tree_label_to_id[label] = row["id"]
        _walk_org_tree(row["id"], depth + 1)


_walk_org_tree(None, 0)

# Periods: only quarterly ones, derived from existing objectives + a sensible default list
existing_quarterly = (
    [p for p in objectives["period"].dropna().unique() if not str(p).startswith("FY")]
    if not objectives.empty
    else []
)
default_quarters = [
    "Q1-2025", "Q2-2025", "Q3-2025", "Q4-2025",
    "Q1-2026", "Q2-2026", "Q3-2026", "Q4-2026",
    "Q1-2027", "Q2-2027", "Q3-2027", "Q4-2027",
]
period_options = sorted(set(existing_quarterly) | set(default_quarters), key=period_sort_key)

pc1, pc2 = st.columns([2, 1])
with pc1:
    # Default to sticky scope from session state if set
    _saved_org_id = st.session_state.get("scope_org_id")
    _default_org_idx = 0
    if _saved_org_id:
        for _i, _lbl in enumerate(tree_labels):
            if tree_label_to_id.get(_lbl) == _saved_org_id:
                _default_org_idx = _i
                break
    selected_ou_label = st.selectbox(
        "**Working on**",
        options=tree_labels,
        index=_default_org_idx,
        help=(
            "Pick the org unit whose quarter you want to plan. "
            "Indented entries (↳) sit under the unit above them. "
            "Your selection persists across pages."
        ),
    )
with pc2:
    # Default to sticky period from session state, falling back to Q3-2026
    _saved_period = st.session_state.get("scope_period")
    if _saved_period and _saved_period in period_options:
        default_period_idx = period_options.index(_saved_period)
    elif "Q3-2026" in period_options:
        default_period_idx = period_options.index("Q3-2026")
    else:
        default_period_idx = 0
    selected_period = st.selectbox(
        "**Period**", options=period_options, index=default_period_idx
    )

selected_ou_id = tree_label_to_id[selected_ou_label]
selected_ou_name = ou_name_by_id[selected_ou_id]
selected_year = year_from_period(selected_period)

# Persist current scope so other pages default to it
st.session_state["scope_org_id"] = selected_ou_id
st.session_state["scope_org_name"] = selected_ou_name
st.session_state["scope_period"] = selected_period


# -----------------------------------------------------------------------------
# Annual context card (read-only) — full cascade
# -----------------------------------------------------------------------------
# Walks UP the org-unit hierarchy from the selected unit to the root, showing
# each ancestor's strategies and yearly objectives. The team's planning has to
# make sense inside every strategy in this chain, so all of them are visible.
parent_by_id: dict = {}
for _, row in org_units.iterrows():
    pid = row.get("parent_unit_id")
    if pid != pid:  # NaN check
        pid = None
    parent_by_id[row["id"]] = pid

# Walk from selected unit up to root, collecting ids bottom-up, then reverse
# so root sits at the top of the card.
ids_up: list = []
cur = selected_ou_id
visited: set = set()  # defensive against cycles in parent_unit_id
while cur is not None and cur not in visited:
    ids_up.append(cur)
    visited.add(cur)
    cur = parent_by_id.get(cur)
chain_ids = list(reversed(ids_up))

with st.container(border=True):
    st.markdown(
        f"**📜 Annual context · {selected_ou_name} · FY{selected_year}**"
    )
    st.caption(
        "The cascade from the top-level org down to here. Your quarterly "
        "planning sits inside this chain of strategies."
    )

    for depth, ou_id in enumerate(chain_ids):
        ou_name_here = ou_name_by_id.get(ou_id, "?")
        prefix = "↳ " * depth
        is_current = ou_id == selected_ou_id
        marker = "  ←  *currently planning*" if is_current else ""
        st.markdown(f"{prefix}**{ou_name_here}**{marker}")

        # Strategies for this unit in the selected fiscal year
        unit_strategies = (
            strategies[
                (strategies["org_unit_id"] == ou_id)
                & (strategies["fiscal_year"] == selected_year)
            ]
            if not strategies.empty
            else pd.DataFrame()
        )

        if unit_strategies.empty:
            st.caption(f"{prefix}_No strategy defined at this level._")
            continue

        for _, s in unit_strategies.iterrows():
            # Use a small gray "Strategy:" tag prefix so it's clear what type of
            # thing each line represents (vs the yearly objectives below).
            st.markdown(
                f"{prefix}📜 <span style='color:#6B7280;font-size:0.85em'>"
                f"Strategy:</span> _{s['title']}_",
                unsafe_allow_html=True,
            )

            # Description snippet
            desc = s.get("description")
            if isinstance(desc, str) and desc.strip():
                snippet = desc.strip().replace("\n", " ")
                if len(snippet) > 160:
                    snippet = snippet[:160].rstrip() + "…"
                st.caption(f"{prefix}{snippet}")

            # Yearly objectives under this specific strategy
            strat_yearly_objs = (
                objectives[
                    (objectives["strategy_id"] == s["id"])
                    & (objectives["period"] == f"FY{selected_year}")
                ]
                if not objectives.empty
                else pd.DataFrame()
            )

            if strat_yearly_objs.empty:
                continue

            for _, yo in strat_yearly_objs.iterrows():
                yo_status = yo.get("status", "active")
                yo_dot = {"active": "🟢", "closed": "🔵", "archived": "⚪"}.get(yo_status, "")
                yo_krs = (
                    key_results[key_results["objective_id"] == yo["id"]]
                    if not key_results.empty
                    else pd.DataFrame()
                )
                yo_grades = [
                    kr_progress(
                        k.get("start_value"),
                        k.get("target_value"),
                        k.get("current_value"),
                    )
                    for _, k in yo_krs.iterrows()
                ]
                grade_summary = ""
                if yo_grades:
                    avg = sum(yo_grades) / len(yo_grades)
                    grade_summary = f" — {grade_color(avg)} avg {avg:.0%}"
                st.markdown(
                    f"{prefix}- {yo_dot} <span style='color:#6B7280;font-size:0.85em'>"
                    f"Yearly:</span> **{yo['title']}**{grade_summary}",
                    unsafe_allow_html=True,
                )


# -----------------------------------------------------------------------------
# Previous quarter card (read-only)
# -----------------------------------------------------------------------------
prior_p = prior_quarterly_period(
    selected_period, objectives["period"].dropna().tolist()
)
prior_objs = pd.DataFrame()
if prior_p:
    prior_objs = objectives[
        (objectives["org_unit_id"] == selected_ou_id)
        & (objectives["period"] == prior_p)
    ]

if prior_p and not prior_objs.empty:
    with st.container(border=True):
        st.markdown(f"**📋 Previous quarter · {prior_p}**")
        for _, p_obj in prior_objs.iterrows():
            p_obj_krs = (
                key_results[key_results["objective_id"] == p_obj["id"]]
                if not key_results.empty
                else pd.DataFrame()
            )
            grades = [
                kr_progress(
                    kr.get("start_value"),
                    kr.get("target_value"),
                    kr.get("current_value"),
                )
                for _, kr in p_obj_krs.iterrows()
            ]
            if grades:
                avg = sum(grades) / len(grades)
                grade_summary = (
                    f"{grade_color(avg)} avg {avg:.0%} across {len(grades)} KR"
                    f"{'s' if len(grades) != 1 else ''}"
                )
            else:
                grade_summary = "_no KRs defined_"
            p_status = p_obj.get("status", "active")
            status_dot = {"active": "🟢", "closed": "🔵", "archived": "⚪"}.get(p_status, "")
            st.markdown(f"- {status_dot} **{p_obj['title']}** — {grade_summary}")


# -----------------------------------------------------------------------------
# Add a new quarterly objective
# -----------------------------------------------------------------------------
# Parent picker auto-filters to YEARLY objectives in the same org unit + year,
# so the natural action is "this Q3 objective rolls up to a FY2026 objective."
with st.expander("➕ Plan a new quarterly objective", expanded=False):
    if strategies.empty:
        st.info(
            "No strategies defined. Set up an annual strategy on **Annual "
            "Strategy & Objectives** first."
        )
    else:
        # Strategy: prefer the one matching this org unit + year
        candidate_strats = strategies[strategies["org_unit_id"] == selected_ou_id]
        if selected_year is not None and not candidate_strats.empty:
            year_match = candidate_strats[
                candidate_strats["fiscal_year"] == selected_year
            ]
            if not year_match.empty:
                candidate_strats = year_match

        if candidate_strats.empty:
            st.info(
                f"No strategy exists for **{selected_ou_name}** in this fiscal "
                "year. Create one on **Annual Strategy & Objectives** first."
            )
        else:
            default_strategy = candidate_strats.sort_values(
                "fiscal_year", ascending=False
            ).iloc[0]

            with st.form("create_quarterly_objective", clear_on_submit=True):
                nq_title = st.text_input(
                    "Title",
                    placeholder="e.g. Turn new signups into activated, paying teams",
                )
                nqc1, nqc2 = st.columns(2)
                with nqc1:
                    nq_owner = st.text_input("Owner", placeholder="e.g. VP Product")
                with nqc2:
                    nq_status = st.selectbox(
                        "Status", options=OBJ_STATUSES, index=0
                    )

                # Parent picker — YEARLY objectives in this org + year only
                parent_candidates = []
                if selected_year is not None and not objectives.empty:
                    parent_candidates_df = objectives[
                        (objectives["org_unit_id"] == selected_ou_id)
                        & (objectives["period"] == f"FY{selected_year}")
                    ]
                    for _, yo in parent_candidates_df.iterrows():
                        parent_candidates.append(
                            (yo["id"], f"FY{selected_year} — {yo['title']}")
                        )

                parent_labels = ["— No parent (top of cascade) —"] + [
                    lbl for _, lbl in parent_candidates
                ]
                parent_id_by_label = {lbl: oid for oid, lbl in parent_candidates}

                nq_parent_label = st.selectbox(
                    "Aligns to (yearly objective)",
                    options=parent_labels,
                    index=1 if parent_candidates else 0,
                    help=(
                        "The yearly objective this quarter's bet ladders up to. "
                        "Only yearly objectives for this org unit and fiscal year "
                        "are shown."
                    ),
                )

                nq_desc = st.text_area("Description (optional)", height=80)

                submitted = st.form_submit_button(
                    "➕ Add quarterly objective", type="primary"
                )
                if submitted:
                    if not nq_title.strip():
                        st.error("Title is required.")
                    else:
                        new_parent_id = parent_id_by_label.get(nq_parent_label)
                        try:
                            sb.table("objective").insert(
                                {
                                    "title": nq_title.strip(),
                                    "description": nq_desc.strip() or None,
                                    "owner": nq_owner.strip() or None,
                                    "period": selected_period,
                                    "status": nq_status,
                                    "strategy_id": default_strategy["id"],
                                    # Derive org_unit_id from the strategy, not
                                    # the page picker — keeps objective and
                                    # strategy's scope in sync.
                                    "org_unit_id": default_strategy["org_unit_id"],
                                    "parent_objective_id": new_parent_id,
                                }
                            ).execute()
                            clear_cache()
                            st.success(
                                f"Added quarterly objective **{nq_title}**."
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Insert failed: {e}")


# -----------------------------------------------------------------------------
# QUARTERLY OBJECTIVES IN SCOPE
# -----------------------------------------------------------------------------
st.divider()

# Filter to quarterly objectives in the selected org unit + period
quarterly_objs = (
    objectives[
        (objectives["org_unit_id"] == selected_ou_id)
        & (objectives["period"] == selected_period)
    ]
    if not objectives.empty
    else pd.DataFrame()
)

st.subheader(
    f"Quarterly Objectives — {selected_ou_name} · {selected_period} "
    f"({len(quarterly_objs)})"
)

if quarterly_objs.empty:
    st.info(
        f"No quarterly objectives for **{selected_ou_name}** in {selected_period} "
        "yet. Use the expander above to plan one."
    )
    st.stop()


# Lookups
init_by_id = (
    initiatives.set_index("id").to_dict("index") if not initiatives.empty else {}
)
bc_by_init = (
    business_cases.set_index("initiative_id").to_dict("index")
    if not business_cases.empty
    else {}
)
obj_by_id = objectives.set_index("id").to_dict("index")


# -----------------------------------------------------------------------------
# Pre-compute the parent-objective picker (used by each quarterly's edit form)
# -----------------------------------------------------------------------------
# Yearly objectives in this org unit + fiscal year are the natural parents
# a quarterly can ladder up to. Build the picker list once and reuse it on
# every edit form below.
edit_parent_candidates: list = []
if selected_year is not None and not objectives.empty:
    edit_parent_candidates_df = objectives[
        (objectives["org_unit_id"] == selected_ou_id)
        & (objectives["period"] == f"FY{selected_year}")
    ]
    for _, yo in edit_parent_candidates_df.iterrows():
        edit_parent_candidates.append(
            (yo["id"], f"FY{selected_year} — {yo['title']}")
        )

NO_PARENT_LABEL = "— No parent (top of cascade) —"
edit_parent_labels = [NO_PARENT_LABEL] + [lbl for _, lbl in edit_parent_candidates]
edit_parent_id_by_label = {lbl: oid for oid, lbl in edit_parent_candidates}
edit_parent_label_by_id = {oid: lbl for oid, lbl in edit_parent_candidates}


# -----------------------------------------------------------------------------
# Group quarterly objectives by their yearly parent
# -----------------------------------------------------------------------------
# Each quarterly objective lands in one of three buckets:
#   1. Aligned to a yearly objective (its parent_objective_id points at a
#      yearly objective that exists). Group keyed by the yearly objective's id.
#   2. Aligned to something that isn't a yearly objective (legacy data, or
#      cross-period parenting) — bucket under "Unaligned".
#   3. No parent at all — bucket under "Unaligned".
#
# Within each group, quarterlies sort alphabetically by title.
UNALIGNED_KEY = "__unaligned__"

quarterly_groups: dict = {}  # group_key → list of quarterly objective rows
for _, qobj in quarterly_objs.iterrows():
    parent_id = qobj.get("parent_objective_id")
    # NaN-safe coercion
    if parent_id != parent_id:
        parent_id = None
    parent_obj = obj_by_id.get(parent_id) if parent_id else None
    parent_is_yearly = (
        parent_obj is not None
        and isinstance(parent_obj.get("period"), str)
        and parent_obj["period"].startswith("FY")
    )
    group_key = parent_id if parent_is_yearly else UNALIGNED_KEY
    quarterly_groups.setdefault(group_key, []).append(qobj)

# Determine group order: yearly-parent groups (alphabetical by yearly title)
# come first, "Unaligned" sits at the bottom.
yearly_parent_keys = [k for k in quarterly_groups if k != UNALIGNED_KEY]
yearly_parent_keys.sort(
    key=lambda k: (obj_by_id.get(k) or {}).get("title", "").lower()
)
ordered_group_keys = yearly_parent_keys + (
    [UNALIGNED_KEY] if UNALIGNED_KEY in quarterly_groups else []
)

for group_key in ordered_group_keys:
    group_qobjs = quarterly_groups[group_key]
    # Stable in-group order: alphabetical by quarterly title
    group_qobjs = sorted(
        group_qobjs, key=lambda q: (q.get("title") or "").lower()
    )

    # Group header
    if group_key == UNALIGNED_KEY:
        st.markdown(
            "##### 🔸 Unaligned "
            f"<span style='color:#6B7280;font-size:0.85em'>"
            f"({len(group_qobjs)} objective{'s' if len(group_qobjs) != 1 else ''} "
            f"with no yearly parent)</span>",
            unsafe_allow_html=True,
        )
        st.caption(
            "These quarterlies don't roll up to any yearly objective. That's "
            "legitimate (matrix planning, cross-period work), but visible here "
            "as a check on whether each is intentionally unaligned."
        )
    else:
        yearly_parent = obj_by_id.get(group_key)
        yearly_title = yearly_parent.get("title", "?") if yearly_parent else "?"
        st.markdown(
            f"##### 📋 Aligned to yearly: *{yearly_title}* "
            f"<span style='color:#6B7280;font-size:0.85em'>"
            f"({len(group_qobjs)} quarterly objective"
            f"{'s' if len(group_qobjs) != 1 else ''})</span>",
            unsafe_allow_html=True,
        )

    for qobj in group_qobjs:
        q_status = qobj.get("status", "active")
        status_icon = {"active": "🟢", "closed": "🔵", "archived": "⚪"}.get(q_status, "")
        qobj_header = f"{status_icon} **{qobj['title']}**"

        with st.expander(qobj_header, expanded=False):
            # --- Inline edit form for the quarterly objective itself ---
            with st.form(f"edit_qobj_{qobj['id']}"):
                eq_title = st.text_input("Title", value=qobj["title"])
                eqc1, eqc2 = st.columns(2)
                with eqc1:
                    cur_owner = qobj.get("owner")
                    eq_owner = st.text_input(
                        "Owner",
                        value=cur_owner if isinstance(cur_owner, str) else "",
                    )
                with eqc2:
                    eq_status = st.selectbox(
                        "Status",
                        options=OBJ_STATUSES,
                        index=OBJ_STATUSES.index(q_status)
                        if q_status in OBJ_STATUSES
                        else 0,
                    )

                # Parent objective picker — yearly objectives in this org+year
                # Default to whichever yearly the quarterly currently points at;
                # fall back to "No parent" if its parent is missing or non-yearly.
                cur_parent_id = qobj.get("parent_objective_id")
                if cur_parent_id != cur_parent_id:  # NaN
                    cur_parent_id = None
                cur_parent_label = (
                    edit_parent_label_by_id.get(cur_parent_id, NO_PARENT_LABEL)
                    if cur_parent_id
                    else NO_PARENT_LABEL
                )
                # If the current parent isn't a known yearly (e.g. matrix
                # alignment to a different unit's yearly), preserve it in the
                # options so the user can still see it.
                effective_labels = list(edit_parent_labels)
                if cur_parent_id and cur_parent_label == NO_PARENT_LABEL and cur_parent_id in obj_by_id:
                    other_parent = obj_by_id[cur_parent_id]
                    other_label = f"(other) — {other_parent.get('title', '?')}"
                    effective_labels.append(other_label)
                    cur_parent_label = other_label
                    edit_parent_id_by_label[other_label] = cur_parent_id

                eq_parent_label = st.selectbox(
                    "Aligns to (yearly objective)",
                    options=effective_labels,
                    index=effective_labels.index(cur_parent_label)
                    if cur_parent_label in effective_labels
                    else 0,
                    help=(
                        "Re-parent this quarterly objective. Only yearly "
                        "objectives in this org unit and fiscal year are shown."
                    ),
                )

                cur_desc = qobj.get("description")
                eq_desc = st.text_area(
                    "Description",
                    value=cur_desc if isinstance(cur_desc, str) else "",
                    height=80,
                )

                save_qobj = st.form_submit_button("💾 Save objective")
                if save_qobj:
                    if not eq_title.strip():
                        st.error("Title is required.")
                    else:
                        new_parent_id = edit_parent_id_by_label.get(eq_parent_label)
                        try:
                            sb.table("objective").update(
                                {
                                    "title": eq_title.strip(),
                                    "description": eq_desc.strip() or None,
                                    "owner": eq_owner.strip() or None,
                                    "status": eq_status,
                                    "parent_objective_id": new_parent_id,
                                }
                            ).eq("id", qobj["id"]).execute()
                            clear_cache()
                            st.success("Objective saved.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Update failed: {e}")

            obj_krs = (
                key_results[key_results["objective_id"] == qobj["id"]]
                if not key_results.empty
                else pd.DataFrame()
            )

            # --- Archive / Delete the quarterly objective -------------------
            # Cascade scope: KRs of this objective + their init links.
            _qo_kr_ids = set(obj_krs["id"]) if not obj_krs.empty else set()
            _qo_links_count = (
                len(links[links["key_result_id"].isin(_qo_kr_ids)])
                if _qo_kr_ids and not links.empty else 0
            )
            # Defensive: check for any children pointing at this objective
            # (rare for quarterlies, but the same FK constraint applies).
            _qo_children = (
                objectives[objectives["parent_objective_id"] == qobj["id"]]
                if not objectives.empty else pd.DataFrame()
            )
            _qo_child_count = len(_qo_children)
            _qo_blast = (
                f"{len(obj_krs)} KR{'s' if len(obj_krs) != 1 else ''}, "
                f"{_qo_links_count} initiative link{'s' if _qo_links_count != 1 else ''}"
            )
            if _qo_child_count > 0:
                _qo_blast += (
                    f"  ·  blocked by {_qo_child_count} child objective"
                    f"{'s' if _qo_child_count != 1 else ''}"
                )
            _qo_archived = (qobj.get("status") == "archived")

            qc_arch, qc_del, _ = st.columns([1.2, 1.2, 3])
            with qc_arch:
                _qo_arch_key = f"qo_arch_confirm_{qobj['id']}"
                if st.session_state.get(_qo_arch_key):
                    label = "✓ Unarchive" if _qo_archived else "✓ Archive"
                    if st.button(label, key=f"qo_arch_do_{qobj['id']}", use_container_width=True):
                        try:
                            sb.table("objective").update(
                                {"status": "active" if _qo_archived else "archived"}
                            ).eq("id", qobj["id"]).execute()
                            st.session_state.pop(_qo_arch_key, None)
                            clear_cache()
                            st.success(
                                f"Quarterly objective {'unarchived' if _qo_archived else 'archived'}."
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed: {e}")
                else:
                    if st.button(
                        "📦 Unarchive" if _qo_archived else "📦 Archive",
                        key=f"qo_arch_ask_{qobj['id']}",
                        use_container_width=True,
                    ):
                        st.session_state[_qo_arch_key] = True
                        st.rerun()

            with qc_del:
                _qo_del_key = f"qo_del_confirm_{qobj['id']}"
                if _qo_child_count > 0:
                    st.button(
                        "🗑️ Delete (blocked)",
                        key=f"qo_del_blocked_{qobj['id']}",
                        use_container_width=True,
                        disabled=True,
                        help=(
                            f"Can't delete — {_qo_child_count} objective(s) "
                            "still align to this one. Re-parent them first, "
                            "or archive this objective instead."
                        ),
                    )
                elif st.session_state.get(_qo_del_key):
                    if st.button(
                        f"⚠ Really delete? Will lose {_qo_blast}",
                        key=f"qo_del_do_{qobj['id']}",
                        use_container_width=True,
                        type="primary",
                    ):
                        try:
                            sb.table("objective").delete().eq("id", qobj["id"]).execute()
                            st.session_state.pop(_qo_del_key, None)
                            clear_cache()
                            st.success("Quarterly objective deleted.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Delete failed: {e}")
                else:
                    if st.button(
                        "🗑️ Delete",
                        key=f"qo_del_ask_{qobj['id']}",
                        use_container_width=True,
                        help=(
                            "Hard delete — removes this objective, every KR "
                            "under it, and all initiative→KR links. The "
                            "initiatives themselves stay (might become orphans). "
                            "Irreversible. Prefer Archive."
                        ),
                    ):
                        st.session_state[_qo_del_key] = True
                        st.rerun()

            if st.session_state.get(_qo_arch_key) or st.session_state.get(_qo_del_key):
                st.caption(
                    f"⚠ Will affect: **{_qo_blast}**. Click the confirmation "
                    "button to proceed, or anywhere else to cancel."
                )

            # --- Add KR form ---
            with st.expander(
                f"➕ Add a Key Result", expanded=obj_krs.empty
            ):
                with st.form(f"add_kr_{qobj['id']}", clear_on_submit=True):
                    new_kr_title = st.text_input(
                        "Title",
                        placeholder="e.g. Activation rate (team reaches first insight)",
                    )
                    kc1, kc2, kc3, kc4 = st.columns(4)
                    with kc1:
                        new_kr_unit = st.selectbox(
                            "Unit", options=COMMON_UNITS + ["other"], index=0
                        )
                    with kc2:
                        new_kr_start = st.number_input(
                            "Start", value=0.0, step=1.0, format="%.2f"
                        )
                    with kc3:
                        new_kr_target = st.number_input(
                            "Target", value=100.0, step=1.0, format="%.2f"
                        )
                    with kc4:
                        new_kr_current = st.number_input(
                            "Current", value=0.0, step=1.0, format="%.2f"
                        )
                    new_kr_unit_custom = ""
                    if new_kr_unit == "other":
                        new_kr_unit_custom = st.text_input("Custom unit")
                    new_kr_owner = st.text_input(
                        "Owner (optional)",
                        placeholder="e.g. Head of Onboarding",
                        help="Who is responsible for moving this KR?",
                    )
                    prev = kr_progress(new_kr_start, new_kr_target, new_kr_current)
                    st.caption(
                        f"Preview: {grade_color(prev)} **{prev:.0%}** "
                        f"({new_kr_start} → {new_kr_current} → {new_kr_target})"
                    )
                    submitted = st.form_submit_button("➕ Add KR", type="primary")
                    if submitted:
                        if not new_kr_title.strip():
                            st.error("Title is required.")
                        elif new_kr_unit == "other" and not new_kr_unit_custom.strip():
                            st.error("Specify a custom unit.")
                        else:
                            unit_value = (
                                new_kr_unit_custom.strip()
                                if new_kr_unit == "other"
                                else new_kr_unit
                            )
                            try:
                                sb.table("key_result").insert(
                                    {
                                        "objective_id": qobj["id"],
                                        "title": new_kr_title.strip(),
                                        "metric_unit": unit_value,
                                        "start_value": new_kr_start,
                                        "target_value": new_kr_target,
                                        "current_value": new_kr_current,
                                        "owner": new_kr_owner.strip() or None,
                                    }
                                ).execute()
                                clear_cache()
                                st.success(f"Added KR **{new_kr_title}**.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Insert failed: {e}")

            # --- Existing KRs with nested initiatives + business cases ---
            if obj_krs.empty:
                st.info("No KRs yet — add the first one above.")
            else:
                for _, kr in obj_krs.iterrows():
                    grade = kr_progress(
                        kr.get("start_value"),
                        kr.get("target_value"),
                        kr.get("current_value"),
                    )
                    unit = kr.get("metric_unit") or ""
                    kr_header = (
                        f"{grade_color(grade)} **{kr['title']}** — "
                        f"{kr.get('current_value')} / {kr.get('target_value')} {unit} "
                        f"({grade:.0%})"
                    )

                    with st.expander(kr_header, expanded=False):
                        # KR edit form
                        with st.form(f"edit_kr_{kr['id']}"):
                            ec1, ec2, ec3, ec4, ec5 = st.columns([3, 1, 1, 1, 1])
                            with ec1:
                                ek_title = st.text_input("Title", value=kr["title"])
                            with ec2:
                                cur_unit = kr.get("metric_unit") or "%"
                                unit_opts = COMMON_UNITS + ["other"]
                                unit_idx = (
                                    unit_opts.index(cur_unit)
                                    if cur_unit in COMMON_UNITS
                                    else len(unit_opts) - 1
                                )
                                ek_unit = st.selectbox(
                                    "Unit", options=unit_opts, index=unit_idx
                                )
                            with ec3:
                                ek_start = st.number_input(
                                    "Start",
                                    value=float(kr.get("start_value") or 0),
                                    step=1.0,
                                    format="%.2f",
                                )
                            with ec4:
                                ek_target = st.number_input(
                                    "Target",
                                    value=float(kr.get("target_value") or 100),
                                    step=1.0,
                                    format="%.2f",
                                )
                            with ec5:
                                ek_current = st.number_input(
                                    "Current",
                                    value=float(kr.get("current_value") or 0),
                                    step=1.0,
                                    format="%.2f",
                                )
                            ek_unit_custom = ""
                            if ek_unit == "other":
                                ek_unit_custom = st.text_input(
                                    "Custom unit",
                                    value=(cur_unit if cur_unit not in COMMON_UNITS else ""),
                                )
                            cur_owner = kr.get("owner")
                            ek_owner = st.text_input(
                                "Owner",
                                value=cur_owner if isinstance(cur_owner, str) else "",
                                placeholder="e.g. Head of Onboarding",
                                key=f"owner_{kr['id']}",
                            )
                            prev = kr_progress(ek_start, ek_target, ek_current)
                            st.caption(
                                f"Preview: {grade_color(prev)} **{prev:.0%}** "
                                f"({ek_start} → {ek_current} → {ek_target})"
                            )
                            save_kr = st.form_submit_button("💾 Save KR")
                            if save_kr:
                                if not ek_title.strip():
                                    st.error("Title is required.")
                                elif ek_unit == "other" and not ek_unit_custom.strip():
                                    st.error("Specify a custom unit.")
                                else:
                                    unit_value = (
                                        ek_unit_custom.strip()
                                        if ek_unit == "other"
                                        else ek_unit
                                    )
                                    try:
                                        sb.table("key_result").update(
                                            {
                                                "title": ek_title.strip(),
                                                "metric_unit": unit_value,
                                                "start_value": ek_start,
                                                "target_value": ek_target,
                                                "current_value": ek_current,
                                                "owner": ek_owner.strip() or None,
                                            }
                                        ).eq("id", kr["id"]).execute()
                                        clear_cache()
                                        st.success("KR saved.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Update failed: {e}")

                        # ---- Initiatives moving this KR ----
                        st.markdown("**Initiatives moving this KR**")

                        kr_links = (
                            links[links["key_result_id"] == kr["id"]]
                            if not links.empty
                            else pd.DataFrame()
                        )

                        # ---- Predicted total impact vs gap diagnostic ----
                        # Shows whether the bets attached to this KR add up to
                        # closing the gap between current and target. The most
                        # useful planning signal we have: under-prediction means
                        # the plan, on paper, isn't even trying to hit target.
                        _kr_current = kr.get("current_value") or 0
                        _kr_target = kr.get("target_value") or 0
                        _kr_gap = _kr_target - _kr_current

                        if not kr_links.empty and _kr_gap != 0:
                            # Sum predicted impact, treating missing values as 0 but
                            # counting how many links lack a prediction.
                            _predictions = kr_links["predicted_kr_impact"].dropna()
                            _predicted_total = float(_predictions.sum()) if not _predictions.empty else 0.0
                            _missing_count = len(kr_links) - len(_predictions)

                            # Coverage = how much of the gap is "promised" by predictions.
                            # If gap is negative (target < current, e.g. reducing churn), use abs.
                            _gap_abs = abs(_kr_gap)
                            _coverage = (
                                abs(_predicted_total) / _gap_abs if _gap_abs > 0 else 0
                            )

                            # Pick a status color: green ≥ 100% covered, yellow 50-99%, red <50%
                            if _coverage >= 1.0:
                                _diag_dot = "🟢"
                            elif _coverage >= 0.5:
                                _diag_dot = "🟡"
                            else:
                                _diag_dot = "🔴"

                            _missing_note = (
                                f" &nbsp;·&nbsp; *{_missing_count} of {len(kr_links)} "
                                f"initiative{'s' if len(kr_links) != 1 else ''} have no prediction yet*"
                                if _missing_count > 0 else ""
                            )

                            st.markdown(
                                f"<div style='background:#F9FAFB;border-left:3px solid #D1D5DB;"
                                f"padding:6px 12px;margin-bottom:8px;font-size:0.9em'>"
                                f"{_diag_dot} <b>Predicted total impact:</b> "
                                f"{_predicted_total:+g} {unit} &nbsp;·&nbsp; "
                                f"<b>Gap to target:</b> {_kr_gap:+g} {unit} &nbsp;·&nbsp; "
                                f"<b>{_coverage:.0%} of gap covered</b>"
                                f"{_missing_note}"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                        if kr_links.empty:
                            st.info("No initiatives attached yet — propose one below.")
                        else:
                            for _, link in kr_links.iterrows():
                                init_id = link["initiative_id"]
                                init = init_by_id.get(init_id)
                                if not init:
                                    continue
                                bc = bc_by_init.get(init_id)
                                init_status_icon = {
                                    "proposed": "💭",
                                    "active": "🟢",
                                    "done": "✅",
                                    "killed": "🪦",
                                }.get(init.get("status"), "")
                                roi_str = "—"
                                if (
                                    bc
                                    and bc.get("predicted_cost")
                                    and bc.get("predicted_value")
                                ):
                                    if bc["predicted_cost"] > 0:
                                        roi_str = (
                                            f"{bc['predicted_value']/bc['predicted_cost']:.1f}x"
                                        )
                                init_header = (
                                    f"{init_status_icon} **{init['title']}**  ·  "
                                    f"Delivery: {init.get('progress_pct') or 0}%  ·  "
                                    f"Impact: {link.get('predicted_kr_impact') or '—'}  ·  "
                                    f"ROI: {roi_str}"
                                )
                                with st.expander(init_header, expanded=False):
                                    # --- Unlink action (top of card) ---
                                    # Remove the join row between this initiative
                                    # and this KR without deleting the initiative
                                    # itself. The button uses st.session_state to
                                    # require a confirmation click.
                                    unlink_confirm_key = f"unlink_confirm_{init_id}_{kr['id']}"
                                    # How many KRs is this initiative linked to in total?
                                    _init_total_links = (
                                        len(links[links["initiative_id"] == init_id])
                                        if not links.empty else 0
                                    )
                                    is_last_link = _init_total_links <= 1
                                    uc1, uc2 = st.columns([4, 1])
                                    with uc2:
                                        if st.session_state.get(unlink_confirm_key):
                                            # Confirmation visible — show "really?"
                                            confirm_label = (
                                                "⚠ Really unlink? (last link!)"
                                                if is_last_link else "✓ Confirm unlink"
                                            )
                                            if st.button(
                                                confirm_label,
                                                key=f"unlink_do_{init_id}_{kr['id']}",
                                                use_container_width=True,
                                            ):
                                                try:
                                                    sb.table("initiative_key_result").delete().eq(
                                                        "initiative_id", init_id
                                                    ).eq("key_result_id", kr["id"]).execute()
                                                    st.session_state.pop(unlink_confirm_key, None)
                                                    clear_cache()
                                                    st.success(
                                                        f"Unlinked **{init['title']}** from this KR. "
                                                        f"{'(Initiative kept; relink later if needed.)' if not is_last_link else '(This was its last link — initiative still exists, now orphan.)'}"
                                                    )
                                                    st.rerun()
                                                except Exception as e:
                                                    st.error(f"Unlink failed: {e}")
                                        else:
                                            if st.button(
                                                "🔗 Unlink from this KR",
                                                key=f"unlink_ask_{init_id}_{kr['id']}",
                                                use_container_width=True,
                                                help=(
                                                    "Remove this initiative from this KR's "
                                                    "linked initiatives. The initiative itself "
                                                    "stays — only the link is removed."
                                                ),
                                            ):
                                                st.session_state[unlink_confirm_key] = True
                                                st.rerun()
                                    with uc1:
                                        if is_last_link and st.session_state.get(unlink_confirm_key):
                                            st.caption(
                                                "⚠ This is the *only* KR this initiative is "
                                                "linked to. Unlinking will leave the initiative "
                                                "orphaned (still in the database, but moving "
                                                "nothing). Consider deleting it instead via SQL "
                                                "if you don't need it."
                                            )

                                    # Initiative edit
                                    with st.form(f"edit_init_{init_id}_{kr['id']}"):
                                        ic1, ic2 = st.columns([3, 1])
                                        with ic1:
                                            ei_title = st.text_input(
                                                "Title", value=init["title"]
                                            )
                                        with ic2:
                                            ei_owner = st.text_input(
                                                "Owner", value=init.get("owner") or ""
                                            )
                                        ic3, ic4, ic5, ic6 = st.columns(4)
                                        with ic3:
                                            ei_status = st.selectbox(
                                                "Status",
                                                options=INIT_STATUSES,
                                                index=INIT_STATUSES.index(
                                                    init.get("status", "proposed")
                                                )
                                                if init.get("status") in INIT_STATUSES
                                                else 0,
                                            )
                                        with ic4:
                                            cur_ms = init.get("milestone_status")
                                            ms_opts = [""] + MILESTONE_STATUSES
                                            ei_ms = st.selectbox(
                                                "Milestone",
                                                options=ms_opts,
                                                index=ms_opts.index(cur_ms)
                                                if cur_ms in ms_opts
                                                else 0,
                                            )
                                        with ic5:
                                            cur_effort = init.get("effort_estimate") or ""
                                            ei_effort = st.selectbox(
                                                "Effort",
                                                options=EFFORT_SIZES,
                                                index=EFFORT_SIZES.index(cur_effort)
                                                if cur_effort in EFFORT_SIZES
                                                else 0,
                                            )
                                        with ic6:
                                            ei_progress = st.number_input(
                                                "Delivery %",
                                                min_value=0.0,
                                                max_value=100.0,
                                                value=float(init.get("progress_pct") or 0),
                                                step=5.0,
                                            )
                                        ei_desc = st.text_area(
                                            "Description",
                                            value=init.get("description") or "",
                                            height=80,
                                        )
                                        st.markdown(
                                            "**Predicted impact on _this_ KR**"
                                        )
                                        st.caption(
                                            f"How much will this initiative move the KR's "
                                            f"current value? In its native units ({unit or 'as defined'}), "
                                            f"not a weight."
                                        )
                                        ie1, ie2 = st.columns(2)
                                        with ie1:
                                            ei_predicted = st.number_input(
                                                f"Predicted Δ to current value ({unit})",
                                                value=float(
                                                    link.get("predicted_kr_impact") or 0
                                                ),
                                                step=1.0,
                                                format="%.2f",
                                                help=(
                                                    f"Predicted absolute change in the KR's "
                                                    f"value (same units as the KR: {unit or 'see KR'}). "
                                                    f"NOT a weight or percentage."
                                                ),
                                            )
                                            # Live preview: show the math
                                            kr_current = kr.get("current_value") or 0
                                            kr_target = kr.get("target_value") or 0
                                            projected = kr_current + ei_predicted
                                            st.caption(
                                                f"→ moves KR from **{kr_current} {unit}** "
                                                f"to **{projected:g} {unit}** "
                                                f"(target {kr_target} {unit})"
                                            )
                                        with ie2:
                                            ei_actual = st.number_input(
                                                f"Actual Δ measured ({unit})",
                                                value=float(
                                                    link.get("actual_kr_impact") or 0
                                                ),
                                                step=1.0,
                                                format="%.2f",
                                                help=(
                                                    "After the initiative runs, the actual "
                                                    "change you measured. Used to compare "
                                                    "predicted vs reality."
                                                ),
                                            )
                                        save_init = st.form_submit_button(
                                            "💾 Save initiative"
                                        )
                                        if save_init:
                                            if not ei_title.strip():
                                                st.error("Title is required.")
                                            else:
                                                try:
                                                    sb.table("initiative").update(
                                                        {
                                                            "title": ei_title.strip(),
                                                            "owner": ei_owner.strip() or None,
                                                            "status": ei_status,
                                                            "milestone_status": ei_ms or None,
                                                            "effort_estimate": ei_effort or None,
                                                            "progress_pct": ei_progress,
                                                            "description": ei_desc.strip() or None,
                                                        }
                                                    ).eq("id", init_id).execute()
                                                    sb.table("initiative_key_result").update(
                                                        {
                                                            "predicted_kr_impact": ei_predicted,
                                                            "actual_kr_impact": ei_actual if ei_actual != 0 else None,
                                                        }
                                                    ).eq("initiative_id", init_id).eq(
                                                        "key_result_id", kr["id"]
                                                    ).execute()
                                                    clear_cache()
                                                    st.success("Initiative saved.")
                                                    st.rerun()
                                                except Exception as e:
                                                    st.error(f"Update failed: {e}")

                                    # Business case
                                    st.markdown("**Business case**")
                                    if bc:
                                        with st.form(f"edit_bc_{bc['id']}_{kr['id']}"):
                                            bc_summary = st.text_area(
                                                "Summary",
                                                value=bc.get("summary") or "",
                                                height=60,
                                            )
                                            bcc1, bcc2 = st.columns(2)
                                            with bcc1:
                                                bc_metric = st.text_input(
                                                    "Target metric",
                                                    value=bc.get("target_metric") or "",
                                                )
                                            with bcc2:
                                                bc_unit_val = st.text_input(
                                                    "Metric unit",
                                                    value=bc.get("target_metric_unit") or "",
                                                )
                                            bcc3, bcc4, bcc5, bcc6 = st.columns(4)
                                            with bcc3:
                                                bc_pv = st.number_input(
                                                    "Predicted value",
                                                    value=float(bc.get("predicted_value") or 0),
                                                    step=1000.0,
                                                )
                                            with bcc4:
                                                bc_pc = st.number_input(
                                                    "Predicted cost",
                                                    value=float(bc.get("predicted_cost") or 0),
                                                    step=1000.0,
                                                )
                                            with bcc5:
                                                bc_av = st.number_input(
                                                    "Actual value",
                                                    value=float(bc.get("actual_value") or 0),
                                                    step=1000.0,
                                                )
                                            with bcc6:
                                                bc_ac = st.number_input(
                                                    "Actual cost",
                                                    value=float(bc.get("actual_cost") or 0),
                                                    step=1000.0,
                                                )
                                            cur_d = bc.get("decision") or "pending"
                                            bc_decision = st.selectbox(
                                                "Decision",
                                                options=DECISIONS,
                                                index=DECISIONS.index(cur_d)
                                                if cur_d in DECISIONS
                                                else 0,
                                            )
                                            planned_roi = (
                                                f"{bc_pv/bc_pc:.1f}x" if bc_pc > 0 else "—"
                                            )
                                            realized_roi = (
                                                f"{bc_av/bc_ac:.1f}x" if bc_ac > 0 else "—"
                                            )
                                            st.caption(
                                                f"Planned ROI: **{planned_roi}**  ·  "
                                                f"Realized ROI: **{realized_roi}**"
                                            )
                                            save_bc = st.form_submit_button(
                                                "💾 Save business case"
                                            )
                                            if save_bc:
                                                try:
                                                    sb.table("business_case").update(
                                                        {
                                                            "summary": bc_summary.strip() or None,
                                                            "target_metric": bc_metric.strip() or None,
                                                            "target_metric_unit": bc_unit_val.strip() or None,
                                                            "predicted_value": bc_pv if bc_pv > 0 else None,
                                                            "predicted_cost": bc_pc if bc_pc > 0 else None,
                                                            "actual_value": bc_av if bc_av > 0 else None,
                                                            "actual_cost": bc_ac if bc_ac > 0 else None,
                                                            "decision": bc_decision,
                                                        }
                                                    ).eq("id", bc["id"]).execute()
                                                    clear_cache()
                                                    st.success("Business case saved.")
                                                    st.rerun()
                                                except Exception as e:
                                                    st.error(f"Update failed: {e}")
                                    else:
                                        st.caption(
                                            "_No business case attached. This bet isn't "
                                            "justified with predicted value vs cost yet._"
                                        )
                                        with st.form(f"add_bc_{init_id}_{kr['id']}"):
                                            bcq1, bcq2, bcq3 = st.columns(3)
                                            with bcq1:
                                                qbc_metric = st.text_input(
                                                    "Target metric"
                                                )
                                            with bcq2:
                                                qbc_pv = st.number_input(
                                                    "Predicted value", value=0.0, step=1000.0
                                                )
                                            with bcq3:
                                                qbc_pc = st.number_input(
                                                    "Predicted cost", value=0.0, step=1000.0
                                                )
                                            qbc_summary = st.text_input(
                                                "Summary (optional)"
                                            )
                                            add_bc = st.form_submit_button(
                                                "➕ Attach business case"
                                            )
                                            if add_bc:
                                                if qbc_pv <= 0 or qbc_pc <= 0:
                                                    st.error(
                                                        "Need both predicted value and cost."
                                                    )
                                                else:
                                                    try:
                                                        sb.table("business_case").insert(
                                                            {
                                                                "initiative_id": init_id,
                                                                "summary": qbc_summary.strip() or None,
                                                                "target_metric": qbc_metric.strip() or None,
                                                                "predicted_value": qbc_pv,
                                                                "predicted_cost": qbc_pc,
                                                                "decision": "pending",
                                                            }
                                                        ).execute()
                                                        clear_cache()
                                                        st.success("Business case attached.")
                                                        st.rerun()
                                                    except Exception as e:
                                                        st.error(f"Insert failed: {e}")

                        # --- Link an existing initiative to this KR ---
                        # For when an initiative already exists (created from
                        # another KR) and you realize it also moves this one.
                        # Avoids duplicate initiatives and supports many-to-many.
                        _already_linked_init_ids = (
                            set(kr_links["initiative_id"].tolist())
                            if not kr_links.empty else set()
                        )
                        _linkable_initiatives = (
                            initiatives[~initiatives["id"].isin(_already_linked_init_ids)]
                            if not initiatives.empty else pd.DataFrame()
                        )
                        if not _linkable_initiatives.empty:
                            with st.expander(
                                "🔗 Link an existing initiative to this KR",
                                expanded=False,
                            ):
                                with st.form(f"link_existing_init_{kr['id']}"):
                                    _link_options = []
                                    _link_id_by_label = {}
                                    for _, _li in _linkable_initiatives.sort_values("title").iterrows():
                                        _li_label = f"{_li['title']}"
                                        _li_status = _li.get("status")
                                        if _li_status:
                                            _li_label += f"  ·  {_li_status}"
                                        _link_options.append(_li_label)
                                        _link_id_by_label[_li_label] = _li["id"]
                                    le_init_label = st.selectbox(
                                        "Initiative to link",
                                        options=_link_options,
                                        help=(
                                            "Pick an existing initiative that should also move "
                                            "this KR. Only initiatives not already linked to this "
                                            "KR are shown."
                                        ),
                                    )
                                    le_predicted_impact = st.number_input(
                                        f"Predicted Δ to this KR ({unit})",
                                        value=0.0,
                                        step=1.0,
                                        help=(
                                            f"Predicted absolute change in this KR's value "
                                            f"(units: {unit or 'see KR'}) from this specific "
                                            f"initiative."
                                        ),
                                    )
                                    # Live preview
                                    _le_kr_current = kr.get("current_value") or 0
                                    _le_kr_target = kr.get("target_value") or 0
                                    _le_projected = _le_kr_current + le_predicted_impact
                                    st.caption(
                                        f"→ would move KR from **{_le_kr_current} {unit}** "
                                        f"to **{_le_projected:g} {unit}** "
                                        f"(target {_le_kr_target} {unit})"
                                    )
                                    link_submitted = st.form_submit_button(
                                        "🔗 Link initiative", type="primary"
                                    )
                                    if link_submitted:
                                        _le_init_id = _link_id_by_label.get(le_init_label)
                                        if not _le_init_id:
                                            st.error("Pick an initiative to link.")
                                        else:
                                            try:
                                                sb.table("initiative_key_result").insert(
                                                    {
                                                        "initiative_id": _le_init_id,
                                                        "key_result_id": kr["id"],
                                                        "predicted_kr_impact": (
                                                            le_predicted_impact
                                                            if le_predicted_impact != 0
                                                            else None
                                                        ),
                                                    }
                                                ).execute()
                                                clear_cache()
                                                st.success(
                                                    f"Linked **{le_init_label.split('  ·  ')[0]}** "
                                                    f"to this KR."
                                                )
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"Link failed: {e}")

                        # --- Propose a new initiative against this KR ---
                        with st.expander(
                            "➕ Propose a new initiative against this KR", expanded=False
                        ):
                            with st.form(f"add_init_{kr['id']}", clear_on_submit=True):
                                ni_title = st.text_input(
                                    "Title",
                                    placeholder="e.g. 'Guided onboarding flow with sample dataset'",
                                )
                                nic1, nic2, nic3 = st.columns(3)
                                with nic1:
                                    ni_owner = st.text_input("Owner")
                                with nic2:
                                    ni_effort = st.selectbox(
                                        "Effort", options=EFFORT_SIZES, index=0
                                    )
                                with nic3:
                                    ni_predicted_impact = st.number_input(
                                        f"Predicted Δ to this KR ({unit})",
                                        value=0.0,
                                        step=1.0,
                                        help=(
                                            f"Predicted absolute change in the KR's "
                                            f"value (same units as the KR: {unit or 'see KR'}). "
                                            f"NOT a weight or percentage."
                                        ),
                                    )
                                # Live preview of the math: what value will this KR
                                # land at if this prediction is correct?
                                _kr_current = kr.get("current_value") or 0
                                _kr_target = kr.get("target_value") or 0
                                _projected = _kr_current + ni_predicted_impact
                                st.caption(
                                    f"→ would move KR from **{_kr_current} {unit}** "
                                    f"to **{_projected:g} {unit}** "
                                    f"(target {_kr_target} {unit})"
                                )
                                ni_desc = st.text_area("Description", height=80)

                                # ---- Multi-KR linking (Option A) ----
                                # Pre-compute "other KRs under the same quarterly
                                # objective" so the user can attach this same
                                # initiative to multiple KRs at creation time.
                                # Cross-objective linking happens via the
                                # "Link existing initiative" flow on another KR's
                                # card after creation.
                                _sibling_krs = obj_krs[obj_krs["id"] != kr["id"]] if not obj_krs.empty else pd.DataFrame()
                                _sibling_label_to_id = {}
                                if not _sibling_krs.empty:
                                    sib_options = []
                                    for _, sk in _sibling_krs.iterrows():
                                        sk_unit = sk.get("metric_unit") or ""
                                        sk_label = f"{sk['title']} ({sk_unit})"
                                        sib_options.append(sk_label)
                                        _sibling_label_to_id[sk_label] = sk["id"]
                                    ni_extra_kr_labels = st.multiselect(
                                        "Also link this initiative to other KRs in the same objective",
                                        options=sib_options,
                                        default=[],
                                        help=(
                                            "Pick zero or more sibling KRs this initiative also "
                                            "moves. The primary KR (this one) keeps the predicted "
                                            "impact you entered above. For the extra KRs, set their "
                                            "predicted impact afterward by editing the linked "
                                            "initiative from each KR's card."
                                        ),
                                    )
                                else:
                                    ni_extra_kr_labels = []

                                st.markdown("**Optional business case (recommended)**")
                                bc1, bc2, bc3 = st.columns(3)
                                with bc1:
                                    ni_metric = st.text_input("Target metric")
                                with bc2:
                                    ni_pv = st.number_input(
                                        "Predicted value", value=0.0, step=1000.0
                                    )
                                with bc3:
                                    ni_pc = st.number_input(
                                        "Predicted cost", value=0.0, step=1000.0
                                    )
                                ni_bc_summary = st.text_input(
                                    "Business case summary"
                                )
                                add_initiative = st.form_submit_button(
                                    "➕ Propose initiative", type="primary"
                                )
                                if add_initiative:
                                    if not ni_title.strip():
                                        st.error("Title is required.")
                                    else:
                                        try:
                                            init_result = sb.table("initiative").insert(
                                                {
                                                    "title": ni_title.strip(),
                                                    "description": ni_desc.strip() or None,
                                                    "owner": ni_owner.strip() or None,
                                                    "status": "proposed",
                                                    "effort_estimate": ni_effort or None,
                                                    "progress_pct": 0,
                                                }
                                            ).execute()
                                            new_init_id = init_result.data[0]["id"]
                                            sb.table("initiative_key_result").insert(
                                                {
                                                    "initiative_id": new_init_id,
                                                    "key_result_id": kr["id"],
                                                    "predicted_kr_impact": (
                                                        ni_predicted_impact
                                                        if ni_predicted_impact != 0
                                                        else None
                                                    ),
                                                }
                                            ).execute()
                                            # Also link to any additional sibling KRs
                                            # selected in the multiselect. Their
                                            # predicted_kr_impact is intentionally
                                            # left None — to be set later via the
                                            # per-KR edit form on each KR.
                                            extra_linked = 0
                                            for _extra_label in ni_extra_kr_labels:
                                                _extra_kr_id = _sibling_label_to_id.get(_extra_label)
                                                if _extra_kr_id:
                                                    try:
                                                        sb.table("initiative_key_result").insert(
                                                            {
                                                                "initiative_id": new_init_id,
                                                                "key_result_id": _extra_kr_id,
                                                            }
                                                        ).execute()
                                                        extra_linked += 1
                                                    except Exception as link_err:
                                                        st.warning(
                                                            f"Couldn't link to '{_extra_label}': {link_err}"
                                                        )
                                            if ni_pv > 0 and ni_pc > 0:
                                                sb.table("business_case").insert(
                                                    {
                                                        "initiative_id": new_init_id,
                                                        "summary": ni_bc_summary.strip() or None,
                                                        "target_metric": ni_metric.strip() or None,
                                                        "predicted_value": ni_pv,
                                                        "predicted_cost": ni_pc,
                                                        "decision": "pending",
                                                    }
                                                ).execute()
                                            clear_cache()
                                            roi_msg = (
                                                f" (ROI {ni_pv/ni_pc:.1f}x)"
                                                if ni_pv > 0 and ni_pc > 0
                                                else ""
                                            )
                                            extra_msg = (
                                                f" Linked to {extra_linked} additional KR"
                                                f"{'s' if extra_linked != 1 else ''}."
                                                if extra_linked > 0 else ""
                                            )
                                            st.success(
                                                f"Proposed **{ni_title}**{roi_msg}.{extra_msg}"
                                            )
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Couldn't propose initiative: {e}")


# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.divider()
st.caption(
    "KRs are the outcomes; initiatives are the bets. An initiative isn't "
    "'done' because it shipped — it's done when its predicted KR impact shows "
    "up in the Actual column."
)

"""
Annual Strategy & Objectives — the yearly planning workspace.

The annual layer of dual-horizon planning. Leadership opens this once a
quarter to refresh; quarterly planning happens on a separate page.

Scope (deliberately small):
  * One strategy per org unit per fiscal year (title + multi-paragraph narrative)
  * 3-5 yearly objectives per org unit per fiscal year
  * Each yearly objective may have a few aspirational KRs (loosely tracked,
    updated quarterly, not weekly)
  * NO initiatives at this level — initiatives are quarterly bets

How yearly vs quarterly are distinguished in the data:
  We use the `period` field convention. Yearly objectives have
  period = "FY{year}" (e.g. "FY2026"). Quarterly objectives use "Q3-2026".
  No schema change; just a textual convention enforced by the UI.
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
    }


def clear_cache():
    load_all.clear()


# -----------------------------------------------------------------------------
# Constants & helpers
# -----------------------------------------------------------------------------
OBJ_STATUSES = ["active", "closed", "archived"]
COMMON_UNITS = ["%", "count", "USD", "min", "hours", "days", "score", "NPS"]

# KR indicator type — lightweight tag for leading vs lagging vs standalone.
# See plan_quarter.py for the full rationale.
INDICATOR_TYPES = ["", "lagging", "leading"]
INDICATOR_LABELS = {
    "": "Standalone (no type)",
    "lagging": "🎯 Lagging",
    "leading": "📡 Leading",
}


def fy_period(year: int) -> str:
    return f"FY{year}"


def is_yearly(period: str) -> bool:
    return bool(period) and period.startswith("FY")


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


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("📜 Annual Strategy & Objectives")
st.caption(
    "The yearly layer — strategy and big-picture objectives that don't change "
    "every quarter. Quarterly OKRs and initiatives live on **Plan a Quarter**."
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

if org_units.empty:
    st.warning(
        "No org units yet. Add at least one on **Manage → Org Units** before "
        "starting annual planning."
    )
    st.stop()


# -----------------------------------------------------------------------------
# Pickers: org unit + fiscal year
# -----------------------------------------------------------------------------
ou_name_by_id = org_units.set_index("id")["name"].to_dict()
ou_id_by_name = {v: k for k, v in ou_name_by_id.items()}

# Sort org units company → segment → team, then by name (used downstream for
# stable ordering of the "All strategies" overview card).
ou_sorted = org_units.copy()
level_order = {"company": 0, "segment": 1, "team": 2}
ou_sorted["__order"] = ou_sorted["level"].map(level_order).fillna(99)
ou_sorted = ou_sorted.sort_values(["__order", "name"])

# Build the indented tree labels for the picker. Walk parent_unit_id from the
# roots downward so children appear right under their parents with a ↳ prefix
# per depth level — same convention as Org Units, Manage Key Results, etc.
children_by_parent: dict = {}
for _, row in org_units.iterrows():
    pid = row["parent_unit_id"]
    # Coerce pandas NaN to None so root rows (null parent) group consistently.
    if pid != pid:  # NaN != NaN is the only value where this is true
        pid = None
    children_by_parent.setdefault(pid, []).append(row)

tree_labels: list[str] = []
tree_label_to_id: dict = {}


def _walk_org_tree(parent_id, depth: int):
    # Stable child order: company → segment → team, then by name
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

# Prepend a meta-option that bypasses the family scoping (shows every strategy
# across the company, like the original behavior).
ALL_ORGS_LABEL = "All Organizations"
tree_labels = [ALL_ORGS_LABEL] + tree_labels

# Default fiscal year: prefer the current year, else most recent used.
import datetime
this_year = datetime.date.today().year
known_years = set()
if not strategies.empty and "fiscal_year" in strategies.columns:
    known_years.update(int(y) for y in strategies["fiscal_year"].dropna().tolist())
years_for_dropdown = sorted(known_years | {this_year, this_year + 1}, reverse=True)

pc1, pc2 = st.columns([2, 1])
with pc1:
    # Default to sticky scope org if set. Note tree_labels here has
    # "All Organizations" at index 0, then the unit tree.
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
            "Pick the org unit whose annual plan you want to set or review. "
            "Indented entries (↳) sit under the unit above them. "
            "Pick 'All Organizations' to see every strategy across the company. "
            "Your selection persists across pages."
        ),
    )
with pc2:
    # Derive default year from a sticky period if one's set, otherwise current year.
    _saved_period = st.session_state.get("scope_period")
    _saved_year = None
    if isinstance(_saved_period, str):
        # period_sort_key handles both 'FY2026' and 'Q3-2026' formats
        if _saved_period.startswith("FY"):
            try:
                _saved_year = int(_saved_period[2:])
            except ValueError:
                _saved_year = None
        else:
            try:
                _saved_year = int(_saved_period.split("-")[1])
            except (ValueError, IndexError):
                _saved_year = None
    if _saved_year is not None and _saved_year in years_for_dropdown:
        default_year_idx = years_for_dropdown.index(_saved_year)
    elif this_year in years_for_dropdown:
        default_year_idx = years_for_dropdown.index(this_year)
    else:
        default_year_idx = 0
    selected_year = st.selectbox(
        "**Fiscal year**",
        options=years_for_dropdown,
        index=default_year_idx,
    )

# selected_ou_id is None when "All Organizations" is picked.
if selected_ou_label == ALL_ORGS_LABEL:
    selected_ou_id = None
    selected_ou_name = ALL_ORGS_LABEL
else:
    selected_ou_id = tree_label_to_id[selected_ou_label]
    selected_ou_name = ou_name_by_id[selected_ou_id]

# Persist scope (only org+name; year stays per-Annual since other pages think
# in terms of period, not year, and writing back would muddle scope_period).
if selected_ou_id is not None:
    st.session_state["scope_org_id"] = selected_ou_id
    st.session_state["scope_org_name"] = selected_ou_name


# -----------------------------------------------------------------------------
# Compute the "family" of org units in scope for the overview card.
# Family = self + ancestors (up the chain) + descendants (down the tree).
# This is the same cascade-vertical-slice idea used on Plan a Quarter's
# annual context card and on the Flow page's filter logic. Consistent.
#
# When "All Organizations" is picked, the family is every unit.
# -----------------------------------------------------------------------------
# Re-walk parent_unit_id (NaN-safe) so we have parent lookup independent of
# the tree builder above.
parent_by_ou_id: dict = {}
for _, row in org_units.iterrows():
    pid = row.get("parent_unit_id")
    if pid != pid:  # NaN check
        pid = None
    parent_by_ou_id[row["id"]] = pid


def _ancestors_of(ou_id):
    chain = set()
    visited = set()
    cur = parent_by_ou_id.get(ou_id)
    while cur is not None and cur not in visited:
        chain.add(cur)
        visited.add(cur)
        cur = parent_by_ou_id.get(cur)
    return chain


def _descendants_of(ou_id):
    out = set()
    # Walk children via the children_by_parent map built earlier.
    stack = list(children_by_parent.get(ou_id, []))
    visited = set()
    while stack:
        row = stack.pop()
        rid = row["id"]
        if rid in visited:
            continue
        visited.add(rid)
        out.add(rid)
        stack.extend(children_by_parent.get(rid, []))
    return out


if selected_ou_id is None:
    family_ids = set(org_units["id"].tolist())  # All Organizations
else:
    family_ids = {selected_ou_id} | _ancestors_of(selected_ou_id) | _descendants_of(selected_ou_id)


# -----------------------------------------------------------------------------
# ALL STRATEGIES — read-only overview card
# -----------------------------------------------------------------------------
# Scoped to the chosen org unit's "family" (self + ancestors + descendants),
# or to every unit when "All Organizations" is picked. Read-only by design:
# this is orientation, not work. The focused editor below is where actual
# changes happen.
with st.container(border=True):
    scope_label = (
        "all org units"
        if selected_ou_id is None
        else f"{selected_ou_name} family"
    )
    st.markdown(f"**🗺️ All strategies · FY{selected_year}** &nbsp;·&nbsp; *{scope_label}*")

    if strategies.empty:
        st.caption("No strategies defined yet — use the editor below to create the first one.")
    else:
        year_strategies = strategies[
            (strategies["fiscal_year"] == selected_year)
            & (strategies["org_unit_id"].isin(family_ids))
        ]
        if year_strategies.empty:
            if selected_ou_id is None:
                st.caption(
                    f"No strategies defined for FY{selected_year}. "
                    "Use the editor below to create one, or change the fiscal year."
                )
            else:
                st.caption(
                    f"No strategies defined for the {selected_ou_name} family in "
                    f"FY{selected_year}. Use the editor below to create one, "
                    "switch to 'All Organizations' to see everything, or change "
                    "the fiscal year."
                )
        else:
            # Order strategies by org-unit tree position (company → segments → teams)
            ou_position = {
                row["id"]: i for i, (_, row) in enumerate(ou_sorted.iterrows())
            }
            year_strategies_sorted = year_strategies.copy()
            year_strategies_sorted["__pos"] = (
                year_strategies_sorted["org_unit_id"].map(ou_position).fillna(999)
            )
            year_strategies_sorted = year_strategies_sorted.sort_values("__pos")

            for _, s in year_strategies_sorted.iterrows():
                s_ou = ou_name_by_id.get(s["org_unit_id"], "?")
                # Lookup the level of this org unit so we can prefix with indentation
                ou_row = org_units[org_units["id"] == s["org_unit_id"]]
                ou_level = ou_row.iloc[0]["level"] if not ou_row.empty else "company"
                indent = {"company": "", "segment": "↳ ", "team": "↳ ↳ "}.get(ou_level, "")

                # Mark whichever one matches the current picker so it's easy to find
                marker = "  ←  *currently editing*" if s["org_unit_id"] == selected_ou_id else ""

                st.markdown(f"{indent}**{s_ou}** — {s['title']}{marker}")
                desc = s.get("description")
                # pandas loads null text columns as NaN (a float), which is
                # truthy in Python — so we have to check for a real string,
                # not just rely on `if desc`.
                if isinstance(desc, str) and desc.strip():
                    # Show only the first ~140 chars of a long narrative
                    snippet = desc.strip().replace("\n", " ")
                    if len(snippet) > 160:
                        snippet = snippet[:160].rstrip() + "…"
                    st.caption(f"{indent}_{snippet}_")


# -----------------------------------------------------------------------------
# STRATEGIES (multiple per org unit + year supported)
# -----------------------------------------------------------------------------
st.divider()
st.subheader("Strategies")
st.caption(
    "A unit can pursue multiple strategies in parallel — coequal pillars with "
    "their own theories of victory (e.g. 'Grow in New Markets' and 'Improve "
    "Customer Satisfaction'). Each gets its own yearly objectives."
)

# Editing requires a specific org unit. The overview card above is the right
# surface for browsing across multiple orgs; the editor below is per-unit.
if selected_ou_id is None:
    st.info(
        "Editing is per-org-unit. Pick a specific organization in the **Working "
        "on** dropdown above to edit its strategies and yearly objectives."
    )
    st.stop()

ou_strategies = pd.DataFrame()
if not strategies.empty:
    ou_strategies = strategies[
        (strategies["org_unit_id"] == selected_ou_id)
        & (strategies["fiscal_year"] == selected_year)
    ]

# --- Add a new strategy ---------------------------------------------------
with st.expander("➕ Add a new strategy", expanded=ou_strategies.empty):
    with st.form("create_strategy_inline", clear_on_submit=True):
        ns_title = st.text_input(
            "Title",
            placeholder="e.g. Grow in New Markets",
            help=(
                "A single bet with its own theory of victory. If the unit has "
                "two distinct strategic priorities, create them as two strategies."
            ),
        )
        ns_desc = st.text_area(
            "Description (narrative — supports multiple paragraphs)",
            height=160,
            placeholder=(
                "What are we aiming at? Why does it matter? What's our angle "
                "vs alternatives?"
            ),
        )
        create_strat = st.form_submit_button("➕ Create strategy", type="primary")
        if create_strat:
            if not ns_title.strip():
                st.error("Title is required.")
            else:
                try:
                    sb.table("strategy").insert(
                        {
                            "title": ns_title.strip(),
                            "description": ns_desc.strip() or None,
                            "org_unit_id": selected_ou_id,
                            "fiscal_year": int(selected_year),
                        }
                    ).execute()
                    clear_cache()
                    st.success(
                        f"Created strategy **{ns_title}** for "
                        f"**{selected_ou_name}**, FY{selected_year}."
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Insert failed: {e}")

# --- Strategy cards (one per strategy in scope) ---------------------------
if ou_strategies.empty:
    st.info(
        f"No strategies defined for **{selected_ou_name}** in FY{selected_year} yet. "
        "Use the expander above to create the first one."
    )
    st.stop()

# Stable order: by title alphabetically
ou_strategies_sorted = ou_strategies.sort_values("title")
target_period = fy_period(selected_year)

for _, strat in ou_strategies_sorted.iterrows():
    # Count yearly objectives belonging to this specific strategy
    strat_yearly_objs = (
        objectives[
            (objectives["strategy_id"] == strat["id"])
            & (objectives["period"] == target_period)
        ]
        if not objectives.empty
        else pd.DataFrame()
    )

    _strat_status_now = strat.get("status") if isinstance(strat.get("status"), str) else "active"
    _archived_suffix = "  ·  📦 archived" if _strat_status_now == "archived" else ""
    strat_header = (
        f"📜 **{strat['title']}** — "
        f"{len(strat_yearly_objs)} yearly objective"
        f"{'s' if len(strat_yearly_objs) != 1 else ''}"
        f"{_archived_suffix}"
    )

    with st.expander(strat_header, expanded=False):
        # --- Inline edit this strategy --------------------------------------
        with st.form(f"edit_strategy_{strat['id']}"):
            es_title = st.text_input("Title", value=strat["title"])
            cur_desc = strat.get("description")
            es_desc = st.text_area(
                "Description (narrative — supports multiple paragraphs)",
                value=cur_desc if isinstance(cur_desc, str) else "",
                height=160,
            )
            save_strat = st.form_submit_button("💾 Save strategy", type="primary")
            if save_strat:
                if not es_title.strip():
                    st.error("Title is required.")
                else:
                    try:
                        sb.table("strategy").update(
                            {
                                "title": es_title.strip(),
                                "description": es_desc.strip() or None,
                            }
                        ).eq("id", strat["id"]).execute()
                        clear_cache()
                        st.success("Strategy saved.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Update failed: {e}")
        st.caption(f"Strategy ID: `{strat['id']}`")

        # --- Archive / Delete (with blast-radius confirmation) -------------
        # Both actions sit behind a two-click confirmation so a misclick
        # doesn't vaporize a strategy and everything below it.
        _strat_objs = (
            objectives[objectives["strategy_id"] == strat["id"]]
            if not objectives.empty else pd.DataFrame()
        )
        _strat_obj_ids = set(_strat_objs["id"]) if not _strat_objs.empty else set()
        _strat_krs = (
            key_results[key_results["objective_id"].isin(_strat_obj_ids)]
            if _strat_obj_ids and not key_results.empty else pd.DataFrame()
        )
        # Also count quarterly objectives that align to any of this strategy's
        # yearly objectives. If any exist, hard delete will fail (FK constraint
        # on parent_objective_id has no cascade), so we refuse the delete and
        # nudge the user to re-parent or archive.
        _strat_yearly_ids = set(_strat_objs[_strat_objs["period"].astype(str).str.startswith("FY")]["id"]) if not _strat_objs.empty else set()
        _strat_blocking_children = (
            objectives[objectives["parent_objective_id"].isin(_strat_yearly_ids)]
            if _strat_yearly_ids and not objectives.empty else pd.DataFrame()
        )
        _strat_blocking_count = len(_strat_blocking_children)
        _blast = (
            f"{len(_strat_objs)} objective{'s' if len(_strat_objs) != 1 else ''}, "
            f"{len(_strat_krs)} KR{'s' if len(_strat_krs) != 1 else ''}"
        )
        if _strat_blocking_count > 0:
            _blast += (
                f"  ·  blocked by {_strat_blocking_count} child quarterly "
                f"objective{'s' if _strat_blocking_count != 1 else ''}"
            )
        _strat_status = strat.get("status", "active") if isinstance(strat.get("status"), str) else "active"
        _archived = (_strat_status == "archived")

        ac_arch, ac_del, ac_spacer = st.columns([1.2, 1.2, 3])
        with ac_arch:
            _arch_confirm_key = f"strat_arch_confirm_{strat['id']}"
            if st.session_state.get(_arch_confirm_key):
                label = "✓ Unarchive" if _archived else f"✓ Archive ({_blast})"
                if st.button(label, key=f"strat_arch_do_{strat['id']}", use_container_width=True):
                    try:
                        sb.table("strategy").update(
                            {"status": "active" if _archived else "archived"}
                        ).eq("id", strat["id"]).execute()
                        st.session_state.pop(_arch_confirm_key, None)
                        clear_cache()
                        st.success(
                            f"Strategy {'unarchived' if _archived else 'archived'}."
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")
            else:
                if st.button(
                    "📦 Unarchive" if _archived else "📦 Archive",
                    key=f"strat_arch_ask_{strat['id']}",
                    use_container_width=True,
                    help=(
                        "Mark this strategy archived. Hidden from default views; "
                        "data stays and can be unarchived later." if not _archived
                        else "Bring this strategy back to active state."
                    ),
                ):
                    st.session_state[_arch_confirm_key] = True
                    st.rerun()

        with ac_del:
            _del_confirm_key = f"strat_del_confirm_{strat['id']}"
            if _strat_blocking_count > 0:
                st.button(
                    "🗑️ Delete (blocked)",
                    key=f"strat_del_blocked_{strat['id']}",
                    use_container_width=True,
                    disabled=True,
                    help=(
                        f"Can't delete — {_strat_blocking_count} quarterly "
                        "objective(s) still align to this strategy's yearly "
                        "objectives. Re-parent them on Plan a Quarter, or "
                        "archive this strategy instead."
                    ),
                )
            elif st.session_state.get(_del_confirm_key):
                if st.button(
                    f"⚠ Really delete? Will lose {_blast}",
                    key=f"strat_del_do_{strat['id']}",
                    use_container_width=True,
                    type="primary",
                ):
                    try:
                        sb.table("strategy").delete().eq("id", strat["id"]).execute()
                        st.session_state.pop(_del_confirm_key, None)
                        clear_cache()
                        st.success("Strategy deleted (cascade complete).")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")
            else:
                if st.button(
                    "🗑️ Delete",
                    key=f"strat_del_ask_{strat['id']}",
                    use_container_width=True,
                    help=(
                        "Hard delete — removes this strategy AND every objective, "
                        "KR, initiative link, and business case under it. "
                        "Irreversible. Prefer Archive unless you're sure."
                    ),
                ):
                    st.session_state[_del_confirm_key] = True
                    st.rerun()

        if st.session_state.get(_arch_confirm_key) or st.session_state.get(_del_confirm_key):
            st.caption(
                f"⚠ Will affect: **{_blast}**. Click the confirmation button to "
                "proceed, or anywhere else to cancel."
            )

        # --- Yearly objectives under THIS strategy --------------------------
        st.markdown("---")
        st.markdown("**Yearly Objectives**")
        st.caption(
            "3-5 big rocks for the year under this strategy. Each may have a "
            "few aspirational KRs (updated quarterly during reviews, not weekly)."
        )

        # Add a new yearly objective scoped to this strategy
        with st.expander(
            f"➕ Add a yearly objective to '{strat['title']}'",
            expanded=strat_yearly_objs.empty,
        ):
            with st.form(
                f"create_yearly_obj_{strat['id']}", clear_on_submit=True
            ):
                yo_title = st.text_input(
                    "Title",
                    placeholder="e.g. Expand our Presence in Japan",
                )
                yo_owner_col, yo_status_col = st.columns(2)
                with yo_owner_col:
                    yo_owner = st.text_input(
                        "Owner", placeholder="e.g. VP Product"
                    )
                with yo_status_col:
                    yo_status = st.selectbox(
                        "Status", options=OBJ_STATUSES, index=0
                    )
                yo_desc = st.text_area("Description (optional)", height=80)

                submitted = st.form_submit_button(
                    "➕ Add yearly objective", type="primary"
                )
                if submitted:
                    if not yo_title.strip():
                        st.error("Title is required.")
                    else:
                        try:
                            sb.table("objective").insert(
                                {
                                    "title": yo_title.strip(),
                                    "description": yo_desc.strip() or None,
                                    "owner": yo_owner.strip() or None,
                                    "period": target_period,
                                    "status": yo_status,
                                    "strategy_id": strat["id"],
                                    # Derive org_unit_id from the strategy itself,
                                    # not the page-level picker — a yearly objective
                                    # belongs to a strategy and inherits its scope.
                                    # Prevents drift if the picker changed after
                                    # the strategy was chosen.
                                    "org_unit_id": strat["org_unit_id"],
                                }
                            ).execute()
                            clear_cache()
                            st.success(
                                f"Added **{yo_title}** under **{strat['title']}**."
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Insert failed: {e}")

        if strat_yearly_objs.empty:
            st.info(
                "No yearly objectives under this strategy yet — use the "
                "expander above to add one."
            )
            continue

        # --- Existing yearly objectives for this strategy -------------------
        for _, obj in strat_yearly_objs.iterrows():
            obj_krs = (
                key_results[key_results["objective_id"] == obj["id"]]
                if not key_results.empty
                else pd.DataFrame()
            )
            grades = [
                kr_progress(
                    kr.get("start_value"),
                    kr.get("target_value"),
                    kr.get("current_value"),
                )
                for _, kr in obj_krs.iterrows()
            ]
            avg_dot = grade_color(sum(grades) / len(grades)) if grades else "⚪"
            obj_status = obj.get("status", "active")
            status_icon = {"active": "🟢", "closed": "🔵", "archived": "⚪"}.get(
                obj_status, ""
            )
            obj_header = (
                f"{status_icon} **{obj['title']}** — {avg_dot} "
                f"{len(obj_krs)} KR{'s' if len(obj_krs) != 1 else ''}"
            )

            with st.expander(obj_header, expanded=False):
                # Inline edit objective
                with st.form(f"edit_yearly_obj_{obj['id']}"):
                    eo_title = st.text_input("Title", value=obj["title"])
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        cur_owner = obj.get("owner")
                        eo_owner = st.text_input(
                            "Owner",
                            value=cur_owner if isinstance(cur_owner, str) else "",
                        )
                    with ec2:
                        cur_st = obj.get("status", "active")
                        eo_status = st.selectbox(
                            "Status",
                            options=OBJ_STATUSES,
                            index=OBJ_STATUSES.index(cur_st)
                            if cur_st in OBJ_STATUSES
                            else 0,
                        )
                    cur_obj_desc = obj.get("description")
                    eo_desc = st.text_area(
                        "Description",
                        value=cur_obj_desc if isinstance(cur_obj_desc, str) else "",
                        height=80,
                    )
                    save_o = st.form_submit_button("💾 Save objective")
                    if save_o:
                        if not eo_title.strip():
                            st.error("Title is required.")
                        else:
                            try:
                                sb.table("objective").update(
                                    {
                                        "title": eo_title.strip(),
                                        "description": eo_desc.strip() or None,
                                        "owner": eo_owner.strip() or None,
                                        "status": eo_status,
                                    }
                                ).eq("id", obj["id"]).execute()
                                clear_cache()
                                st.success("Objective saved.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Update failed: {e}")

                # --- Archive / Delete the yearly objective ---------------
                _yo_krs_local = obj_krs
                # Count child quarterly objectives that align to this yearly.
                # Postgres has no cascade on parent_objective_id (intentional —
                # a parent's delete must not silently orphan children's links),
                # so we refuse the delete if any children exist and explain why.
                _yo_children = (
                    objectives[objectives["parent_objective_id"] == obj["id"]]
                    if not objectives.empty else pd.DataFrame()
                )
                _yo_child_count = len(_yo_children)
                _yo_blast = (
                    f"{len(_yo_krs_local)} KR"
                    f"{'s' if len(_yo_krs_local) != 1 else ''}"
                )
                if _yo_child_count > 0:
                    _yo_blast += (
                        f"  ·  blocked by {_yo_child_count} child quarterly "
                        f"objective{'s' if _yo_child_count != 1 else ''}"
                    )
                _yo_archived = (obj.get("status") == "archived")

                yc_arch, yc_del, _ = st.columns([1.2, 1.2, 3])
                with yc_arch:
                    _yo_arch_key = f"yo_arch_confirm_{obj['id']}"
                    if st.session_state.get(_yo_arch_key):
                        label = "✓ Unarchive" if _yo_archived else f"✓ Archive"
                        if st.button(label, key=f"yo_arch_do_{obj['id']}", use_container_width=True):
                            try:
                                sb.table("objective").update(
                                    {"status": "active" if _yo_archived else "archived"}
                                ).eq("id", obj["id"]).execute()
                                st.session_state.pop(_yo_arch_key, None)
                                clear_cache()
                                st.success(
                                    f"Yearly objective {'unarchived' if _yo_archived else 'archived'}."
                                )
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed: {e}")
                    else:
                        if st.button(
                            "📦 Unarchive" if _yo_archived else "📦 Archive",
                            key=f"yo_arch_ask_{obj['id']}",
                            use_container_width=True,
                        ):
                            st.session_state[_yo_arch_key] = True
                            st.rerun()

                with yc_del:
                    _yo_del_key = f"yo_del_confirm_{obj['id']}"
                    if _yo_child_count > 0:
                        # Can't delete — children would dangle. Show a disabled
                        # button and a clear next-step message.
                        st.button(
                            "🗑️ Delete (blocked)",
                            key=f"yo_del_blocked_{obj['id']}",
                            use_container_width=True,
                            disabled=True,
                            help=(
                                f"Can't delete — {_yo_child_count} quarterly "
                                "objective(s) still align to this yearly. "
                                "Re-parent them first on Plan a Quarter, or "
                                "archive this yearly instead."
                            ),
                        )
                    elif st.session_state.get(_yo_del_key):
                        if st.button(
                            f"⚠ Really delete? Will lose {_yo_blast}",
                            key=f"yo_del_do_{obj['id']}",
                            use_container_width=True,
                            type="primary",
                        ):
                            try:
                                sb.table("objective").delete().eq("id", obj["id"]).execute()
                                st.session_state.pop(_yo_del_key, None)
                                clear_cache()
                                st.success("Yearly objective deleted.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Delete failed: {e}")
                    else:
                        if st.button(
                            "🗑️ Delete",
                            key=f"yo_del_ask_{obj['id']}",
                            use_container_width=True,
                            help=(
                                "Hard delete — removes this objective and every "
                                "KR under it. Irreversible. Prefer Archive."
                            ),
                        ):
                            st.session_state[_yo_del_key] = True
                            st.rerun()

                if st.session_state.get(_yo_arch_key) or st.session_state.get(_yo_del_key):
                    st.caption(
                        f"⚠ Will affect: **{_yo_blast}**. Click the confirmation "
                        "button to proceed, or anywhere else to cancel."
                    )

                # KRs under this objective
                st.markdown("**Aspirational Key Results**")
                if obj_krs.empty:
                    st.info("No KRs on this yearly objective yet.")
                else:
                    for _, kr in obj_krs.iterrows():
                        grade = kr_progress(
                            kr.get("start_value"),
                            kr.get("target_value"),
                            kr.get("current_value"),
                        )
                        unit = kr.get("metric_unit") or ""
                        _ind_type = kr.get("indicator_type")
                        indicator_prefix = ""
                        if _ind_type == "lagging":
                            indicator_prefix = "🎯 "
                        elif _ind_type == "leading":
                            indicator_prefix = "📡 "
                        kr_header = (
                            f"{grade_color(grade)} {indicator_prefix}**{kr['title']}** — "
                            f"{kr.get('current_value')} / {kr.get('target_value')} {unit} "
                            f"({grade:.0%})"
                        )
                        with st.expander(kr_header, expanded=False):
                            with st.form(f"edit_yearly_kr_{kr['id']}"):
                                kt_title = st.text_input(
                                    "Title", value=kr["title"]
                                )
                                kcc1, kcc2, kcc3, kcc4 = st.columns(4)
                                with kcc1:
                                    cur_unit = kr.get("metric_unit") or "%"
                                    unit_opts = COMMON_UNITS + ["other"]
                                    if cur_unit in COMMON_UNITS:
                                        u_idx = unit_opts.index(cur_unit)
                                        custom_default = ""
                                    else:
                                        u_idx = len(unit_opts) - 1
                                        custom_default = cur_unit
                                    kt_unit = st.selectbox(
                                        "Unit", options=unit_opts, index=u_idx
                                    )
                                with kcc2:
                                    kt_start = st.number_input(
                                        "Start",
                                        value=float(kr.get("start_value") or 0),
                                        step=1.0,
                                        format="%.2f",
                                    )
                                with kcc3:
                                    kt_target = st.number_input(
                                        "Target",
                                        value=float(kr.get("target_value") or 100),
                                        step=1.0,
                                        format="%.2f",
                                    )
                                with kcc4:
                                    kt_current = st.number_input(
                                        "Current",
                                        value=float(kr.get("current_value") or 0),
                                        step=1.0,
                                        format="%.2f",
                                    )
                                kt_unit_custom = ""
                                if kt_unit == "other":
                                    kt_unit_custom = st.text_input(
                                        "Custom unit", value=custom_default
                                    )
                                cur_kr_owner = kr.get("owner")
                                kt_owner = st.text_input(
                                    "Owner",
                                    value=cur_kr_owner if isinstance(cur_kr_owner, str) else "",
                                    placeholder="e.g. VP Growth",
                                    key=f"yearly_owner_{kr['id']}",
                                )
                                cur_kt_indicator = kr.get("indicator_type") or ""
                                kt_indicator = st.selectbox(
                                    "Indicator type",
                                    options=INDICATOR_TYPES,
                                    index=INDICATOR_TYPES.index(cur_kt_indicator)
                                    if cur_kt_indicator in INDICATOR_TYPES else 0,
                                    format_func=lambda t: INDICATOR_LABELS.get(t, t),
                                    key=f"yearly_indicator_{kr['id']}",
                                    help=(
                                        "Leading (early signal), Lagging (final "
                                        "outcome), or Standalone."
                                    ),
                                )
                                save_k = st.form_submit_button("💾 Save KR")
                                if save_k:
                                    if not kt_title.strip():
                                        st.error("Title is required.")
                                    elif (
                                        kt_unit == "other"
                                        and not kt_unit_custom.strip()
                                    ):
                                        st.error("Specify a custom unit.")
                                    else:
                                        unit_value = (
                                            kt_unit_custom.strip()
                                            if kt_unit == "other"
                                            else kt_unit
                                        )
                                        try:
                                            sb.table("key_result").update(
                                                {
                                                    "title": kt_title.strip(),
                                                    "metric_unit": unit_value,
                                                    "start_value": kt_start,
                                                    "target_value": kt_target,
                                                    "current_value": kt_current,
                                                    "owner": kt_owner.strip() or None,
                                                    "indicator_type": kt_indicator or None,
                                                }
                                            ).eq("id", kr["id"]).execute()
                                            clear_cache()
                                            st.success("KR saved.")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Update failed: {e}")

                # Add a new KR to this yearly objective
                with st.expander("➕ Add an aspirational KR", expanded=False):
                    with st.form(
                        f"add_yearly_kr_{obj['id']}", clear_on_submit=True
                    ):
                        nk_title = st.text_input(
                            "Title",
                            placeholder="e.g. 10 Early Adopters on Product B by end of Q3 2026",
                        )
                        nkc1, nkc2, nkc3, nkc4 = st.columns(4)
                        with nkc1:
                            nk_unit = st.selectbox(
                                "Unit",
                                options=COMMON_UNITS + ["other"],
                                index=1,  # default to 'count' since the example uses counts
                            )
                        with nkc2:
                            nk_start = st.number_input(
                                "Start", value=0.0, step=1.0, format="%.2f"
                            )
                        with nkc3:
                            nk_target = st.number_input(
                                "Target", value=10.0, step=1.0, format="%.2f"
                            )
                        with nkc4:
                            nk_current = st.number_input(
                                "Current", value=0.0, step=1.0, format="%.2f"
                            )
                        nk_unit_custom = ""
                        if nk_unit == "other":
                            nk_unit_custom = st.text_input("Custom unit")
                        nk_owner = st.text_input(
                            "Owner (optional)",
                            placeholder="e.g. VP Growth",
                            help="Who is responsible for moving this KR?",
                        )
                        nk_indicator = st.selectbox(
                            "Indicator type",
                            options=INDICATOR_TYPES,
                            index=0,
                            format_func=lambda t: INDICATOR_LABELS.get(t, t),
                            help=(
                                "Leading, Lagging, or Standalone — just a label, "
                                "no rollup math."
                            ),
                        )
                        add_k = st.form_submit_button("➕ Add KR", type="primary")
                        if add_k:
                            if not nk_title.strip():
                                st.error("Title is required.")
                            elif (
                                nk_unit == "other"
                                and not nk_unit_custom.strip()
                            ):
                                st.error("Specify a custom unit.")
                            else:
                                unit_value = (
                                    nk_unit_custom.strip()
                                    if nk_unit == "other"
                                    else nk_unit
                                )
                                try:
                                    sb.table("key_result").insert(
                                        {
                                            "objective_id": obj["id"],
                                            "title": nk_title.strip(),
                                            "metric_unit": unit_value,
                                            "start_value": nk_start,
                                            "target_value": nk_target,
                                            "current_value": nk_current,
                                            "owner": nk_owner.strip() or None,
                                            "indicator_type": nk_indicator or None,
                                        }
                                    ).execute()
                                    clear_cache()
                                    st.success(f"Added KR **{nk_title}**.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Insert failed: {e}")

                st.caption(f"Objective ID: `{obj['id']}`")


# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.divider()
st.caption(
    "Yearly objectives are aspirational and stable. Quarterly OKRs and "
    "initiatives — the actual bets you'll make and ship — live on the **Plan "
    "a Quarter** page, where they cascade up to these yearly objectives via "
    "the parent-objective link."
)

"""
Plan an Objective — the planning workspace.

Pick one objective and build out the entire tree underneath it inline: KRs,
initiatives, business cases. No page-hopping, no losing visual context.

The mental model:
    SELECTED OBJECTIVE
        ↓ KR 1
            ↓ Initiative A (+ business case)
            ↓ Initiative B (+ business case)
        ↓ KR 2
            ↓ Initiative C (+ business case)
        ...

Each row is editable in place. Each level has a small "+ add" affordance so a
new KR / initiative / business case can be added without leaving the page.

This is the page a product lead opens when planning a quarter. The existing
Manage pages stay around for bulk editing and setup.
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
# Constants
# -----------------------------------------------------------------------------
COMMON_UNITS = ["%", "count", "USD", "min", "hours", "days", "score", "NPS"]
INIT_STATUSES = ["proposed", "active", "done", "killed"]
MILESTONE_STATUSES = ["on_track", "at_risk", "blocked"]
DECISIONS = ["pending", "approved", "rejected"]
EFFORT_SIZES = ["", "XS", "S", "M", "L", "XL"]


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def period_sort_key(period: str) -> tuple:
    if not period:
        return (9999, 9, period or "")
    try:
        q, y = period.split("-")
        return (int(y), int(q.lstrip("Q")), "")
    except (ValueError, AttributeError):
        return (9999, 9, period)


def year_from_period(period: str):
    """Extract the year from a 'Qn-YYYY' period string. Returns None on failure."""
    if not period:
        return None
    try:
        return int(period.split("-")[1])
    except (ValueError, AttributeError, IndexError):
        return None


def prior_period(period: str, all_periods) -> str | None:
    """Find the period that comes chronologically right before `period`."""
    sorted_periods = sorted(set(all_periods), key=period_sort_key)
    try:
        idx = sorted_periods.index(period)
        return sorted_periods[idx - 1] if idx > 0 else None
    except ValueError:
        return None


def common_periods() -> list[str]:
    return [
        "Q1-2025", "Q2-2025", "Q3-2025", "Q4-2025",
        "Q1-2026", "Q2-2026", "Q3-2026", "Q4-2026",
        "Q1-2027", "Q2-2027", "Q3-2027", "Q4-2027",
    ]


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
st.title("✏️ Plan an Objective")
st.caption(
    "Pick one objective and build the cascade underneath it inline. The "
    "natural workflow for quarterly planning — KRs, initiatives, and business "
    "cases all editable in one place."
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

if objectives.empty:
    st.warning(
        "No objectives yet. Go to **Manage → Strategy & Objectives** to create "
        "your first one, then come back here to flesh it out."
    )
    st.stop()


# -----------------------------------------------------------------------------
# Objective picker
# -----------------------------------------------------------------------------
ou_name_by_id = org_units.set_index("id")["name"].to_dict()

# Build options sorted by org unit then period
ou_sorted = org_units.copy()
level_order = {"company": 0, "segment": 1, "team": 2}
ou_sorted["__order"] = ou_sorted["level"].map(level_order).fillna(99)
ou_sorted = ou_sorted.sort_values(["__order", "name"])
ou_position = {row["id"]: i for i, (_, row) in enumerate(ou_sorted.iterrows())}

objs_sorted = objectives.copy()
objs_sorted["__pos"] = objs_sorted["org_unit_id"].map(ou_position).fillna(999)
objs_sorted["__period_key"] = objs_sorted["period"].apply(period_sort_key)
objs_sorted = objs_sorted.sort_values(["__pos", "__period_key"])

objective_options = []
for _, o in objs_sorted.iterrows():
    ou_name = ou_name_by_id.get(o["org_unit_id"], "?")
    label = f"{ou_name} · {o['period']} — {o['title']}"
    objective_options.append((o["id"], label))

obj_labels = [lbl for _, lbl in objective_options]
obj_id_by_label = {lbl: oid for oid, lbl in objective_options}
obj_label_by_id = {oid: lbl for oid, lbl in objective_options}

# If we just created an objective via the inline form, pre-select it after
# rerun. Then clear the flag so subsequent navigation doesn't keep snapping
# back to that objective.
default_picker_idx = 0
just_created_id = st.session_state.pop("just_created_obj_id", None)
if just_created_id and just_created_id in obj_label_by_id:
    new_label = obj_label_by_id[just_created_id]
    if new_label in obj_labels:
        default_picker_idx = obj_labels.index(new_label)

# Objective picker lives inline at the top of the page, not in the sidebar —
# the selection drives the whole page, so it needs to be impossible to miss.
# Wide column so long objective labels don't get truncated.
pc1, pc2 = st.columns([3, 1])
with pc1:
    selected_label = st.selectbox(
        "**Working on**",
        options=obj_labels,
        index=default_picker_idx,
        help="Pick the objective you want to plan in depth.",
    )

selected_obj_id = obj_id_by_label[selected_label]
selected_obj = objectives[objectives["id"] == selected_obj_id].iloc[0]
selected_ou_id = selected_obj["org_unit_id"]
selected_ou_name = ou_name_by_id.get(selected_ou_id, "?")


# -----------------------------------------------------------------------------
# Strategy context card (read-only)
# -----------------------------------------------------------------------------
# Show the strategy the selected objective sits under. Looks up by org_unit_id,
# preferring exact fiscal-year match, falling back to most recent for that org.
strategy_for_obj = None
if not strategies.empty:
    ou_strategies = strategies[strategies["org_unit_id"] == selected_ou_id]
    if not ou_strategies.empty:
        obj_year = year_from_period(selected_obj.get("period", ""))
        if obj_year is not None:
            year_match = ou_strategies[ou_strategies["fiscal_year"] == obj_year]
            if not year_match.empty:
                strategy_for_obj = year_match.iloc[0]
        if strategy_for_obj is None:
            # Fall back to most recent strategy for this org unit
            strategy_for_obj = ou_strategies.sort_values(
                "fiscal_year", ascending=False
            ).iloc[0]

with st.container(border=True):
    if strategy_for_obj is not None:
        st.markdown(
            f"**🗺️ Strategy · {selected_ou_name} · FY{int(strategy_for_obj['fiscal_year'])}**  —  "
            f"{strategy_for_obj['title']}"
        )
        if strategy_for_obj.get("description"):
            st.caption(strategy_for_obj["description"])
    else:
        st.markdown(f"**🗺️ Strategy · {selected_ou_name}** — _not yet defined_")
        st.caption(
            "Define an annual strategy on **Manage → Strategy & Objectives**. "
            "It gives the cascade below its 'why'."
        )


# -----------------------------------------------------------------------------
# Previous period card (read-only)
# -----------------------------------------------------------------------------
# Same org unit, immediately prior period. Shows the objectives that ran in the
# last quarter and their average KR grade — useful continuity signal when
# planning the next quarter's bets.
prior_p = prior_period(selected_obj["period"], objectives["period"].dropna().tolist())
prior_objs = pd.DataFrame()
if prior_p:
    prior_objs = objectives[
        (objectives["org_unit_id"] == selected_ou_id)
        & (objectives["period"] == prior_p)
    ]

if prior_p and not prior_objs.empty:
    with st.container(border=True):
        st.markdown(f"**📋 Previous period · {prior_p}**")
        for _, p_obj in prior_objs.iterrows():
            p_obj_krs = key_results[key_results["objective_id"] == p_obj["id"]]
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
# Add a new objective (inline)
# -----------------------------------------------------------------------------
# Defaults to the same org unit as the currently-selected objective and the
# next chronological period — both safe assumptions for "I'm planning the next
# quarter for this team".
def _next_period(current: str) -> str:
    """Bump Qn-YYYY by one quarter, rolling over the year."""
    try:
        q, y = current.split("-")
        q_num = int(q.lstrip("Q"))
        y_num = int(y)
        if q_num == 4:
            return f"Q1-{y_num + 1}"
        return f"Q{q_num + 1}-{y_num}"
    except (ValueError, AttributeError):
        return "Q1-2026"


with st.expander("➕ Plan a new objective", expanded=False):
    # Strategy dropdown — sorted by org tree position, year desc
    if strategies.empty:
        st.info(
            "No strategies defined yet. Add one on **Manage → Strategy & "
            "Objectives** first; objectives belong to a strategy."
        )
    else:
        strats_for_dropdown = strategies.copy()
        strats_for_dropdown["__pos"] = (
            strats_for_dropdown["org_unit_id"].map(ou_position).fillna(999)
        )
        strats_for_dropdown = strats_for_dropdown.sort_values(
            ["__pos", "fiscal_year"], ascending=[True, False]
        )

        strategy_options = []
        for _, s in strats_for_dropdown.iterrows():
            s_ou_name = ou_name_by_id.get(s["org_unit_id"], "?")
            label = f"{s_ou_name} · FY{int(s['fiscal_year'])} — {s['title']}"
            strategy_options.append((s["id"], label, s["org_unit_id"]))
        strategy_labels = [lbl for _, lbl, _ in strategy_options]
        strategy_ou_by_id = {sid: ouid for sid, _, ouid in strategy_options}

        # Default the strategy dropdown to one matching the currently-selected
        # objective's org unit (if found).
        default_strat_idx = 0
        for i, (_, _, ouid) in enumerate(strategy_options):
            if ouid == selected_ou_id:
                default_strat_idx = i
                break

        with st.form("create_objective_inline", clear_on_submit=True):
            no1, no2 = st.columns([3, 2])
            with no1:
                no_title = st.text_input(
                    "Title",
                    placeholder="e.g. Turn new signups into activated, paying teams",
                )
            with no2:
                no_strategy_label = st.selectbox(
                    "Strategy",
                    options=strategy_labels,
                    index=default_strat_idx,
                )

            no3, no4, no5 = st.columns([2, 2, 2])
            with no3:
                periods = common_periods()
                default_period = _next_period(selected_obj.get("period", "Q3-2026"))
                if default_period not in periods:
                    periods = [default_period] + periods
                no_period = st.selectbox(
                    "Period",
                    options=periods,
                    index=periods.index(default_period),
                )
            with no4:
                no_owner = st.text_input("Owner", placeholder="e.g. VP Product")
            with no5:
                no_status = st.selectbox(
                    "Status", options=["active", "closed", "archived"], index=0
                )

            # Parent objective picker — same-or-earlier period only, no cycles
            def _eligible_parents_for_period(child_period: str):
                out = []
                for _, o in objectives.iterrows():
                    if period_sort_key(o.get("period")) > period_sort_key(child_period):
                        continue
                    ou_name = ou_name_by_id.get(o["org_unit_id"], "?")
                    out.append(
                        (o["id"], f"{ou_name} · {o['period']} — {o['title']}")
                    )
                return out

            eligible = _eligible_parents_for_period(no_period)
            parent_labels = ["— No parent (top of cascade) —"] + [
                lbl for _, lbl in eligible
            ]
            parent_id_by_label = {lbl: oid for oid, lbl in eligible}

            # Default parent: if the currently-selected objective is at an
            # eligible period (same or earlier), pre-pick it as the parent —
            # that's the natural "this is the child of the one I was just on" case.
            default_parent_idx = 0
            if period_sort_key(selected_obj.get("period")) <= period_sort_key(no_period):
                target_label = obj_label_by_id.get(selected_obj_id)
                if target_label in parent_labels:
                    default_parent_idx = parent_labels.index(target_label)

            no_parent_label = st.selectbox(
                "Aligns to (parent objective)",
                options=parent_labels,
                index=default_parent_idx,
                help="Only objectives in the same or an earlier period are shown.",
            )

            no_desc = st.text_area("Description (optional)", height=80)

            submitted_new_obj = st.form_submit_button(
                "➕ Add objective and start planning it", type="primary"
            )
            if submitted_new_obj:
                if not no_title.strip():
                    st.error("Title is required.")
                else:
                    new_strategy_id = next(
                        sid for sid, lbl, _ in strategy_options
                        if lbl == no_strategy_label
                    )
                    new_parent_id = parent_id_by_label.get(no_parent_label)
                    try:
                        inserted = sb.table("objective").insert(
                            {
                                "title": no_title.strip(),
                                "description": no_desc.strip() or None,
                                "owner": no_owner.strip() or None,
                                "period": no_period,
                                "status": no_status,
                                "strategy_id": new_strategy_id,
                                "org_unit_id": strategy_ou_by_id[new_strategy_id],
                                "parent_objective_id": new_parent_id,
                            }
                        ).execute()
                        new_obj_id = inserted.data[0]["id"]
                        # Remember so the picker preselects it after rerun
                        st.session_state["just_created_obj_id"] = new_obj_id
                        clear_cache()
                        st.success(
                            f"Added objective **{no_title}** — page will switch "
                            "to plan it now."
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Insert failed: {e}")


# -----------------------------------------------------------------------------
# Objective header card
# -----------------------------------------------------------------------------
ou_name = selected_ou_name
status_icon = {"active": "🟢", "closed": "🔵", "archived": "⚪"}.get(
    selected_obj.get("status", "active"), ""
)

st.markdown(
    f"### {status_icon} {selected_obj['title']}"
)
st.markdown(
    f"**{ou_name}** · {selected_obj['period']}  ·  Owner: "
    f"{selected_obj.get('owner') or '—'}"
)
if selected_obj.get("description"):
    st.caption(selected_obj["description"])

st.divider()


# -----------------------------------------------------------------------------
# KRs under this objective
# -----------------------------------------------------------------------------
obj_krs = key_results[key_results["objective_id"] == selected_obj_id]

st.subheader(f"Key Results ({len(obj_krs)})")
st.caption("3-5 is the sweet spot. Each should be measurable and outcome-focused.")

# --- Add KR form -----------------------------------------------------------
with st.expander("➕ Add a Key Result", expanded=obj_krs.empty):
    with st.form(f"add_kr_{selected_obj_id}", clear_on_submit=True):
        new_kr_title = st.text_input(
            "Title", placeholder="e.g. Activation rate (team reaches first insight)"
        )
        kc1, kc2, kc3, kc4 = st.columns(4)
        with kc1:
            new_kr_unit_choice = st.selectbox(
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
        if new_kr_unit_choice == "other":
            new_kr_unit_custom = st.text_input("Custom unit", placeholder="e.g. 'demos'")

        prev = kr_progress(new_kr_start, new_kr_target, new_kr_current)
        st.caption(
            f"Preview grade: {grade_color(prev)} **{prev:.0%}** "
            f"({new_kr_start} → {new_kr_current} → {new_kr_target})"
        )

        submitted = st.form_submit_button("➕ Add KR", type="primary")
        if submitted:
            if not new_kr_title.strip():
                st.error("Title is required.")
            elif new_kr_unit_choice == "other" and not new_kr_unit_custom.strip():
                st.error("Specify a custom unit or pick from the list.")
            else:
                unit_value = (
                    new_kr_unit_custom.strip()
                    if new_kr_unit_choice == "other"
                    else new_kr_unit_choice
                )
                try:
                    sb.table("key_result").insert(
                        {
                            "objective_id": selected_obj_id,
                            "title": new_kr_title.strip(),
                            "metric_unit": unit_value,
                            "start_value": new_kr_start,
                            "target_value": new_kr_target,
                            "current_value": new_kr_current,
                        }
                    ).execute()
                    clear_cache()
                    st.success(f"Added KR **{new_kr_title}**.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Insert failed: {e}")


# --- Existing KRs (with their initiatives nested inside) -------------------
if obj_krs.empty:
    st.info("No KRs yet — add the first one above. The cascade lives or dies here.")
    st.stop()


# Lookups for initiatives and business cases
init_by_id = (
    initiatives.set_index("id").to_dict("index") if not initiatives.empty else {}
)
bc_by_init = (
    business_cases.set_index("initiative_id").to_dict("index")
    if not business_cases.empty
    else {}
)


for _, kr in obj_krs.iterrows():
    grade = kr_progress(
        kr.get("start_value"), kr.get("target_value"), kr.get("current_value")
    )
    unit = kr.get("metric_unit") or ""

    kr_header = (
        f"{grade_color(grade)} **{kr['title']}** — "
        f"{kr.get('current_value')} / {kr.get('target_value')} {unit} "
        f"({grade:.0%})"
    )

    with st.expander(kr_header, expanded=True):
        # ---- Inline edit KR -------------------------------------------------
        with st.form(f"edit_kr_{kr['id']}"):
            kec1, kec2, kec3, kec4, kec5 = st.columns([3, 1, 1, 1, 1])
            with kec1:
                ek_title = st.text_input("Title", value=kr["title"])
            with kec2:
                cur_unit = kr.get("metric_unit") or "%"
                unit_opts = COMMON_UNITS + ["other"]
                if cur_unit in COMMON_UNITS:
                    unit_idx = unit_opts.index(cur_unit)
                else:
                    unit_idx = len(unit_opts) - 1
                ek_unit = st.selectbox("Unit", options=unit_opts, index=unit_idx)
            with kec3:
                ek_start = st.number_input(
                    "Start",
                    value=float(kr.get("start_value") or 0),
                    step=1.0,
                    format="%.2f",
                )
            with kec4:
                ek_target = st.number_input(
                    "Target",
                    value=float(kr.get("target_value") or 100),
                    step=1.0,
                    format="%.2f",
                )
            with kec5:
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
                        ek_unit_custom.strip() if ek_unit == "other" else ek_unit
                    )
                    try:
                        sb.table("key_result").update(
                            {
                                "title": ek_title.strip(),
                                "metric_unit": unit_value,
                                "start_value": ek_start,
                                "target_value": ek_target,
                                "current_value": ek_current,
                            }
                        ).eq("id", kr["id"]).execute()
                        clear_cache()
                        st.success("KR saved.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Update failed: {e}")

        # ---- Initiatives moving this KR -----------------------------------
        st.markdown("**Initiatives moving this KR**")

        # Find initiatives linked to this KR via the join table
        kr_links = (
            links[links["key_result_id"] == kr["id"]]
            if not links.empty
            else pd.DataFrame()
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
                if bc and bc.get("predicted_cost") and bc.get("predicted_value"):
                    if bc["predicted_cost"] > 0:
                        roi_str = f"{bc['predicted_value']/bc['predicted_cost']:.1f}x"

                init_header = (
                    f"{init_status_icon} **{init['title']}**  ·  "
                    f"Delivery: {init.get('progress_pct') or 0}%  ·  "
                    f"Impact on this KR: {link.get('predicted_kr_impact') or '—'}  ·  "
                    f"ROI: {roi_str}"
                )

                with st.expander(init_header, expanded=False):
                    # Inline initiative edit
                    with st.form(f"edit_init_{init_id}_{kr['id']}"):
                        ic1, ic2 = st.columns([3, 1])
                        with ic1:
                            ei_title = st.text_input("Title", value=init["title"])
                        with ic2:
                            ei_owner = st.text_input(
                                "Owner", value=init.get("owner") or ""
                            )

                        ic3, ic4, ic5, ic6 = st.columns(4)
                        with ic3:
                            ei_status = st.selectbox(
                                "Status",
                                options=INIT_STATUSES,
                                index=INIT_STATUSES.index(init.get("status", "proposed"))
                                if init.get("status") in INIT_STATUSES else 0,
                            )
                        with ic4:
                            cur_ms = init.get("milestone_status")
                            ms_opts = [""] + MILESTONE_STATUSES
                            ei_ms = st.selectbox(
                                "Milestone",
                                options=ms_opts,
                                index=ms_opts.index(cur_ms) if cur_ms in ms_opts else 0,
                            )
                        with ic5:
                            cur_effort = init.get("effort_estimate") or ""
                            ei_effort = st.selectbox(
                                "Effort",
                                options=EFFORT_SIZES,
                                index=EFFORT_SIZES.index(cur_effort)
                                if cur_effort in EFFORT_SIZES else 0,
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

                        # The KR-specific impact (from the join row)
                        st.markdown("**Predicted impact on _this_ KR**")
                        ie1, ie2 = st.columns(2)
                        with ie1:
                            ei_predicted = st.number_input(
                                f"Predicted impact ({unit})",
                                value=float(link.get("predicted_kr_impact") or 0),
                                step=1.0,
                                format="%.2f",
                                help=(
                                    "This bet's claimed effect on this KR. If "
                                    "the initiative also moves other KRs, those "
                                    "have their own impact values on their pages."
                                ),
                            )
                        with ie2:
                            ei_actual = st.number_input(
                                f"Actual impact ({unit})",
                                value=float(link.get("actual_kr_impact") or 0),
                                step=1.0,
                                format="%.2f",
                                help="Fill in after the bet runs to close the loop.",
                            )

                        save_init = st.form_submit_button("💾 Save initiative")
                        if save_init:
                            if not ei_title.strip():
                                st.error("Title is required.")
                            else:
                                try:
                                    # Update initiative
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
                                    # Update the join row (per-KR impact)
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

                    # ---- Business case for this initiative ------------------
                    st.markdown("**Business case**")
                    if bc:
                        with st.form(f"edit_bc_{bc['id']}_{kr['id']}"):
                            bc_summary = st.text_area(
                                "Summary",
                                value=bc.get("summary") or "",
                                height=60,
                                placeholder="One-line justification: why is this bet worth funding?",
                            )

                            bcc1, bcc2 = st.columns(2)
                            with bcc1:
                                bc_metric = st.text_input(
                                    "Target metric",
                                    value=bc.get("target_metric") or "",
                                    placeholder="e.g. 'new ARR'",
                                )
                            with bcc2:
                                bc_unit_val = st.text_input(
                                    "Metric unit",
                                    value=bc.get("target_metric_unit") or "",
                                    placeholder="e.g. 'USD'",
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

                            cur_decision = bc.get("decision") or "pending"
                            bc_decision = st.selectbox(
                                "Decision",
                                options=DECISIONS,
                                index=DECISIONS.index(cur_decision)
                                if cur_decision in DECISIONS else 0,
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

                            save_bc = st.form_submit_button("💾 Save business case")
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
                        # No business case yet — quick-add inline
                        st.caption(
                            "_No business case attached. This bet isn't "
                            "justified with predicted value vs cost yet._"
                        )
                        with st.form(f"add_bc_{init_id}_{kr['id']}"):
                            bcq1, bcq2, bcq3 = st.columns(3)
                            with bcq1:
                                qbc_metric = st.text_input(
                                    "Target metric", placeholder="e.g. 'new ARR'"
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
                                "Summary (optional)", placeholder="One-line justification"
                            )
                            add_bc = st.form_submit_button("➕ Attach business case")
                            if add_bc:
                                if qbc_pv <= 0 or qbc_pc <= 0:
                                    st.error(
                                        "Need both predicted value and cost to compute ROI."
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

        # ---- Add new initiative against this KR ---------------------------
        st.markdown("")
        with st.expander(f"➕ Propose a new initiative against this KR", expanded=False):
            with st.form(f"add_init_{kr['id']}", clear_on_submit=True):
                ni_title = st.text_input(
                    "Title",
                    placeholder="e.g. 'Guided onboarding flow with sample dataset'",
                )
                nic1, nic2, nic3 = st.columns(3)
                with nic1:
                    ni_owner = st.text_input("Owner")
                with nic2:
                    ni_effort = st.selectbox("Effort", options=EFFORT_SIZES, index=0)
                with nic3:
                    ni_predicted_impact = st.number_input(
                        f"Predicted impact on this KR ({unit})",
                        value=0.0,
                        step=1.0,
                    )
                ni_desc = st.text_area("Description", height=80)

                # Optional inline business case at proposal time
                st.markdown("**Optional business case (recommended)**")
                bc1, bc2, bc3 = st.columns(3)
                with bc1:
                    ni_metric = st.text_input(
                        "Target metric", placeholder="e.g. 'new ARR'"
                    )
                with bc2:
                    ni_pv = st.number_input(
                        "Predicted value", value=0.0, step=1000.0
                    )
                with bc3:
                    ni_pc = st.number_input(
                        "Predicted cost", value=0.0, step=1000.0
                    )
                ni_bc_summary = st.text_input(
                    "Business case summary",
                    placeholder="One-line justification (optional)",
                )

                add_initiative = st.form_submit_button(
                    "➕ Propose initiative", type="primary"
                )
                if add_initiative:
                    if not ni_title.strip():
                        st.error("Title is required.")
                    else:
                        try:
                            # 1. Insert initiative
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

                            # 2. Insert join (this KR)
                            sb.table("initiative_key_result").insert(
                                {
                                    "initiative_id": new_init_id,
                                    "key_result_id": kr["id"],
                                    "predicted_kr_impact": ni_predicted_impact
                                    if ni_predicted_impact != 0 else None,
                                }
                            ).execute()

                            # 3. Optionally insert business case
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
                            st.success(
                                f"Proposed **{ni_title}**{roi_msg}. "
                                "Set status to 'active' once approved."
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Couldn't propose initiative: {e}")


# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.divider()
st.caption(
    "Tips: KRs are the outcomes; initiatives are the bets. The discipline is "
    "keeping them honest: an initiative isn't \"done\" because it shipped — "
    "it's done when its predicted KR impact shows up in the Actual column."
)

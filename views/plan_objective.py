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

with st.sidebar:
    st.header("Working on")
    selected_label = st.selectbox(
        "Objective",
        options=obj_labels,
        index=0,
        help="Pick the objective you want to plan in depth.",
    )

selected_obj_id = obj_id_by_label[selected_label]
selected_obj = objectives[objectives["id"] == selected_obj_id].iloc[0]


# -----------------------------------------------------------------------------
# Objective header card
# -----------------------------------------------------------------------------
ou_name = ou_name_by_id.get(selected_obj["org_unit_id"], "?")
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

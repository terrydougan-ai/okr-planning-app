"""
Initiatives — initiative-centric workspace.

This is the operational home for initiatives:
  * View the portfolio with status / org / KR-count summaries.
  * Edit each initiative's core fields (title, owner, status, milestone, effort,
    progress, description) inline.
  * Manage KR links from the initiative side: edit predicted/actual impact per
    link, unlink, or link to additional KRs (cross-objective is fine).
  * Edit the business case.
  * Delete (with cascade-aware confirmation).

Why this page exists as an editor (not just a viewer):
  Initiatives are first-class objects. Plan a Quarter buries them four levels
  deep inside KR cards, which makes sense when you're working FROM a KR — but
  awkward when the initiative is what you're working ON, especially for multi-
  KR initiatives where there's no single "right" KR to drill through.

Delivery, impact, and ROI stay as three distinct measurements throughout —
never collapsed into a single "health" score.
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client


# Constants — kept in sync with Plan a Quarter so values mean the same thing.
INIT_STATUSES = ["proposed", "active", "done", "killed"]
MILESTONE_STATUSES = ["on_track", "at_risk", "blocked"]
EFFORT_SIZES = ["", "XS", "S", "M", "L", "XL"]


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
        "initiatives": pd.DataFrame(sb.table("initiative").select("*").execute().data),
        "links": pd.DataFrame(sb.table("initiative_key_result").select("*").execute().data),
        "key_results": pd.DataFrame(sb.table("key_result").select("*").execute().data),
        "objectives": pd.DataFrame(sb.table("objective").select("*").execute().data),
        "org_units": pd.DataFrame(sb.table("org_unit").select("*").execute().data),
        "business_cases": pd.DataFrame(sb.table("business_case").select("*").execute().data),
    }


def clear_cache():
    load_all.clear()


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
    if num is None or denom is None or pd.isna(num) or pd.isna(denom) or denom == 0:
        return "—"
    return f"{num / denom:.1f}x"


def safe_str(v) -> str:
    return v if isinstance(v, str) else ""


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("🚀 Initiatives")
st.caption(
    "The portfolio of bets and the workspace for editing them. "
    "Delivery, impact, and ROI shown as three distinct measurements — "
    "never collapsed."
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
    st.warning("No initiatives yet. Add one via **Plan a Quarter** under any KR.")
    st.stop()

# Lookups
kr_by_id = key_results.set_index("id").to_dict("index") if not key_results.empty else {}
obj_by_id = objectives.set_index("id").to_dict("index") if not objectives.empty else {}
ou_name_by_id = org_units.set_index("id")["name"].to_dict() if not org_units.empty else {}
ou_id_by_name = {v: k for k, v in ou_name_by_id.items()}
bc_by_init = (
    business_cases.set_index("initiative_id").to_dict("index")
    if not business_cases.empty
    else {}
)


# -----------------------------------------------------------------------------
# In-page filters
# -----------------------------------------------------------------------------
# Initiatives don't have a direct org_unit_id — they belong to objectives via
# their KR links. Filtering by org means: "initiatives moving at least one KR
# whose objective is in this org unit."
all_orgs = ["All org units"] + sorted(ou_name_by_id.values())
_saved_org_id = st.session_state.get("scope_org_id")
_default_org_label = "All org units"
if _saved_org_id and _saved_org_id in ou_name_by_id:
    _candidate_name = ou_name_by_id[_saved_org_id]
    if _candidate_name in all_orgs:
        _default_org_label = _candidate_name
_default_org_idx = all_orgs.index(_default_org_label)

all_statuses = ["all"] + INIT_STATUSES

fc1, fc2 = st.columns([2, 1])
with fc1:
    org_filter = st.selectbox(
        "**Org unit**",
        options=all_orgs,
        index=_default_org_idx,
        help=(
            "Filter to initiatives moving at least one KR in this org unit's "
            "objectives. Persists across pages."
        ),
    )
with fc2:
    status_filter = st.selectbox(
        "**Status**",
        options=all_statuses,
        index=0,
        format_func=lambda s: status_badge(s) if s != "all" else "All statuses",
    )

# Persist org scope (specific selections only — "All" doesn't propagate)
if org_filter != "All org units" and org_filter in ou_id_by_name:
    st.session_state["scope_org_id"] = ou_id_by_name[org_filter]
    st.session_state["scope_org_name"] = org_filter


# -----------------------------------------------------------------------------
# Apply filters
# -----------------------------------------------------------------------------
visible = initiatives.copy()
if status_filter != "all":
    visible = visible[visible["status"] == status_filter]

if org_filter != "All org units":
    filter_org_id = ou_id_by_name.get(org_filter)
    if filter_org_id is not None:
        # KRs whose objective is in this org
        objs_in_org = (
            objectives[objectives["org_unit_id"] == filter_org_id]
            if not objectives.empty else pd.DataFrame()
        )
        obj_ids_in_org = set(objs_in_org["id"]) if not objs_in_org.empty else set()
        krs_in_org = (
            key_results[key_results["objective_id"].isin(obj_ids_in_org)]
            if obj_ids_in_org and not key_results.empty else pd.DataFrame()
        )
        kr_ids_in_org = set(krs_in_org["id"]) if not krs_in_org.empty else set()
        init_ids_in_org = (
            set(links[links["key_result_id"].isin(kr_ids_in_org)]["initiative_id"].tolist())
            if kr_ids_in_org and not links.empty else set()
        )
        visible = visible[visible["id"].isin(init_ids_in_org)]


if visible.empty:
    st.info(
        f"No initiatives match these filters "
        f"(org: {org_filter}, status: {status_filter})."
    )
    st.stop()


# -----------------------------------------------------------------------------
# Summary strip
# -----------------------------------------------------------------------------
total_predicted_value = 0.0
total_predicted_cost = 0.0
for _, init in visible.iterrows():
    bc = bc_by_init.get(init["id"])
    if bc:
        v = bc.get("predicted_value") or 0
        c = bc.get("predicted_cost") or 0
        total_predicted_value += v
        total_predicted_cost += c

sc1, sc2, sc3, sc4 = st.columns(4)
sc1.metric("Initiatives shown", len(visible))
sc2.metric("Predicted value", fmt_money(total_predicted_value))
sc3.metric("Predicted cost", fmt_money(total_predicted_cost))
sc4.metric("Portfolio ROI", fmt_ratio(total_predicted_value, total_predicted_cost))

st.caption(
    "_Portfolio ROI is a naive sum across business cases — "
    "see note on attribution at the bottom._"
)

st.divider()


# -----------------------------------------------------------------------------
# Per-initiative editable cards (collapsed by default)
# -----------------------------------------------------------------------------
# Sort by status (active first, then proposed, then done/killed), then by # of
# KRs moved (descending), so the bets most worth looking at surface at the top.
status_rank = {"active": 0, "proposed": 1, "done": 2, "killed": 3}
sorted_initiatives = []
for _, init in visible.iterrows():
    init_links_local = links[links["initiative_id"] == init["id"]] if not links.empty else pd.DataFrame()
    sorted_initiatives.append({
        "init": init,
        "kr_count": len(init_links_local),
        "rank": status_rank.get(init.get("status"), 99),
    })
sorted_initiatives.sort(key=lambda x: (x["rank"], -x["kr_count"], safe_str(x["init"].get("title"))))


for entry in sorted_initiatives:
    init = entry["init"]
    init_id = init["id"]
    kr_count_for_header = entry["kr_count"]

    multi_kr_tag = (
        f"  ·  📌 moves {kr_count_for_header} KRs"
        if kr_count_for_header > 1 else ""
    )
    header = (
        f"{status_badge(init['status'])}  ·  "
        f"{milestone_badge(init.get('milestone_status'))}  —  "
        f"**{init['title']}**{multi_kr_tag}"
    )

    with st.expander(header, expanded=False):
        # ----- Core fields edit form ------------------------------------
        with st.form(f"edit_init_core_{init_id}"):
            ec1, ec2 = st.columns([3, 1])
            with ec1:
                ei_title = st.text_input("Title", value=init["title"])
            with ec2:
                ei_owner = st.text_input("Owner", value=init.get("owner") or "")

            ec3, ec4, ec5, ec6 = st.columns(4)
            with ec3:
                ei_status = st.selectbox(
                    "Status",
                    options=INIT_STATUSES,
                    index=INIT_STATUSES.index(init.get("status", "proposed"))
                    if init.get("status") in INIT_STATUSES else 0,
                )
            with ec4:
                cur_ms = init.get("milestone_status")
                ms_opts = [""] + MILESTONE_STATUSES
                ei_ms = st.selectbox(
                    "Milestone",
                    options=ms_opts,
                    index=ms_opts.index(cur_ms) if cur_ms in ms_opts else 0,
                    help=(
                        "Owner's judgment of execution health. Separate from "
                        "KR progress — an initiative can be 'on track' while "
                        "its KRs are slipping (or vice versa)."
                    ),
                )
            with ec5:
                cur_effort = init.get("effort_estimate") or ""
                ei_effort = st.selectbox(
                    "Effort",
                    options=EFFORT_SIZES,
                    index=EFFORT_SIZES.index(cur_effort)
                    if cur_effort in EFFORT_SIZES else 0,
                )
            with ec6:
                ei_progress = st.number_input(
                    "Delivery %",
                    min_value=0.0, max_value=100.0,
                    value=float(init.get("progress_pct") or 0),
                    step=5.0,
                )

            ei_desc = st.text_area(
                "Description",
                value=init.get("description") or "",
                height=80,
            )

            save_core = st.form_submit_button("💾 Save initiative", type="primary")
            if save_core:
                if not ei_title.strip():
                    st.error("Title is required.")
                else:
                    try:
                        sb.table("initiative").update({
                            "title": ei_title.strip(),
                            "owner": ei_owner.strip() or None,
                            "status": ei_status,
                            "milestone_status": ei_ms or None,
                            "effort_estimate": ei_effort or None,
                            "progress_pct": ei_progress,
                            "description": ei_desc.strip() or None,
                        }).eq("id", init_id).execute()
                        clear_cache()
                        st.success("Initiative saved.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Update failed: {e}")

        # Delivery progress bar (read-only visualization of the saved value)
        st.progress((init.get("progress_pct") or 0) / 100)

        # ----- Linked KRs section ---------------------------------------
        st.markdown("---")
        st.markdown("**Linked Key Results (impact layer)**")

        init_links = links[links["initiative_id"] == init_id] if not links.empty else pd.DataFrame()

        if init_links.empty:
            st.info(
                "No KRs linked. This initiative isn't aimed at a measurable "
                "outcome — link it to at least one KR below."
            )
        else:
            for _, lk in init_links.iterrows():
                kr_id = lk["key_result_id"]
                kr = kr_by_id.get(kr_id, {})
                obj = obj_by_id.get(kr.get("objective_id"), {})
                ou_name = ou_name_by_id.get(obj.get("org_unit_id"), "—")
                kr_unit = kr.get("metric_unit") or ""
                kr_title = kr.get("title", "?")

                # KR header + unlink button on the right
                lkr_c1, lkr_c2 = st.columns([4, 1])
                with lkr_c1:
                    st.markdown(
                        f"**{kr_title}** "
                        f"<span style='color:#6B7280;font-size:0.85em'>"
                        f"({ou_name} · target {kr.get('target_value')} {kr_unit})"
                        f"</span>",
                        unsafe_allow_html=True,
                    )
                with lkr_c2:
                    unlink_confirm_key = f"init_unlink_{init_id}_{kr_id}"
                    if st.session_state.get(unlink_confirm_key):
                        if st.button(
                            "✓ Confirm unlink",
                            key=f"init_unlink_do_{init_id}_{kr_id}",
                            use_container_width=True,
                        ):
                            try:
                                sb.table("initiative_key_result").delete().eq(
                                    "initiative_id", init_id
                                ).eq("key_result_id", kr_id).execute()
                                st.session_state.pop(unlink_confirm_key, None)
                                clear_cache()
                                st.success(f"Unlinked from **{kr_title}**.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Unlink failed: {e}")
                    else:
                        if st.button(
                            "🔗 Unlink",
                            key=f"init_unlink_ask_{init_id}_{kr_id}",
                            use_container_width=True,
                        ):
                            st.session_state[unlink_confirm_key] = True
                            st.rerun()

                # Edit predicted / actual impact for this link
                with st.form(f"edit_link_{init_id}_{kr_id}"):
                    pi1, pi2 = st.columns(2)
                    with pi1:
                        link_predicted = st.number_input(
                            f"Predicted Δ ({kr_unit})",
                            value=float(lk.get("predicted_kr_impact") or 0),
                            step=1.0,
                            format="%.2f",
                            key=f"pred_{init_id}_{kr_id}",
                            help=(
                                "Absolute change in the KR's value. Not a "
                                "weight or percentage."
                            ),
                        )
                        kr_current = kr.get("current_value") or 0
                        kr_target = kr.get("target_value") or 0
                        projected = kr_current + link_predicted
                        st.caption(
                            f"→ moves KR from **{kr_current} {kr_unit}** to "
                            f"**{projected:g} {kr_unit}** (target {kr_target} {kr_unit})"
                        )
                    with pi2:
                        link_actual = st.number_input(
                            f"Actual Δ ({kr_unit})",
                            value=float(lk.get("actual_kr_impact") or 0),
                            step=1.0,
                            format="%.2f",
                            key=f"act_{init_id}_{kr_id}",
                            help="Measured change after the initiative ran.",
                        )
                    save_link = st.form_submit_button("💾 Save impact")
                    if save_link:
                        try:
                            sb.table("initiative_key_result").update({
                                "predicted_kr_impact": link_predicted if link_predicted != 0 else None,
                                "actual_kr_impact": link_actual if link_actual != 0 else None,
                            }).eq("initiative_id", init_id).eq("key_result_id", kr_id).execute()
                            clear_cache()
                            st.success("Impact saved.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Save failed: {e}")

        # ----- Link to an additional KR ---------------------------------
        # Show all KRs not already linked to this initiative. Group display
        # by org unit so the picker is navigable when there are many KRs.
        already_linked_kr_ids = set(init_links["key_result_id"].tolist()) if not init_links.empty else set()
        linkable_krs = (
            key_results[~key_results["id"].isin(already_linked_kr_ids)]
            if not key_results.empty else pd.DataFrame()
        )
        if not linkable_krs.empty:
            with st.expander("🔗 Link an additional KR to this initiative", expanded=False):
                with st.form(f"add_link_to_init_{init_id}"):
                    # Build a labeled picker: "[Org] · KR Title (unit)"
                    link_options = []
                    link_id_by_label = {}
                    for _, candidate_kr in linkable_krs.sort_values("title").iterrows():
                        c_obj = obj_by_id.get(candidate_kr.get("objective_id"), {})
                        c_ou_name = ou_name_by_id.get(c_obj.get("org_unit_id"), "?")
                        c_unit = candidate_kr.get("metric_unit") or ""
                        c_label = f"[{c_ou_name}] · {candidate_kr['title']} ({c_unit})"
                        link_options.append(c_label)
                        link_id_by_label[c_label] = candidate_kr["id"]

                    chosen_label = st.selectbox(
                        "Pick a KR to link",
                        options=link_options,
                        help=(
                            "Cross-objective and cross-org linking is fine. "
                            "Only KRs not already linked to this initiative appear."
                        ),
                    )
                    chosen_kr_id = link_id_by_label.get(chosen_label)
                    chosen_kr = kr_by_id.get(chosen_kr_id, {}) if chosen_kr_id else {}
                    chosen_unit = chosen_kr.get("metric_unit") or ""
                    chosen_current = chosen_kr.get("current_value") or 0
                    chosen_target = chosen_kr.get("target_value") or 0

                    new_predicted = st.number_input(
                        f"Predicted Δ ({chosen_unit})",
                        value=0.0, step=1.0,
                        help=(
                            "Predicted absolute change in this KR's value "
                            "(units: same as the KR). Not a weight."
                        ),
                    )
                    projected_new = chosen_current + new_predicted
                    st.caption(
                        f"→ would move KR from **{chosen_current} {chosen_unit}** "
                        f"to **{projected_new:g} {chosen_unit}** "
                        f"(target {chosen_target} {chosen_unit})"
                    )

                    add_link_submit = st.form_submit_button("🔗 Link KR", type="primary")
                    if add_link_submit:
                        if not chosen_kr_id:
                            st.error("Pick a KR to link.")
                        else:
                            try:
                                sb.table("initiative_key_result").insert({
                                    "initiative_id": init_id,
                                    "key_result_id": chosen_kr_id,
                                    "predicted_kr_impact": new_predicted if new_predicted != 0 else None,
                                }).execute()
                                clear_cache()
                                st.success(f"Linked to KR.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Link failed: {e}")

        # ----- Business case ----------------------------------------------
        st.markdown("---")
        st.markdown("**Business case (ROI layer)**")
        bc = bc_by_init.get(init_id)

        with st.form(f"edit_bc_{init_id}"):
            bc1, bc2 = st.columns(2)
            with bc1:
                ei_pv = st.number_input(
                    "Predicted value ($)",
                    value=float((bc.get("predicted_value") if bc else None) or 0),
                    step=1000.0, format="%.0f",
                )
                ei_av = st.number_input(
                    "Actual value ($)",
                    value=float((bc.get("actual_value") if bc else None) or 0),
                    step=1000.0, format="%.0f",
                )
            with bc2:
                ei_pc = st.number_input(
                    "Predicted cost ($)",
                    value=float((bc.get("predicted_cost") if bc else None) or 0),
                    step=1000.0, format="%.0f",
                )
                ei_ac = st.number_input(
                    "Actual cost ($)",
                    value=float((bc.get("actual_cost") if bc else None) or 0),
                    step=1000.0, format="%.0f",
                )

            ei_metric = st.text_input(
                "Target metric (free text)",
                value=(bc.get("target_metric") if bc else None) or "",
                placeholder="e.g. ARR, cost saved, retention rate",
            )
            ei_munit = st.text_input(
                "Metric unit",
                value=(bc.get("target_metric_unit") if bc else None) or "",
                placeholder="$, %, count, etc.",
            )
            ei_decision = st.selectbox(
                "Decision",
                options=["pending", "approved", "rejected"],
                index=["pending", "approved", "rejected"].index(
                    (bc.get("decision") if bc else None) or "pending"
                ),
            )
            ei_summary = st.text_area(
                "Summary",
                value=(bc.get("summary") if bc else None) or "",
                height=70,
                placeholder="One-paragraph rationale for the bet.",
            )

            # Live preview
            roi_predicted_now = fmt_ratio(ei_pv, ei_pc)
            roi_actual_now = fmt_ratio(ei_av, ei_ac)
            st.caption(
                f"Planned ROI: **{roi_predicted_now}** · Realized ROI: **{roi_actual_now}**"
            )

            save_bc = st.form_submit_button("💾 Save business case")
            if save_bc:
                bc_payload = {
                    "initiative_id": init_id,
                    "predicted_value": ei_pv if ei_pv != 0 else None,
                    "actual_value": ei_av if ei_av != 0 else None,
                    "predicted_cost": ei_pc if ei_pc != 0 else None,
                    "actual_cost": ei_ac if ei_ac != 0 else None,
                    "target_metric": ei_metric.strip() or None,
                    "target_metric_unit": ei_munit.strip() or None,
                    "decision": ei_decision,
                    "summary": ei_summary.strip() or None,
                }
                try:
                    if bc:
                        # Update existing
                        sb.table("business_case").update(bc_payload).eq(
                            "initiative_id", init_id
                        ).execute()
                    else:
                        # Insert new
                        sb.table("business_case").insert(bc_payload).execute()
                    clear_cache()
                    st.success("Business case saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Save failed: {e}")

        # ----- Delete initiative -----------------------------------------
        # Hard delete cascades through initiative_key_result (per the schema's
        # on delete cascade), but business_case has cascade too. Show the
        # blast radius so the user knows what disappears.
        st.markdown("---")
        _del_blast = (
            f"{len(init_links)} KR link"
            f"{'s' if len(init_links) != 1 else ''}"
        )
        if bc:
            _del_blast += ", 1 business case"

        dc1, dc2 = st.columns([4, 1])
        with dc2:
            _del_key = f"init_del_confirm_{init_id}"
            if st.session_state.get(_del_key):
                if st.button(
                    f"⚠ Really delete? ({_del_blast})",
                    key=f"init_del_do_{init_id}",
                    use_container_width=True,
                    type="primary",
                ):
                    try:
                        sb.table("initiative").delete().eq("id", init_id).execute()
                        st.session_state.pop(_del_key, None)
                        clear_cache()
                        st.success("Initiative deleted.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")
            else:
                if st.button(
                    "🗑️ Delete initiative",
                    key=f"init_del_ask_{init_id}",
                    use_container_width=True,
                    help=(
                        "Hard delete. Removes the initiative, all KR links, "
                        "and the business case (cascade). Irreversible. To "
                        "'park' an initiative without deleting, set its "
                        "status to 'killed' above instead."
                    ),
                ):
                    st.session_state[_del_key] = True
                    st.rerun()
        with dc1:
            if st.session_state.get(_del_key):
                st.caption(
                    f"⚠ Will affect: **{_del_blast}**. Click the confirmation "
                    "button to proceed, or anywhere else to cancel."
                )


# -----------------------------------------------------------------------------
# Footnote on attribution
# -----------------------------------------------------------------------------
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
        """
    )

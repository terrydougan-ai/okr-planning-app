"""
Create Initiative — the structural management page for initiatives.

Owns:
  * Creating a new initiative from scratch
  * Editing what an initiative IS: title, owner, status, effort,
    project description, linked KRs (with predicted impact), business case
  * Deleting initiatives (with cascade-aware confirmation)

Does NOT own (those live on Initiative Updates under Track):
  * Delivery %, milestone delivery status (RAG)
  * Next major milestone text + date
  * Exec narrative + exec RAG
  * Actual KR impact

The split mirrors the rest of the app: Manage is for what something IS;
Track is for how it's GOING.
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client


INIT_STATUSES = ["proposed", "active", "done", "killed"]
EFFORT_SIZES = ["", "XS", "S", "M", "L", "XL"]


@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


sb = get_supabase()


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


def status_badge(status: str) -> str:
    return {
        "proposed": "💭 proposed",
        "active":   "🟢 active",
        "done":     "✅ done",
        "killed":   "🪦 killed",
    }.get(status, status or "—")


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
st.title("🚀 Create Initiative")
st.caption(
    "Create new initiatives and manage their structure: linked KRs, business "
    "case, ownership, status. Execution updates (milestone status, exec "
    "narrative, delivery %) live on **Track → Initiative Updates**."
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

kr_by_id = key_results.set_index("id").to_dict("index") if not key_results.empty else {}
obj_by_id = objectives.set_index("id").to_dict("index") if not objectives.empty else {}
ou_name_by_id = org_units.set_index("id")["name"].to_dict() if not org_units.empty else {}
bc_by_init = (
    business_cases.set_index("initiative_id").to_dict("index")
    if not business_cases.empty else {}
)


# Build a KR picker label that's findable across many KRs
def kr_label(kr) -> str:
    obj = obj_by_id.get(kr.get("objective_id"), {})
    ou_name = ou_name_by_id.get(obj.get("org_unit_id"), "?")
    unit = kr.get("metric_unit") or ""
    return f"[{ou_name}] · {kr['title']} ({unit})"


# Build the tree-indented org picker labels used in the create and edit forms.
# Same pattern as Plan a Quarter / Key Result Updates / etc. — keeps the
# family relationships visible at a glance when picking.
_level_order = {"company": 0, "segment": 1, "team": 2}
_children_by_parent: dict = {}
for _, _row in org_units.iterrows():
    _pid = _row["parent_unit_id"]
    if _pid != _pid:  # NaN
        _pid = None
    _children_by_parent.setdefault(_pid, []).append(_row)

org_tree_labels: list[str] = []
org_tree_label_to_id: dict = {}


def _walk_org_tree(parent_id, depth: int):
    siblings = sorted(
        _children_by_parent.get(parent_id, []),
        key=lambda r: (_level_order.get(r.get("level"), 99), r["name"]),
    )
    for r in siblings:
        prefix = "↳ " * depth
        label = f"{prefix}{r['name']}"
        org_tree_labels.append(label)
        org_tree_label_to_id[label] = r["id"]
        _walk_org_tree(r["id"], depth + 1)


_walk_org_tree(None, 0)
org_tree_id_to_label = {v: k for k, v in org_tree_label_to_id.items()}


# -----------------------------------------------------------------------------
# CREATE NEW INITIATIVE (top-of-page form)
# -----------------------------------------------------------------------------
st.divider()
st.header("➕ Create a new initiative")
st.caption(
    "Define the bet and the KR(s) it's aimed at. You can refine details "
    "(business case, additional KR links) after creation by expanding the "
    "initiative below."
)

if key_results.empty:
    st.warning(
        "No Key Results exist yet. Add at least one KR on **Plan a Quarter** "
        "or **Annual Strategy & Objectives** before creating an initiative."
    )
else:
    with st.form("create_new_init", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        with c1:
            new_title = st.text_input(
                "Title *", placeholder="e.g. Localize onboarding flow for Japan early adopters"
            )
        with c2:
            new_owner = st.text_input("Owner", placeholder="e.g. VP Product")

        # Org Unit picker (required) — establishes which team OWNS this
        # initiative for reporting purposes. Separate from KR linkage, which
        # captures what outcomes the initiative is supposed to MOVE.
        # Cross-team work: one team can own an initiative that moves another
        # team's KRs.
        # Default to sticky scope org if set
        _saved_org_id = st.session_state.get("scope_org_id")
        _default_org_idx = 0
        if _saved_org_id and _saved_org_id in org_tree_id_to_label:
            _candidate = org_tree_id_to_label[_saved_org_id]
            if _candidate in org_tree_labels:
                _default_org_idx = org_tree_labels.index(_candidate)
        new_org_label = st.selectbox(
            "Owning Org Unit *",
            options=org_tree_labels,
            index=_default_org_idx,
            help=(
                "Which team owns this initiative? Indented entries (↳) sit "
                "under the unit above them. This is the team accountable "
                "for delivery — separate from the KR(s) the initiative moves."
            ),
        )

        c3, c4 = st.columns(2)
        with c3:
            new_status = st.selectbox(
                "Status",
                options=INIT_STATUSES,
                index=INIT_STATUSES.index("proposed"),
            )
        with c4:
            new_effort = st.selectbox(
                "Effort estimate",
                options=EFFORT_SIZES,
                index=0,
            )

        new_desc = st.text_area(
            "Project Description",
            height=80,
            placeholder=(
                "What's the bet and how does it work? Keep it short — "
                "supporting detail belongs in the business case below."
            ),
        )

        # KR linking — multiselect of all KRs, with predicted impact per pick.
        # Streamlit forms can't dynamically render per-KR impact inputs based on
        # selection, so the create form keeps things simple: pick KRs at creation
        # time and set predicted impacts later by editing the initiative below.
        kr_options = []
        kr_id_by_label = {}
        for _, kr in key_results.sort_values("title").iterrows():
            lbl = kr_label(kr)
            kr_options.append(lbl)
            kr_id_by_label[lbl] = kr["id"]

        chosen_kr_labels = st.multiselect(
            "Link to KR(s) *",
            options=kr_options,
            default=[],
            help=(
                "Pick at least one KR this initiative will move. Predicted "
                "impact per KR is set later by editing the initiative."
            ),
        )

        st.markdown("**Optional business case (recommended)**")
        bc1, bc2 = st.columns(2)
        with bc1:
            new_pv = st.number_input("Predicted value ($)", value=0.0, step=1000.0, format="%.0f")
        with bc2:
            new_pc = st.number_input("Predicted cost ($)", value=0.0, step=1000.0, format="%.0f")

        # Live ROI preview
        if new_pv > 0 and new_pc > 0:
            st.caption(f"Planned ROI: **{new_pv / new_pc:.1f}x**")

        submit_new = st.form_submit_button("➕ Create initiative", type="primary")
        if submit_new:
            if not new_title.strip():
                st.error("Title is required.")
            elif not chosen_kr_labels:
                st.error("Link at least one KR.")
            else:
                try:
                    # Insert the initiative row
                    new_org_id = org_tree_label_to_id.get(new_org_label)
                    insert_result = sb.table("initiative").insert({
                        "title": new_title.strip(),
                        "owner": new_owner.strip() or None,
                        "org_unit_id": new_org_id,
                        "status": new_status,
                        "effort_estimate": new_effort or None,
                        "description": new_desc.strip() or None,
                    }).execute()
                    new_init_id = insert_result.data[0]["id"]

                    # Insert KR links (predicted impact set later via edit form)
                    linked_count = 0
                    for lbl in chosen_kr_labels:
                        kr_id = kr_id_by_label.get(lbl)
                        if kr_id:
                            try:
                                sb.table("initiative_key_result").insert({
                                    "initiative_id": new_init_id,
                                    "key_result_id": kr_id,
                                }).execute()
                                linked_count += 1
                            except Exception as e:
                                st.warning(f"Couldn't link to '{lbl}': {e}")

                    # Optional business case
                    if new_pv > 0 or new_pc > 0:
                        sb.table("business_case").insert({
                            "initiative_id": new_init_id,
                            "predicted_value": new_pv if new_pv > 0 else None,
                            "predicted_cost": new_pc if new_pc > 0 else None,
                            "decision": "pending",
                        }).execute()

                    clear_cache()
                    roi_msg = f" (ROI {new_pv/new_pc:.1f}x)" if new_pv > 0 and new_pc > 0 else ""
                    st.success(
                        f"Created **{new_title.strip()}**{roi_msg}. Linked to "
                        f"{linked_count} KR(s)."
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Create failed: {e}")


# -----------------------------------------------------------------------------
# EXISTING INITIATIVES — structural editing
# -----------------------------------------------------------------------------
st.divider()
st.header(f"Existing initiatives ({len(initiatives)})")
st.caption(
    "Expand any initiative to edit structural fields. For status, milestone, "
    "and exec updates, use **Track → Initiative Updates**."
)

if initiatives.empty:
    st.info("No initiatives yet. Use the form above to create the first one.")
else:
    # Sort by status then title for predictability
    status_rank = {"active": 0, "proposed": 1, "done": 2, "killed": 3}
    init_rows = []
    for _, init in initiatives.iterrows():
        init_links_local = links[links["initiative_id"] == init["id"]] if not links.empty else pd.DataFrame()
        init_rows.append({
            "init": init,
            "links": init_links_local,
            "rank": status_rank.get(init.get("status"), 99),
        })
    init_rows.sort(key=lambda r: (r["rank"], safe_str(r["init"].get("title")).lower()))

    for row in init_rows:
        init = row["init"]
        init_id = init["id"]
        init_links = row["links"]
        kr_count = len(init_links)

        multi_kr_tag = f"  ·  📌 {kr_count} KRs" if kr_count > 1 else ""
        header = (
            f"{status_badge(init['status'])}  —  **{init['title']}**{multi_kr_tag}"
        )

        with st.expander(header, expanded=False):
            # ---- Core structural fields ----
            with st.form(f"create_edit_core_{init_id}"):
                ec1, ec2 = st.columns([3, 1])
                with ec1:
                    ei_title = st.text_input("Title", value=init["title"])
                with ec2:
                    ei_owner = st.text_input("Owner", value=init.get("owner") or "")

                # Org Unit picker — required, but backward-compatible: existing
                # initiatives without org_unit_id show a (not set) sentinel
                # at the top of the list so they can be assigned to a team.
                _cur_ou_id = init.get("org_unit_id")
                NOT_SET = "— (not set)"
                ou_options = [NOT_SET] + org_tree_labels if not isinstance(_cur_ou_id, str) or _cur_ou_id not in org_tree_id_to_label else org_tree_labels
                _cur_label = (
                    org_tree_id_to_label.get(_cur_ou_id)
                    if isinstance(_cur_ou_id, str) else None
                )
                if _cur_label and _cur_label in ou_options:
                    _ou_idx = ou_options.index(_cur_label)
                else:
                    _ou_idx = 0
                ei_org_label = st.selectbox(
                    "Owning Org Unit",
                    options=ou_options,
                    index=_ou_idx,
                    help=(
                        "Which team owns this initiative? Separate from the "
                        "KR(s) it moves. Used by Hotspots to roll the "
                        "initiative's warnings up under the right team."
                    ),
                    key=f"create_edit_org_{init_id}",
                )

                ec3, ec4 = st.columns(2)
                with ec3:
                    ei_status = st.selectbox(
                        "Status",
                        options=INIT_STATUSES,
                        index=INIT_STATUSES.index(init.get("status", "proposed"))
                        if init.get("status") in INIT_STATUSES else 0,
                    )
                with ec4:
                    cur_effort = init.get("effort_estimate") or ""
                    ei_effort = st.selectbox(
                        "Effort",
                        options=EFFORT_SIZES,
                        index=EFFORT_SIZES.index(cur_effort)
                        if cur_effort in EFFORT_SIZES else 0,
                    )

                ei_desc = st.text_area(
                    "Project Description",
                    value=init.get("description") or "",
                    height=80,
                )

                save_core = st.form_submit_button("💾 Save core fields", type="primary")
                if save_core:
                    if not ei_title.strip():
                        st.error("Title is required.")
                    else:
                        try:
                            ei_org_id = (
                                None
                                if ei_org_label == NOT_SET
                                else org_tree_label_to_id.get(ei_org_label)
                            )
                            sb.table("initiative").update({
                                "title": ei_title.strip(),
                                "owner": ei_owner.strip() or None,
                                "org_unit_id": ei_org_id,
                                "status": ei_status,
                                "effort_estimate": ei_effort or None,
                                "description": ei_desc.strip() or None,
                            }).eq("id", init_id).execute()
                            clear_cache()
                            st.success("Core fields saved.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Update failed: {e}")

            # ---- Linked KRs (structural — which KRs + predicted impact) ----
            st.markdown("---")
            st.markdown("**Linked Key Results** &nbsp; *(structural: which KRs + predicted impact)*", unsafe_allow_html=True)

            if init_links.empty:
                st.info("No KRs linked yet — link at least one below.")
            else:
                for _, lk in init_links.iterrows():
                    kr_id = lk["key_result_id"]
                    kr = kr_by_id.get(kr_id, {})
                    obj = obj_by_id.get(kr.get("objective_id"), {})
                    ou_name = ou_name_by_id.get(obj.get("org_unit_id"), "—")
                    kr_unit = kr.get("metric_unit") or ""
                    kr_title = kr.get("title", "?")

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
                        unlink_key = f"create_unlink_{init_id}_{kr_id}"
                        if st.session_state.get(unlink_key):
                            if st.button(
                                "✓ Confirm unlink",
                                key=f"create_unlink_do_{init_id}_{kr_id}",
                                use_container_width=True,
                            ):
                                try:
                                    sb.table("initiative_key_result").delete().eq(
                                        "initiative_id", init_id
                                    ).eq("key_result_id", kr_id).execute()
                                    st.session_state.pop(unlink_key, None)
                                    clear_cache()
                                    st.success(f"Unlinked from **{kr_title}**.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Unlink failed: {e}")
                        else:
                            if st.button(
                                "🔗 Unlink",
                                key=f"create_unlink_ask_{init_id}_{kr_id}",
                                use_container_width=True,
                            ):
                                st.session_state[unlink_key] = True
                                st.rerun()

                    # Predicted impact for this link (structural)
                    with st.form(f"create_edit_predicted_{init_id}_{kr_id}"):
                        link_predicted = st.number_input(
                            f"Predicted Δ ({kr_unit})",
                            value=float(lk.get("predicted_kr_impact") or 0),
                            step=1.0, format="%.2f",
                            key=f"create_pred_{init_id}_{kr_id}",
                            help=(
                                "Absolute change in the KR's value (units: "
                                f"{kr_unit or 'see KR'}). Not a weight."
                            ),
                        )
                        kr_current = kr.get("current_value") or 0
                        kr_target = kr.get("target_value") or 0
                        projected = kr_current + link_predicted
                        st.caption(
                            f"→ moves KR from **{kr_current} {kr_unit}** to "
                            f"**{projected:g} {kr_unit}** (target {kr_target} {kr_unit})"
                        )
                        save_link = st.form_submit_button("💾 Save predicted impact")
                        if save_link:
                            try:
                                sb.table("initiative_key_result").update({
                                    "predicted_kr_impact": link_predicted if link_predicted != 0 else None,
                                }).eq("initiative_id", init_id).eq("key_result_id", kr_id).execute()
                                clear_cache()
                                st.success("Predicted impact saved.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Save failed: {e}")

            # Link an additional KR
            already_linked_ids = set(init_links["key_result_id"].tolist()) if not init_links.empty else set()
            linkable_krs = (
                key_results[~key_results["id"].isin(already_linked_ids)]
                if not key_results.empty else pd.DataFrame()
            )
            if not linkable_krs.empty:
                with st.expander("🔗 Link an additional KR", expanded=False):
                    with st.form(f"create_add_link_{init_id}"):
                        opts = []
                        opts_id_by_lbl = {}
                        for _, ckr in linkable_krs.sort_values("title").iterrows():
                            lbl = kr_label(ckr)
                            opts.append(lbl)
                            opts_id_by_lbl[lbl] = ckr["id"]
                        chosen_lbl = st.selectbox("Pick a KR to link", options=opts)
                        chosen_kr_id = opts_id_by_lbl.get(chosen_lbl)
                        chosen_kr = kr_by_id.get(chosen_kr_id, {}) if chosen_kr_id else {}
                        chosen_unit = chosen_kr.get("metric_unit") or ""
                        chosen_current = chosen_kr.get("current_value") or 0
                        chosen_target = chosen_kr.get("target_value") or 0

                        new_pred = st.number_input(
                            f"Predicted Δ ({chosen_unit})", value=0.0, step=1.0,
                        )
                        st.caption(
                            f"→ would move KR from **{chosen_current} {chosen_unit}** "
                            f"to **{chosen_current + new_pred:g} {chosen_unit}** "
                            f"(target {chosen_target} {chosen_unit})"
                        )
                        add_submit = st.form_submit_button("🔗 Link KR", type="primary")
                        if add_submit and chosen_kr_id:
                            try:
                                sb.table("initiative_key_result").insert({
                                    "initiative_id": init_id,
                                    "key_result_id": chosen_kr_id,
                                    "predicted_kr_impact": new_pred if new_pred != 0 else None,
                                }).execute()
                                clear_cache()
                                st.success("Linked.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Link failed: {e}")

            # ---- Business case (structural — predicted value/cost, decision, summary) ----
            st.markdown("---")
            st.markdown("**Business case** &nbsp; *(structural: predicted value, cost, decision, rationale)*", unsafe_allow_html=True)
            bc = bc_by_init.get(init_id)

            with st.form(f"create_edit_bc_{init_id}"):
                bcc1, bcc2 = st.columns(2)
                with bcc1:
                    ei_pv = st.number_input(
                        "Predicted value ($)",
                        value=float((bc.get("predicted_value") if bc else None) or 0),
                        step=1000.0, format="%.0f",
                    )
                with bcc2:
                    ei_pc = st.number_input(
                        "Predicted cost ($)",
                        value=float((bc.get("predicted_cost") if bc else None) or 0),
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

                st.caption(
                    f"Planned ROI: **{fmt_ratio(ei_pv, ei_pc)}**"
                )

                save_bc = st.form_submit_button("💾 Save business case")
                if save_bc:
                    payload = {
                        "initiative_id": init_id,
                        "predicted_value": ei_pv if ei_pv != 0 else None,
                        "predicted_cost": ei_pc if ei_pc != 0 else None,
                        "target_metric": ei_metric.strip() or None,
                        "target_metric_unit": ei_munit.strip() or None,
                        "decision": ei_decision,
                        "summary": ei_summary.strip() or None,
                    }
                    try:
                        if bc:
                            sb.table("business_case").update(payload).eq(
                                "initiative_id", init_id
                            ).execute()
                        else:
                            sb.table("business_case").insert(payload).execute()
                        clear_cache()
                        st.success("Business case saved.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Save failed: {e}")

            # ---- Delete ----
            st.markdown("---")
            _del_blast = f"{len(init_links)} KR link{'s' if len(init_links) != 1 else ''}"
            if bc:
                _del_blast += ", 1 business case"

            dc1, dc2 = st.columns([4, 1])
            with dc2:
                _del_key = f"create_del_confirm_{init_id}"
                if st.session_state.get(_del_key):
                    if st.button(
                        f"⚠ Really delete? ({_del_blast})",
                        key=f"create_del_do_{init_id}",
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
                        key=f"create_del_ask_{init_id}",
                        use_container_width=True,
                        help=(
                            "Hard delete. Removes the initiative, all KR links, "
                            "and the business case (cascade). Irreversible."
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
# Footer
# -----------------------------------------------------------------------------
st.divider()
st.caption(
    "This page is for what an initiative IS. To update how it's GOING — "
    "milestone status, exec narrative, delivery percentage — head over to "
    "**Track → Initiative Updates**."
)

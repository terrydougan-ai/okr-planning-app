"""
Initiative Updates — execution reporting surface for initiatives.

Owns the questions "how's it going?" and "what should execs know?":
  * Delivery % (progress bar)
  * Milestone Delivery Status (🟢🟡🔴🚧)
  * Next Major Milestone + date
  * Exec narrative (free text — what execs should know)
  * Exec RAG (🟢🟡🔴🚧 — owner's curated outward signal, can differ from
    Milestone Delivery Status which is the internal team's view)
  * Actual KR impact per linked KR (measurement, not prediction)

Does NOT own (those live on Manage → Create Initiative):
  * Title, owner, status (proposed/active/done/killed), effort
  * Project description
  * Which KRs are linked (and predicted impacts)
  * Business case predicted value/cost, decision, summary
  * Delete

The split mirrors the rest of the app: Manage is for what something IS;
Track is for how it's GOING.
"""

import streamlit as st
import pandas as pd
from datetime import date
from supabase import create_client, Client


# Display vocabulary — the four RAG-ish states for delivery health.
# Stored in DB as the keys below; rendered as the friendlier labels.
DELIVERY_STATES = ["", "on_track", "at_risk", "off_track", "blocked"]
DELIVERY_LABELS = {
    "":          "—  (not set)",
    "on_track":  "🟢  On Track",
    "at_risk":   "🟡  At Risk",
    "off_track": "🔴  Off Track",
    "blocked":   "🚧  Blocked",
}
DELIVERY_ICONS = {
    "on_track":  "🟢",
    "at_risk":   "🟡",
    "off_track": "🔴",
    "blocked":   "🚧",
}

INIT_STATUSES = ["proposed", "active", "done", "killed"]


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


def delivery_icon(v) -> str:
    """Just the icon, used in card headers."""
    if not isinstance(v, str):
        return "⚪"
    return DELIVERY_ICONS.get(v, "⚪")


def safe_str(v) -> str:
    return v if isinstance(v, str) else ""


def parse_date(v):
    """Try to parse a date value from DB; return None if not a real date."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, date):
        return v
    try:
        return pd.to_datetime(v).date()
    except Exception:
        return None


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("📊 Initiative Updates")
st.caption(
    "Weekly/monthly execution reporting. Update delivery %, milestone "
    "status, exec narrative, and actual KR impact. Structural changes "
    "(title, KR links, business case) live on **Manage → Create Initiative**."
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

if initiatives.empty:
    st.warning(
        "No initiatives yet. Create one on **Manage → Create Initiative**."
    )
    st.stop()

kr_by_id = key_results.set_index("id").to_dict("index") if not key_results.empty else {}
obj_by_id = objectives.set_index("id").to_dict("index") if not objectives.empty else {}
ou_name_by_id = org_units.set_index("id")["name"].to_dict() if not org_units.empty else {}
ou_id_by_name = {v: k for k, v in ou_name_by_id.items()}


# -----------------------------------------------------------------------------
# In-page filters (org + owner + status)
# -----------------------------------------------------------------------------
# Org dropdown uses the same tree-indented format as Plan a Quarter / Annual /
# etc., so family relationships are visible at a glance.
level_order = {"company": 0, "segment": 1, "team": 2}
children_by_parent: dict = {}
for _, row in org_units.iterrows():
    pid = row["parent_unit_id"]
    if pid != pid:
        pid = None
    children_by_parent.setdefault(pid, []).append(row)

org_tree_labels: list[str] = []
tree_label_to_id: dict = {}


def _walk_org_tree(parent_id, depth: int):
    siblings = sorted(
        children_by_parent.get(parent_id, []),
        key=lambda r: (level_order.get(r.get("level"), 99), r["name"]),
    )
    for r in siblings:
        prefix = "↳ " * depth
        label = f"{prefix}{r['name']}"
        org_tree_labels.append(label)
        tree_label_to_id[label] = r["id"]
        _walk_org_tree(r["id"], depth + 1)


_walk_org_tree(None, 0)
# Prepend the "All" meta-option so the cross-org bird's-eye view is still
# the easy zero-click default.
ALL_ORGS_LABEL = "All org units"
org_dropdown_options = [ALL_ORGS_LABEL] + org_tree_labels

# Default to sticky scope org if set
_saved_org_id = st.session_state.get("scope_org_id")
_default_org_idx = 0  # "All org units"
if _saved_org_id:
    for _i, _lbl in enumerate(org_dropdown_options):
        if tree_label_to_id.get(_lbl) == _saved_org_id:
            _default_org_idx = _i
            break

# Owners pulled from the initiatives table (de-duped, sorted). Initiatives with
# no owner get filtered as "No owner."
owner_values = sorted(
    {
        o for o in initiatives["owner"].dropna().tolist()
        if isinstance(o, str) and o.strip()
    }
)
NO_OWNER_LABEL = "— No owner set"
ALL_OWNERS_LABEL = "All owners"
owner_dropdown_options = [ALL_OWNERS_LABEL] + owner_values + [NO_OWNER_LABEL]

all_statuses = ["all"] + INIT_STATUSES

fc1, fc2, fc3 = st.columns([2, 1.2, 1])
with fc1:
    selected_org_label = st.selectbox(
        "**Org unit**",
        options=org_dropdown_options,
        index=_default_org_idx,
        help=(
            "Show initiatives moving KRs in this org. Indented entries (↳) "
            "sit under the unit above them. Persists across pages."
        ),
    )
with fc2:
    selected_owner = st.selectbox(
        "**Owner**",
        options=owner_dropdown_options,
        index=0,
        help=(
            "Filter to initiatives owned by a specific person, or pick "
            f"'{NO_OWNER_LABEL}' to surface initiatives with no owner "
            "assigned."
        ),
    )
with fc3:
    status_filter = st.selectbox(
        "**Status**",
        options=all_statuses,
        index=0,
        format_func=lambda s: status_badge(s) if s != "all" else "All statuses",
    )

# Persist org scope (selecting "All" clears it so other pages default broad too)
if selected_org_label != ALL_ORGS_LABEL:
    _scope_id = tree_label_to_id.get(selected_org_label)
    if _scope_id:
        st.session_state["scope_org_id"] = _scope_id
        # Find raw org name (strip the ↳ prefix) for the sidebar indicator
        st.session_state["scope_org_name"] = ou_name_by_id.get(_scope_id, selected_org_label)
else:
    st.session_state.pop("scope_org_id", None)
    st.session_state.pop("scope_org_name", None)


# Apply filters
visible = initiatives.copy()
if status_filter != "all":
    visible = visible[visible["status"] == status_filter]

if selected_org_label != ALL_ORGS_LABEL:
    filter_org_id = tree_label_to_id.get(selected_org_label)
    if filter_org_id is not None:
        # Build the family (self + descendants). Picking "Acme Analytics"
        # should include Product, Go-to-Market, Platform — mirrors Hotspots.
        _children_by_parent: dict = {}
        for _, _row in org_units.iterrows():
            _pid = _row["parent_unit_id"]
            if _pid != _pid:  # NaN check
                _pid = None
            _children_by_parent.setdefault(_pid, []).append(_row["id"])

        family_ids = {filter_org_id}
        _stack = list(_children_by_parent.get(filter_org_id, []))
        while _stack:
            _cid = _stack.pop()
            if _cid in family_ids:
                continue
            family_ids.add(_cid)
            _stack.extend(_children_by_parent.get(_cid, []))

        # Two paths to include an initiative in scope:
        #   1. It's linked (via KR) to a KR whose objective is under a family org
        #   2. It's directly owned by a family org (initiative.org_unit_id in family)
        # An initiative can qualify via either path — mirrors Hotspots.
        objs_in_family = (
            objectives[objectives["org_unit_id"].isin(family_ids)]
            if not objectives.empty else pd.DataFrame()
        )
        obj_ids_in_family = set(objs_in_family["id"]) if not objs_in_family.empty else set()
        krs_in_family = (
            key_results[key_results["objective_id"].isin(obj_ids_in_family)]
            if obj_ids_in_family and not key_results.empty else pd.DataFrame()
        )
        kr_ids_in_family = set(krs_in_family["id"]) if not krs_in_family.empty else set()
        linked_init_ids = (
            set(links[links["key_result_id"].isin(kr_ids_in_family)]["initiative_id"].tolist())
            if kr_ids_in_family and not links.empty else set()
        )
        # Directly-owned initiatives
        if "org_unit_id" in visible.columns:
            owned_init_ids = set(
                visible[visible["org_unit_id"].isin(family_ids)]["id"].tolist()
            )
        else:
            owned_init_ids = set()
        in_family_init_ids = linked_init_ids | owned_init_ids
        visible = visible[visible["id"].isin(in_family_init_ids)]

if selected_owner == NO_OWNER_LABEL:
    # NaN-safe "owner is empty" filter
    visible = visible[
        visible["owner"].isna()
        | (visible["owner"].fillna("").str.strip() == "")
    ]
elif selected_owner != ALL_OWNERS_LABEL:
    visible = visible[visible["owner"] == selected_owner]

if visible.empty:
    st.info(
        f"No initiatives match these filters "
        f"(org: {selected_org_label}, owner: {selected_owner}, "
        f"status: {status_filter})."
    )
    st.stop()


# -----------------------------------------------------------------------------
# Roll-up strip — Milestone Delivery Status counts (team's internal view)
# -----------------------------------------------------------------------------
st.divider()
st.markdown("**Roll-up by Milestone Delivery Status** &nbsp; *(team's internal view of execution health)*", unsafe_allow_html=True)
counts = {"on_track": 0, "at_risk": 0, "off_track": 0, "blocked": 0, "unset": 0}
for _, init in visible.iterrows():
    ms = init.get("milestone_status")
    if isinstance(ms, str) and ms in counts:
        counts[ms] += 1
    else:
        counts["unset"] += 1

rc1, rc2, rc3, rc4, rc5 = st.columns(5)
rc1.metric("🟢 On Track", counts["on_track"])
rc2.metric("🟡 At Risk", counts["at_risk"])
rc3.metric("🔴 Off Track", counts["off_track"])
rc4.metric("🚧 Blocked", counts["blocked"])
rc5.metric("— Not set", counts["unset"])


# -----------------------------------------------------------------------------
# Per-initiative cards — collapsed by default
# -----------------------------------------------------------------------------
# Sort by milestone severity (worst first — blocked > off_track > at_risk >
# on_track > unset), so things that need attention surface at the top of a
# weekly review.
ms_rank = {"blocked": 0, "off_track": 1, "at_risk": 2, "on_track": 3}
def _sort_key(init):
    ms = init.get("milestone_status")
    return (
        ms_rank.get(ms, 99),
        safe_str(init.get("title")).lower(),
    )
visible_sorted = visible.copy()
visible_sorted["__sk"] = visible_sorted.apply(_sort_key, axis=1)
visible_sorted = visible_sorted.sort_values("__sk")


st.divider()
for _, init in visible_sorted.iterrows():
    init_id = init["id"]
    init_links = links[links["initiative_id"] == init_id] if not links.empty else pd.DataFrame()
    kr_count = len(init_links)

    ms_icon = delivery_icon(init.get("milestone_status"))
    exec_icon = delivery_icon(init.get("exec_rag"))
    multi_tag = f"  ·  📌 {kr_count} KRs" if kr_count > 1 else ""
    # Labels in front of each icon so it's obvious which RAG is which —
    # the team's view (Milestone Delivery Status) vs the curated outward
    # signal (Exec RAG). Without labels, the two icons are ambiguous.
    header = (
        f"Milestone {ms_icon}  ·  Exec {exec_icon}  —  "
        f"**{init['title']}**{multi_tag}"
    )

    with st.expander(header, expanded=False):
        # Context line (read-only) — what this initiative IS
        st.caption(
            f"Status: **{status_badge(init.get('status'))}**  ·  "
            f"Owner: **{init.get('owner') or '—'}**  ·  "
            f"Effort: **{init.get('effort_estimate') or '—'}**"
        )
        if init.get("description"):
            with st.expander("Project description", expanded=False):
                st.write(init["description"])

        # ---- Update form: the things this page exists to update ----
        with st.form(f"update_init_{init_id}"):
            # Delivery %
            ui_progress = st.slider(
                "Delivery %",
                min_value=0, max_value=100,
                value=int(init.get("progress_pct") or 0),
                step=5,
                help="How much of the work is done?",
            )

            # Milestone Delivery Status (RAG of execution health)
            cur_ms = init.get("milestone_status")
            cur_ms_idx = DELIVERY_STATES.index(cur_ms) if isinstance(cur_ms, str) and cur_ms in DELIVERY_STATES else 0
            ui_ms = st.selectbox(
                "Milestone Delivery Status",
                options=DELIVERY_STATES,
                index=cur_ms_idx,
                format_func=lambda s: DELIVERY_LABELS.get(s, s),
                help=(
                    "Internal team view of how execution is going. Can differ "
                    "from Exec RAG below — Exec RAG is the curated outward signal."
                ),
            )

            # Next Major Milestone (text + date)
            um1, um2 = st.columns([3, 1])
            with um1:
                ui_next_ms_text = st.text_input(
                    "Next Major Milestone",
                    value=safe_str(init.get("next_milestone_text")),
                    placeholder="e.g. Onboarding redesign deployed to 100% of new signups",
                )
            with um2:
                cur_date = parse_date(init.get("next_milestone_date"))
                ui_next_ms_date = st.date_input(
                    "Milestone date",
                    value=cur_date,
                    format="YYYY-MM-DD",
                )

            st.markdown("---")
            st.markdown("**Exec reporting**")

            # Exec RAG
            cur_exec = init.get("exec_rag")
            cur_exec_idx = DELIVERY_STATES.index(cur_exec) if isinstance(cur_exec, str) and cur_exec in DELIVERY_STATES else 0
            ui_exec_rag = st.selectbox(
                "Exec RAG",
                options=DELIVERY_STATES,
                index=cur_exec_idx,
                format_func=lambda s: DELIVERY_LABELS.get(s, s),
                help=(
                    "The owner's curated signal for exec reporting. Often "
                    "matches Milestone Delivery Status, but the owner may "
                    "choose to surface a different signal externally."
                ),
            )

            # Exec narrative
            ui_exec_narrative = st.text_area(
                "Exec narrative",
                value=safe_str(init.get("exec_narrative")),
                height=80,
                placeholder=(
                    "What should execs know about this initiative right "
                    "now? Risks, asks, key context. 2–4 sentences."
                ),
            )

            save_updates = st.form_submit_button("💾 Save updates", type="primary")
            if save_updates:
                payload = {
                    "progress_pct": ui_progress,
                    "milestone_status": ui_ms or None,
                    "next_milestone_text": ui_next_ms_text.strip() or None,
                    "next_milestone_date": ui_next_ms_date.isoformat() if ui_next_ms_date else None,
                    "exec_rag": ui_exec_rag or None,
                    "exec_narrative": ui_exec_narrative.strip() or None,
                }
                try:
                    sb.table("initiative").update(payload).eq("id", init_id).execute()
                    clear_cache()
                    st.success("Updates saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Save failed: {e}")

        # Delivery progress bar (visualization of what's stored)
        st.progress((init.get("progress_pct") or 0) / 100)

        # ---- Actual KR impact per link ----
        st.markdown("---")
        st.markdown("**Actual KR impact** &nbsp; *(measurement: what each linked KR actually moved by)*", unsafe_allow_html=True)

        if init_links.empty:
            st.info("No KRs linked. Link them on **Manage → Create Initiative**.")
        else:
            for _, lk in init_links.iterrows():
                kr_id = lk["key_result_id"]
                kr = kr_by_id.get(kr_id, {})
                kr_unit = kr.get("metric_unit") or ""
                kr_title = kr.get("title", "?")
                predicted = lk.get("predicted_kr_impact")
                pred_str = f"predicted +{predicted:g} {kr_unit}" if predicted not in (None, 0) else "no prediction set"

                st.markdown(
                    f"**{kr_title}** "
                    f"<span style='color:#6B7280;font-size:0.85em'>({pred_str})</span>",
                    unsafe_allow_html=True,
                )

                with st.form(f"update_actual_{init_id}_{kr_id}"):
                    cur_actual = lk.get("actual_kr_impact")
                    ui_actual = st.number_input(
                        f"Actual Δ measured ({kr_unit})",
                        value=float(cur_actual) if cur_actual not in (None,) and not pd.isna(cur_actual) else 0.0,
                        step=1.0, format="%.2f",
                        key=f"act_{init_id}_{kr_id}",
                        help="The actual change in this KR's value attributable to this initiative.",
                    )
                    save_act = st.form_submit_button("💾 Save actual impact")
                    if save_act:
                        try:
                            sb.table("initiative_key_result").update({
                                "actual_kr_impact": ui_actual if ui_actual != 0 else None,
                            }).eq("initiative_id", init_id).eq("key_result_id", kr_id).execute()
                            clear_cache()
                            st.success("Actual impact saved.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Save failed: {e}")


# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.divider()
st.caption(
    "This page is for execution updates. To create new initiatives or change "
    "structural fields (title, KR links, business case), head over to "
    "**Manage → Create Initiative**."
)

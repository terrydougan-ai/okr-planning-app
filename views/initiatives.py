"""
Initiatives — read-only structural view of the initiative portfolio.

Mirrors Objectives & KRs in shape:
  * Org unit picker at the top (tree-indented, sticky scope)
  * Org grouping (one section per team in scope)
  * Each initiative renders as its own card with key facts visible at a
    glance + a small table of linked KRs underneath

Differences from Initiative Updates (Track section):
  * Updates is an editor — fast typing-in of milestone status, narratives,
    delivery %
  * Initiatives (this page) is a read-only "what does the portfolio look
    like?" — sibling to Objectives & KRs

The initiative card shows:
  * Header row: milestone icon, title, exec icon + delivery %
  * Sub-row: owner, effort, status
  * Next milestone (text + date) when set
  * Exec narrative when set
  * Linked KRs table (matches the table on Objectives & KRs for consistency)

Sort order within each team: blocked/off-track first, then at-risk, then
on-track, then no-signal. Within each tier, alphabetical by title.
"""

import streamlit as st
import pandas as pd
from datetime import date
from supabase import create_client, Client


# -----------------------------------------------------------------------------
# Constants — mirror the rest of the app
# -----------------------------------------------------------------------------
EXEC_RAG_ICONS = {
    "on_track":  "🟢",
    "at_risk":   "🟡",
    "off_track": "🔴",
    "blocked":   "🚧",
}
MS_LABELS = {
    "on_track":  "on track",
    "at_risk":   "at risk",
    "off_track": "off track",
    "blocked":   "blocked",
}
STATUS_BADGES = {
    "proposed": "💭 proposed",
    "active":   "🟢 active",
    "done":     "✅ done",
    "killed":   "🪦 killed",
}


@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


sb = get_supabase()


@st.cache_data(ttl=60)
def load_all():
    return {
        "org_units": pd.DataFrame(sb.table("org_unit").select("*").execute().data),
        "objectives": pd.DataFrame(sb.table("objective").select("*").execute().data),
        "key_results": pd.DataFrame(sb.table("key_result").select("*").execute().data),
        "initiatives": pd.DataFrame(sb.table("initiative").select("*").execute().data),
        "links": pd.DataFrame(sb.table("initiative_key_result").select("*").execute().data),
    }


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def safe_str(v) -> str:
    return v if isinstance(v, str) else ""


def parse_date_safe(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, date):
        return v
    try:
        return pd.to_datetime(v).date()
    except Exception:
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


def worst_signal(init):
    """Worst of milestone_status and exec_rag for this initiative.
    Returns 'blocked', 'off_track', 'at_risk', 'on_track', or None.
    Used for sort order — done/killed go to the bottom regardless."""
    severity = {"blocked": 0, "off_track": 1, "at_risk": 2, "on_track": 3}
    worst = None
    worst_sev = 99
    for field in ("milestone_status", "exec_rag"):
        v = init.get(field)
        if isinstance(v, str) and v in severity:
            if severity[v] < worst_sev:
                worst = v
                worst_sev = severity[v]
    return worst


def sort_key_for_initiative(init):
    """Sort order within a team's section:
       1. Worst-of-signal severity (blocked first, no-signal last)
       2. done/killed go to the bottom regardless
       3. Alphabetical by title within each tier
    """
    status = init.get("status")
    if status in ("done", "killed"):
        primary = 99  # bottom
    else:
        signal = worst_signal(init)
        primary = {
            "blocked": 0, "off_track": 1, "at_risk": 2, "on_track": 3
        }.get(signal, 4)
    return (primary, safe_str(init.get("title")).lower())


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("🚀 Initiatives")
st.caption(
    "Read-only structural view of the initiative portfolio — sibling to "
    "Objectives & KRs. For editing, see **Manage → Create Initiative** "
    "(structural fields) or **Track → Initiative Updates** (status + narrative)."
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

if org_units.empty:
    st.warning("No org units yet.")
    st.stop()

if initiatives.empty:
    st.info(
        "No initiatives defined yet. Create some on **Manage → Create "
        "Initiative**."
    )
    st.stop()


# -----------------------------------------------------------------------------
# Lookups
# -----------------------------------------------------------------------------
ou_name_by_id = org_units.set_index("id")["name"].to_dict()
kr_by_id = key_results.set_index("id").to_dict("index") if not key_results.empty else {}
obj_by_id = objectives.set_index("id").to_dict("index") if not objectives.empty else {}


# -----------------------------------------------------------------------------
# Org tree (for the picker)
# -----------------------------------------------------------------------------
level_order = {"company": 0, "segment": 1, "team": 2}
children_by_parent: dict = {}
for _, row in org_units.iterrows():
    pid = row["parent_unit_id"]
    if pid != pid:
        pid = None
    children_by_parent.setdefault(pid, []).append(row)

tree_labels: list[str] = []
tree_label_to_id: dict = {}
tree_depth_by_id: dict = {}


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
        tree_depth_by_id[r["id"]] = depth
        _walk_org_tree(r["id"], depth + 1)


_walk_org_tree(None, 0)

ALL_ORGS_LABEL = "All org units"
org_dropdown_options = [ALL_ORGS_LABEL] + tree_labels

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
        "Pick an org unit to see its initiatives. 'All org units' shows "
        "everything grouped by team. Persists across pages."
    ),
)

if selected_org_label != ALL_ORGS_LABEL:
    _scope_id = tree_label_to_id.get(selected_org_label)
    if _scope_id:
        st.session_state["scope_org_id"] = _scope_id
        st.session_state["scope_org_name"] = ou_name_by_id.get(
            _scope_id, selected_org_label
        )


# -----------------------------------------------------------------------------
# Build the per-org grouping
# -----------------------------------------------------------------------------
# An initiative belongs to an org via:
#   1. Its org_unit_id (the direct owning team)
#   2. As a fallback for legacy data, via the KR(s) it links to
# When org_unit_id is set, use that. When not, infer from the first linked KR's
# objective's org (best-effort). When still nothing, it goes under "Contextless".

links_by_init: dict = {}
if not links.empty:
    for _, lk in links.iterrows():
        links_by_init.setdefault(lk["initiative_id"], []).append(lk)


def org_for_initiative(init) -> str | None:
    """Returns the ou_id this initiative belongs to (or None if contextless)."""
    direct = init.get("org_unit_id")
    if isinstance(direct, str) and direct in ou_name_by_id:
        return direct
    # Fallback: infer from first linked KR's objective's org
    init_links = links_by_init.get(init["id"], [])
    for lk in init_links:
        kr = kr_by_id.get(lk.get("key_result_id"))
        if kr:
            obj = obj_by_id.get(kr.get("objective_id"))
            if obj:
                ou_id = obj.get("org_unit_id")
                if isinstance(ou_id, str) and ou_id in ou_name_by_id:
                    return ou_id
    return None


# Filter initiatives by scope
if selected_org_label == ALL_ORGS_LABEL:
    in_scope_ou_ids = set(org_units["id"].tolist())
else:
    # Family = self + descendants (mirrors Hotspots' "drill" semantics)
    selected_ou_id = tree_label_to_id[selected_org_label]
    in_scope_ou_ids = {selected_ou_id}
    stack = list(children_by_parent.get(selected_ou_id, []))
    visited = set()
    while stack:
        row = stack.pop()
        rid = row["id"]
        if rid in visited:
            continue
        visited.add(rid)
        in_scope_ou_ids.add(rid)
        stack.extend(children_by_parent.get(rid, []))

# Group initiatives by their owning org
inits_by_org: dict = {}
contextless_inits = []
for _, init in initiatives.iterrows():
    owning_ou = org_for_initiative(init)
    if owning_ou is None:
        contextless_inits.append(init)
        continue
    if owning_ou not in in_scope_ou_ids:
        continue
    inits_by_org.setdefault(owning_ou, []).append(init)


# -----------------------------------------------------------------------------
# Card rendering
# -----------------------------------------------------------------------------
def _render_kr_link_table(init_id):
    """Small table of linked KRs for this initiative. Matches the columns on
    Objectives & KRs for visual consistency between the two pages."""
    init_links = links_by_init.get(init_id, [])
    if not init_links:
        st.caption(
            "_No KRs linked to this initiative. Either it's an orphan "
            "(should be linked on Manage → Create Initiative) or it's been "
            "intentionally unlinked._"
        )
        return
    rows = []
    for lk in init_links:
        kr = kr_by_id.get(lk.get("key_result_id"))
        if not kr:
            continue
        progress = kr_progress(
            kr.get("start_value"), kr.get("target_value"), kr.get("current_value")
        )
        rows.append({
            "KR": kr.get("title", "?"),
            "unit": kr.get("metric_unit") or "",
            "progress": f"{progress:.0%}",
            "predicted impact": lk.get("predicted_kr_impact"),
            "actual impact": lk.get("actual_kr_impact"),
        })
    if rows:
        st.dataframe(
            pd.DataFrame(rows), use_container_width=True, hide_index=True,
        )


def _render_initiative_card(init):
    """A single initiative as a bordered card with key facts + linked KRs."""
    init_id = init["id"]
    title = init.get("title", "?")
    owner = safe_str(init.get("owner")) or "—"
    effort = safe_str(init.get("effort_estimate")) or "—"
    status = init.get("status") or "—"
    status_badge = STATUS_BADGES.get(status, status)
    ms = init.get("milestone_status")
    exec_rag = init.get("exec_rag")
    ms_icon = EXEC_RAG_ICONS.get(ms, "⚪") if isinstance(ms, str) else "⚪"
    exec_icon = EXEC_RAG_ICONS.get(exec_rag, "⚪") if isinstance(exec_rag, str) else "⚪"
    delivery = init.get("progress_pct") or 0

    next_ms_text = safe_str(init.get("next_milestone_text")).strip()
    next_ms_date = parse_date_safe(init.get("next_milestone_date"))
    exec_narrative = safe_str(init.get("exec_narrative")).strip()

    with st.container(border=True):
        # Header row: milestone icon + title (left) | exec + delivery (right)
        h1, h2 = st.columns([3, 1])
        with h1:
            st.markdown(
                f"### {ms_icon} {title}",
            )
        with h2:
            st.markdown(
                f"<div style='text-align:right;font-size:0.9em;color:#374151;"
                f"padding-top:6px'>"
                f"exec {exec_icon} · {delivery}% delivery"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Sub-row: owner / effort / status
        st.markdown(
            f"<div style='color:#6B7280;font-size:0.9em;margin-top:-8px'>"
            f"owner: <b>{owner}</b> &nbsp;·&nbsp; "
            f"effort: <b>{effort}</b> &nbsp;·&nbsp; "
            f"status: {status_badge}"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Next milestone (if set)
        if next_ms_text or next_ms_date:
            ms_line = "Next: "
            if next_ms_text:
                ms_line += f"<i>{next_ms_text}</i>"
            if next_ms_date:
                ms_line += (
                    f" <span style='color:#6B7280'>"
                    f"(by {next_ms_date.isoformat()})</span>"
                )
            st.markdown(
                f"<div style='margin-top:8px'>{ms_line}</div>",
                unsafe_allow_html=True,
            )

        # Exec narrative (if set)
        if exec_narrative:
            st.markdown(
                f"<div style='margin-top:8px;color:#4B5563;font-size:0.95em'>"
                f"<i>“{exec_narrative}”</i>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Linked KRs table
        st.markdown(
            "<div style='margin-top:12px;font-weight:600;font-size:0.9em;"
            "color:#374151'>Linked KRs</div>",
            unsafe_allow_html=True,
        )
        _render_kr_link_table(init_id)


# -----------------------------------------------------------------------------
# Render each org section
# -----------------------------------------------------------------------------
# Sort orgs by tree depth + name (mirrors Objectives & KRs / Hotspots ordering)
def _ordered_ou_ids():
    ordered = []
    def _walk(parent_id):
        siblings = sorted(
            children_by_parent.get(parent_id, []),
            key=lambda r: (level_order.get(r.get("level"), 99), r["name"]),
        )
        for r in siblings:
            ordered.append(r["id"])
            _walk(r["id"])
    _walk(None)
    return ordered


orgs_in_order = [
    ou_id for ou_id in _ordered_ou_ids()
    if ou_id in inits_by_org and inits_by_org[ou_id]
]

if not orgs_in_order:
    st.info(
        f"No initiatives match in **{selected_org_label}**. Either no "
        "initiatives are owned by this team, or the org_unit_id field is "
        "unset on them (use **Manage → Create Initiative** to set it)."
    )
else:
    for ou_id in orgs_in_order:
        depth = tree_depth_by_id.get(ou_id, 0)
        org_name = ou_name_by_id.get(ou_id, "?")
        init_count = len(inits_by_org[ou_id])
        indent_px = depth * 20
        # Org header line — tree-indented
        st.markdown(
            f"<div style='margin-left:{indent_px}px;margin-top:24px'>"
            f"<h3 style='margin-bottom:8px'>"
            f"🏛️ {org_name} "
            f"<span style='color:#6B7280;font-size:0.7em;font-weight:normal'>"
            f"· {init_count} initiative{'s' if init_count != 1 else ''}"
            f"</span></h3></div>",
            unsafe_allow_html=True,
        )
        # Render cards in priority order
        sorted_inits = sorted(inits_by_org[ou_id], key=sort_key_for_initiative)
        for init in sorted_inits:
            _render_initiative_card(init)


# -----------------------------------------------------------------------------
# Contextless section — initiatives without org_unit_id AND no KR linkage
# -----------------------------------------------------------------------------
if selected_org_label == ALL_ORGS_LABEL and contextless_inits:
    st.divider()
    st.markdown(
        f"### 🪨 Contextless initiatives "
        f"<span style='color:#6B7280;font-size:0.7em;font-weight:normal'>"
        f"· {len(contextless_inits)}"
        f"</span>",
        unsafe_allow_html=True,
    )
    st.caption(
        "_These initiatives have neither an `org_unit_id` set nor any linked "
        "KRs. Assign an owning team on **Manage → Create Initiative**, or "
        "delete if no longer relevant._"
    )
    for init in sorted(contextless_inits, key=sort_key_for_initiative):
        _render_initiative_card(init)


# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.divider()
st.caption(
    "Initiatives is read-only. To create or edit initiatives, see "
    "**Manage → Create Initiative**. To update status / milestone / narrative, "
    "see **Track → Initiative Updates**."
)

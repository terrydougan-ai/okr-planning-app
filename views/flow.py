"""
Flow — the planning portfolio as a Sankey.

Four layers: Yearly Objective → Quarterly Objective → Key Result → Initiative.

Bar widths are predicted $ value from each initiative's business case, falling
back to a small placeholder when no business case exists (so unfunded bets
still appear).

Why this view exists: a flat list answers "what do we have?", but a Sankey
answers "where does our portfolio concentrate, and where are the gaps?". You
glance at it and see:
  * Yearly objectives with no quarterly children — annual bets nobody's working on
  * Quarterly objectives with no KRs — incomplete planning
  * KRs with no initiatives — outcomes nobody is moving
  * Where predicted ROI dollars flow (fat bands at the right)
  * Multi-KR initiatives (one node feeding several KRs upstream)

Yearly vs quarterly are distinguished by the `period` string:
  Yearly:    period starts with "FY" (e.g. "FY2026")
  Quarterly: anything else (e.g. "Q3-2026")
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
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


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def period_sort_key(period: str) -> tuple:
    """Sort yearly first within a year, then quarterly Q1..Q4."""
    if not period:
        return (9999, 9, period or "")
    if isinstance(period, str) and period.startswith("FY"):
        try:
            return (int(period[2:]), 0, "")
        except ValueError:
            return (9999, 9, period)
    try:
        q_part, y_part = period.split("-")
        return (int(y_part), int(q_part.lstrip("Q")), "")
    except (ValueError, AttributeError):
        return (9999, 9, period)


def is_yearly_period(p) -> bool:
    return isinstance(p, str) and p.startswith("FY")


def fmt_money(v) -> str:
    if v is None or pd.isna(v) or v == 0:
        return "—"
    return f"${v:,.0f}"


def truncate(text: str, max_len: int = 38) -> str:
    if not text:
        return ""
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


# Color palette — distinct enough to differentiate four layers at a glance,
# with red reserved for "orphan" markers that flag incomplete planning.
LAYER_COLORS = {
    "yearly_objective":    "#6366F1",   # indigo  — annual bets
    "quarterly_objective": "#3B82F6",   # blue    — this quarter's bets
    "key_result":          "#10B981",   # green   — outcomes
    "initiative":          "#F59E0B",   # amber   — the work
    "orphan":              "#EF4444",   # red     — incomplete planning
}
LINK_COLOR = "rgba(180, 180, 180, 0.4)"
ORPHAN_LINK_COLOR = "rgba(239, 68, 68, 0.25)"


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("🌊 Flow")
st.caption(
    "The planning portfolio as a Sankey. Four layers: yearly → quarterly → "
    "KRs → initiatives. Bar widths are predicted $ value. Red nodes flag gaps."
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
    st.warning("No objectives defined yet.")
    st.stop()


# -----------------------------------------------------------------------------
# Page filters
# -----------------------------------------------------------------------------
# Pickers live in-page (not sidebar) for consistency with the rest of the app.
# Both org and period offer "All …" options for the portfolio bird's-eye view
# that's the whole point of Flow. Defaults come from session state so the
# scope you picked on another page stays selected here.
ou_name_by_id = org_units.set_index("id")["name"].to_dict()
ou_id_by_name = {v: k for k, v in ou_name_by_id.items()}

org_unit_options = ["All org units"]
ou_sorted = org_units.copy()
level_order = {"company": 0, "segment": 1, "team": 2}
ou_sorted["__order"] = ou_sorted["level"].map(level_order).fillna(99)
ou_sorted = ou_sorted.sort_values(["__order", "name"])
for _, row in ou_sorted.iterrows():
    org_unit_options.append(row["name"])

periods_available = sorted(
    objectives["period"].dropna().unique(),
    key=period_sort_key,
)
period_options = ["All periods"] + list(periods_available)

# Read sticky scope as defaults. Flow uses display names not IDs, so we look
# up the name from the saved org_id.
_saved_org_id = st.session_state.get("scope_org_id")
_default_org_label = "All org units"
if _saved_org_id and _saved_org_id in ou_name_by_id:
    _candidate_name = ou_name_by_id[_saved_org_id]
    if _candidate_name in org_unit_options:
        _default_org_label = _candidate_name
_default_org_idx = org_unit_options.index(_default_org_label)

_saved_period = st.session_state.get("scope_period")
_default_period_idx = 0  # "All periods"
if _saved_period and _saved_period in period_options:
    _default_period_idx = period_options.index(_saved_period)

fc1, fc2 = st.columns([2, 1])
with fc1:
    selected_ou = st.selectbox(
        "**Org unit**",
        options=org_unit_options,
        index=_default_org_idx,
        help="Pick a specific unit or 'All org units' for the company-wide view. Persists across pages.",
    )
with fc2:
    selected_period = st.selectbox(
        "**Period**",
        options=period_options,
        index=_default_period_idx,
        help="Pick a quarter, a fiscal year, or all periods.",
    )

# Persist scope. Selecting "All" now clears the scope key so other pages
# consistently default to their broadest view too. Earlier behavior kept
# "All" local to Flow, which created asymmetric persistence — user picks
# a team → sticks, user picks All → doesn't stick.
if selected_ou != "All org units" and selected_ou in ou_id_by_name:
    st.session_state["scope_org_id"] = ou_id_by_name[selected_ou]
    st.session_state["scope_org_name"] = selected_ou
else:
    st.session_state.pop("scope_org_id", None)
    st.session_state.pop("scope_org_name", None)

if selected_period != "All periods":
    st.session_state["scope_period"] = selected_period
else:
    st.session_state.pop("scope_period", None)


# -----------------------------------------------------------------------------
# Filter data — yearly + quarterly together, with cascade awareness
# -----------------------------------------------------------------------------
# Start by filtering by org unit (applies to both yearly and quarterly equally).
# When a parent org is picked, include the family (self + descendants) so
# picking "Acme Analytics" surfaces every team's planning, not just objectives
# attached to the container node itself. This matches Hotspots' behavior.
filtered_objs = objectives.copy()
if selected_ou != "All org units":
    selected_ou_id = next(
        (oid for oid, name in ou_name_by_id.items() if name == selected_ou), None
    )
    if selected_ou_id is not None:
        # Build the family (self + all descendants) via a small tree walk
        _children_by_parent: dict = {}
        for _, _row in org_units.iterrows():
            _pid = _row["parent_unit_id"]
            if _pid != _pid:  # NaN
                _pid = None
            _children_by_parent.setdefault(_pid, []).append(_row["id"])

        family_ids = {selected_ou_id}
        stack = list(_children_by_parent.get(selected_ou_id, []))
        while stack:
            child_id = stack.pop()
            if child_id in family_ids:
                continue
            family_ids.add(child_id)
            stack.extend(_children_by_parent.get(child_id, []))

        filtered_objs = filtered_objs[filtered_objs["org_unit_id"].isin(family_ids)]

# Period filter, with cascade awareness:
#   - "All periods" → show all yearly + all quarterly in the org-filtered set
#   - "FY2026"      → that yearly + every quarterly rolling up to it
#   - "Q3-2026"     → that quarterly + the yearly parents it rolls up to
if selected_period != "All periods":
    if is_yearly_period(selected_period):
        # Show the chosen yearly + every quarterly whose parent is one of them
        yearly_match = filtered_objs[filtered_objs["period"] == selected_period]
        yearly_ids_match = set(yearly_match["id"])
        quarterly_under = filtered_objs[
            (~filtered_objs["period"].apply(is_yearly_period))
            & filtered_objs["parent_objective_id"].isin(yearly_ids_match)
        ]
        filtered_objs = pd.concat([yearly_match, quarterly_under], ignore_index=True)
    else:
        # Quarterly filter — show those plus their yearly parents (regardless of
        # org filter, since a parent yearly might live one org level up)
        quarterly_match = filtered_objs[filtered_objs["period"] == selected_period]
        parent_ids_needed = set(
            pid for pid in quarterly_match["parent_objective_id"].dropna().tolist()
        )
        yearly_parents = (
            objectives[objectives["id"].isin(parent_ids_needed)]
            if parent_ids_needed
            else pd.DataFrame()
        )
        filtered_objs = pd.concat([quarterly_match, yearly_parents], ignore_index=True)

# Defensive: drop dupes that could appear from the union steps above
if not filtered_objs.empty:
    filtered_objs = filtered_objs.drop_duplicates(subset="id")

if filtered_objs.empty:
    st.info("No objectives match the current filters.")
    st.stop()

# Split into yearly and quarterly buckets
yearly_objs = filtered_objs[filtered_objs["period"].apply(is_yearly_period)]
quarterly_objs = filtered_objs[~filtered_objs["period"].apply(is_yearly_period)]

yearly_ids_in_scope = set(yearly_objs["id"])
quarterly_ids_in_scope = set(quarterly_objs["id"])
obj_ids_in_scope = yearly_ids_in_scope | quarterly_ids_in_scope

# KRs only attach to QUARTERLY objectives that have them. Yearly objectives
# CAN have KRs (the aspirational ones from the Annual page), but they won't
# show up as nodes in column 3 — we keep KR column scoped to quarterly bets
# to preserve the "outcomes layer" meaning of column 3.
filtered_krs = (
    key_results[key_results["objective_id"].isin(quarterly_ids_in_scope)]
    if not key_results.empty
    else pd.DataFrame()
)
kr_ids_in_scope = set(filtered_krs["id"]) if not filtered_krs.empty else set()
filtered_links = (
    links[links["key_result_id"].isin(kr_ids_in_scope)]
    if not links.empty and kr_ids_in_scope
    else pd.DataFrame()
)
init_ids_in_scope = (
    set(filtered_links["initiative_id"]) if not filtered_links.empty else set()
)
filtered_inits = (
    initiatives[initiatives["id"].isin(init_ids_in_scope)]
    if init_ids_in_scope and not initiatives.empty
    else pd.DataFrame()
)


# -----------------------------------------------------------------------------
# Identify orphans — what "orphan" means depends on the layer
# -----------------------------------------------------------------------------
# Yearly objective: orphan if NO quarterly objectives in scope roll up to it.
# A yearly objective is supposed to be a parent — without children, it's
# either aspirational-only (fine, just unrepresented in this quarter's bets)
# or genuinely abandoned. Either way, surfacing it is useful.
yearly_with_children = set(
    pid for pid in quarterly_objs["parent_objective_id"].dropna().tolist()
)
orphan_yearly_ids = yearly_ids_in_scope - yearly_with_children

# Quarterly objective: orphan if no KRs (unchanged from before). A quarterly
# objective without a yearly parent is NOT orphan — matrix/cross-unit
# alignment is legitimate and very common.
obj_has_kr = (
    set(filtered_krs["objective_id"]) if not filtered_krs.empty else set()
)
orphan_quarterly_ids = quarterly_ids_in_scope - obj_has_kr

# KR: orphan if no initiatives (unchanged)
kr_has_init = (
    set(filtered_links["key_result_id"]) if not filtered_links.empty else set()
)
orphan_kr_ids = kr_ids_in_scope - kr_has_init


# -----------------------------------------------------------------------------
# Compute flow weights
# -----------------------------------------------------------------------------
bc_by_init = (
    business_cases.set_index("initiative_id").to_dict("index")
    if not business_cases.empty
    else {}
)

known_values = [
    bc.get("predicted_value", 0) or 0
    for bc in bc_by_init.values()
    if (bc.get("predicted_value") or 0) > 0
]
fallback_value = (
    sorted(known_values)[len(known_values) // 2] if known_values else 1.0
)

init_value: dict = {}
for _, init in filtered_inits.iterrows():
    bc = bc_by_init.get(init["id"])
    v = (bc.get("predicted_value") if bc else None) or 0
    init_value[init["id"]] = v if v > 0 else fallback_value

init_link_count: dict = {}
if not filtered_links.empty:
    init_link_count = filtered_links.groupby("initiative_id").size().to_dict()


# -----------------------------------------------------------------------------
# Build Sankey nodes
# -----------------------------------------------------------------------------
nodes_labels: list[str] = []
nodes_colors: list[str] = []
nodes_customdata: list[str] = []
nodes_kinds: list[str] = []  # parallel array tracking each node's layer
node_idx: dict = {}


def add_node(kind: str, node_id: str, label: str, hover: str, is_orphan: bool = False) -> int:
    key = (kind, node_id)
    if key in node_idx:
        return node_idx[key]
    idx = len(nodes_labels)
    display_label = ("⚠ " + label) if is_orphan else label
    nodes_labels.append(truncate(display_label, 40))
    nodes_colors.append(LAYER_COLORS["orphan"] if is_orphan else LAYER_COLORS[kind])
    nodes_customdata.append(hover)
    nodes_kinds.append(kind)
    node_idx[key] = idx
    return idx


ou_position = {row["id"]: i for i, (_, row) in enumerate(ou_sorted.iterrows())}

# Track each node's position within its column. Downstream columns sort by
# their parent's position so ribbons stay non-crossing where the topology
# is mostly linear (barycentric sort — standard Sankey layout trick).
position_in_column: dict = {}  # node_id (string uuid) → its index in its column

# ---------- YEARLY column (column 1) ----------
# Stable starting order: by org-tree position, then by period (within year)
yearly_sorted = yearly_objs.copy()
if not yearly_sorted.empty:
    yearly_sorted["__pos"] = yearly_sorted["org_unit_id"].map(ou_position).fillna(999)
    yearly_sorted["__period_key"] = yearly_sorted["period"].apply(period_sort_key)
    yearly_sorted = yearly_sorted.sort_values(["__pos", "__period_key"])

    for i, (_, yo) in enumerate(yearly_sorted.iterrows()):
        is_orphan = yo["id"] in orphan_yearly_ids
        ou_name = ou_name_by_id.get(yo["org_unit_id"], "?")
        orphan_note = (
            "<br><b style='color:#EF4444'>⚠ No quarterly objectives "
            "rolling up to this</b>"
            if is_orphan else ""
        )
        hover = (
            f"<b>{yo['title']}</b><br>"
            f"{ou_name} · {yo.get('period', '?')}"
            f"{orphan_note}"
        )
        add_node("yearly_objective", yo["id"], yo["title"], hover, is_orphan=is_orphan)
        position_in_column[yo["id"]] = i

# ---------- QUARTERLY column (column 2) ----------
# Sort by the parent yearly's position. Quarterlies without a yearly parent
# (matrix or orphan-aligned) go to the bottom of the column, sorted by their
# own org/period for stability.
quarterly_sorted = quarterly_objs.copy()
if not quarterly_sorted.empty:
    def _quarterly_sort_key(row):
        parent_id = row.get("parent_objective_id")
        if parent_id != parent_id:  # NaN
            parent_id = None
        parent_pos = position_in_column.get(parent_id, 999_999) if parent_id else 999_999
        own_pos = ou_position.get(row["org_unit_id"], 999)
        period_key = period_sort_key(row.get("period"))
        # (parent's position, then by own org+period for ties / no-parent cases)
        return (parent_pos, own_pos, period_key)

    quarterly_sorted["__sort_key"] = quarterly_sorted.apply(_quarterly_sort_key, axis=1)
    quarterly_sorted = quarterly_sorted.sort_values("__sort_key")

    for i, (_, qo) in enumerate(quarterly_sorted.iterrows()):
        is_orphan = qo["id"] in orphan_quarterly_ids
        ou_name = ou_name_by_id.get(qo["org_unit_id"], "?")
        orphan_note = (
            "<br><b style='color:#EF4444'>⚠ No KRs defined</b>"
            if is_orphan else ""
        )
        hover = (
            f"<b>{qo['title']}</b><br>"
            f"{ou_name} · {qo.get('period', '?')}"
            f"{orphan_note}"
        )
        add_node("quarterly_objective", qo["id"], qo["title"], hover, is_orphan=is_orphan)
        position_in_column[qo["id"]] = i

# ---------- KR column (column 3) ----------
# Sort by the parent quarterly's position. Each KR has exactly one objective_id,
# so the lookup is direct.
if not filtered_krs.empty:
    def _kr_sort_key(row):
        parent_pos = position_in_column.get(row.get("objective_id"), 999_999)
        return (parent_pos, safe_str_for_sort(row.get("title")))

    def safe_str_for_sort(v):
        return v if isinstance(v, str) else ""

    krs_sorted = filtered_krs.copy()
    krs_sorted["__sort_key"] = krs_sorted.apply(_kr_sort_key, axis=1)
    krs_sorted = krs_sorted.sort_values("__sort_key")
else:
    krs_sorted = filtered_krs

for i, (_, kr) in enumerate(krs_sorted.iterrows()):
    is_orphan = kr["id"] in orphan_kr_ids
    unit = kr.get("metric_unit") or ""
    orphan_note = (
        "<br><b style='color:#EF4444'>⚠ No initiatives moving this</b>"
        if is_orphan else ""
    )
    hover = (
        f"<b>{kr['title']}</b><br>"
        f"Start {kr.get('start_value')} → "
        f"Current {kr.get('current_value')} → "
        f"Target {kr.get('target_value')} {unit}"
        f"{orphan_note}"
    )
    add_node("key_result", kr["id"], kr["title"], hover, is_orphan=is_orphan)
    position_in_column[kr["id"]] = i

# ---------- Initiative column (column 4) ----------
# Sort by the AVERAGE position of the KRs each initiative links to. So a multi-
# KR initiative sits between its KRs vertically, and single-KR initiatives sit
# at their KR's row. This is the key fix for crossing ribbons.
if not filtered_inits.empty:
    # Build init_id → list of KR positions
    init_avg_pos: dict = {}
    if not filtered_links.empty:
        for init_id, group in filtered_links.groupby("initiative_id"):
            kr_positions = [
                position_in_column.get(kid, 999_999)
                for kid in group["key_result_id"].tolist()
            ]
            init_avg_pos[init_id] = (
                sum(kr_positions) / len(kr_positions) if kr_positions else 999_999
            )

    inits_sorted = filtered_inits.copy()
    inits_sorted["__sort_key"] = inits_sorted["id"].map(
        lambda iid: init_avg_pos.get(iid, 999_999)
    )
    inits_sorted = inits_sorted.sort_values("__sort_key")
else:
    inits_sorted = filtered_inits

for _, init in inits_sorted.iterrows():
    bc = bc_by_init.get(init["id"])
    v = (bc.get("predicted_value") if bc else None) or 0
    cost = (bc.get("predicted_cost") if bc else None) or 0
    roi_str = f"{v/cost:.1f}x" if cost > 0 else "—"
    hover = (
        f"<b>{init['title']}</b><br>"
        f"Status: {init.get('status', '—')} · "
        f"Delivery: {init.get('progress_pct') or 0}%<br>"
        f"Predicted value: {fmt_money(v)} · "
        f"Cost: {fmt_money(cost)} · "
        f"ROI: {roi_str}"
    )
    add_node("initiative", init["id"], init["title"], hover)


# -----------------------------------------------------------------------------
# Build links
# -----------------------------------------------------------------------------
sources: list[int] = []
targets: list[int] = []
values: list[float] = []
link_hover: list[str] = []
link_colors: list[str] = []

# KR total weights (from initiatives flowing in)
kr_total_value: dict = {}
if not filtered_links.empty:
    for _, link in filtered_links.iterrows():
        init_id = link["initiative_id"]
        kr_id = link["key_result_id"]
        n_links = init_link_count.get(init_id, 1) or 1
        share = init_value.get(init_id, fallback_value) / n_links
        kr_total_value[kr_id] = kr_total_value.get(kr_id, 0) + share

# Quarterly objective total weights (from KRs flowing in)
quarterly_total_value: dict = {}
for _, kr in filtered_krs.iterrows():
    qo_id = kr["objective_id"]
    if qo_id not in quarterly_ids_in_scope:
        continue
    quarterly_total_value[qo_id] = quarterly_total_value.get(qo_id, 0) + kr_total_value.get(
        kr["id"], fallback_value * 0.1
    )

# YEARLY → QUARTERLY (via parent_objective_id)
for _, qo in quarterly_objs.iterrows():
    parent_id = qo.get("parent_objective_id")
    # NaN-safe: pandas may load null parent_objective_id as NaN
    if parent_id != parent_id:  # NaN check
        parent_id = None
    if not parent_id or parent_id not in yearly_ids_in_scope:
        continue
    if ("yearly_objective", parent_id) not in node_idx:
        continue
    if ("quarterly_objective", qo["id"]) not in node_idx:
        continue
    y_idx = node_idx[("yearly_objective", parent_id)]
    q_idx = node_idx[("quarterly_objective", qo["id"])]
    w = quarterly_total_value.get(qo["id"], fallback_value * 0.4)
    sources.append(y_idx)
    targets.append(q_idx)
    values.append(w)
    link_hover.append(
        f"{nodes_labels[y_idx]} → {nodes_labels[q_idx]}<br>"
        f"Weight: {fmt_money(w) if w > fallback_value * 0.5 else '(placeholder)'}"
    )
    link_colors.append(LINK_COLOR)

# QUARTERLY → KR
for _, kr in filtered_krs.iterrows():
    qo_id = kr["objective_id"]
    if qo_id not in quarterly_ids_in_scope:
        continue
    if ("quarterly_objective", qo_id) not in node_idx:
        continue
    if ("key_result", kr["id"]) not in node_idx:
        continue
    qo_idx = node_idx[("quarterly_objective", qo_id)]
    kr_idx = node_idx[("key_result", kr["id"])]
    is_orphan_kr = kr["id"] in orphan_kr_ids
    w = kr_total_value.get(kr["id"], fallback_value * 0.1)
    sources.append(qo_idx)
    targets.append(kr_idx)
    values.append(w)
    link_hover.append(
        f"{nodes_labels[qo_idx]} → {nodes_labels[kr_idx]}<br>"
        f"Weight: {fmt_money(w) if w > fallback_value * 0.5 else '(placeholder)'}"
    )
    link_colors.append(ORPHAN_LINK_COLOR if is_orphan_kr else LINK_COLOR)

# KR → INITIATIVE
if not filtered_links.empty:
    for _, link in filtered_links.iterrows():
        init_id = link["initiative_id"]
        kr_id = link["key_result_id"]
        if ("key_result", kr_id) not in node_idx:
            continue
        if ("initiative", init_id) not in node_idx:
            continue
        kr_idx = node_idx[("key_result", kr_id)]
        init_idx = node_idx[("initiative", init_id)]
        n_links = init_link_count.get(init_id, 1) or 1
        share = init_value.get(init_id, fallback_value) / n_links
        sources.append(kr_idx)
        targets.append(init_idx)
        values.append(share)
        link_hover.append(
            f"{nodes_labels[kr_idx]} → {nodes_labels[init_idx]}<br>"
            f"Weight: {fmt_money(share)}"
        )
        link_colors.append(LINK_COLOR)

# Orphan placeholders downstream so the gaps render visibly.

# Orphan yearly objectives → "⚠ No quarterly" placeholder
for yo_id in orphan_yearly_ids:
    if ("yearly_objective", yo_id) not in node_idx:
        continue
    yo_idx = node_idx[("yearly_objective", yo_id)]
    p_idx = len(nodes_labels)
    nodes_labels.append("⚠ No quarterly objectives")
    nodes_colors.append(LAYER_COLORS["orphan"])
    nodes_customdata.append(
        "This yearly objective has no quarterly objectives rolling up to it. "
        "Either add quarterly bets that align to it, or treat it as aspirational-only."
    )
    # Placeholder sits in the Quarterly column (the layer this orphan would feed into)
    nodes_kinds.append("quarterly_objective")
    sources.append(yo_idx)
    targets.append(p_idx)
    values.append(fallback_value * 0.4)
    link_hover.append("⚠ No quarterly objectives roll up to this")
    link_colors.append(ORPHAN_LINK_COLOR)

# Orphan quarterly objectives → "⚠ Define a KR" placeholder
for qo_id in orphan_quarterly_ids:
    if ("quarterly_objective", qo_id) not in node_idx:
        continue
    qo_idx = node_idx[("quarterly_objective", qo_id)]
    p_idx = len(nodes_labels)
    nodes_labels.append("⚠ Define a KR")
    nodes_colors.append(LAYER_COLORS["orphan"])
    nodes_customdata.append(
        "This quarterly objective has no KRs yet. Add at least one on Plan a Quarter."
    )
    # Placeholder sits in the KR column
    nodes_kinds.append("key_result")
    sources.append(qo_idx)
    targets.append(p_idx)
    values.append(fallback_value * 0.4)
    link_hover.append("⚠ No KRs defined for this objective")
    link_colors.append(ORPHAN_LINK_COLOR)

# Orphan KRs → "⚠ No initiative" placeholder
for kr_id in orphan_kr_ids:
    if ("key_result", kr_id) not in node_idx:
        continue
    kr_idx = node_idx[("key_result", kr_id)]
    p_idx = len(nodes_labels)
    nodes_labels.append("⚠ No initiative")
    nodes_colors.append(LAYER_COLORS["orphan"])
    nodes_customdata.append(
        "This KR has no initiatives moving it. Propose one on Plan a Quarter."
    )
    # Placeholder sits in the Initiative column
    nodes_kinds.append("initiative")
    sources.append(kr_idx)
    targets.append(p_idx)
    values.append(fallback_value * 0.4)
    link_hover.append("⚠ No initiatives attached")
    link_colors.append(ORPHAN_LINK_COLOR)


# -----------------------------------------------------------------------------
# Render
# -----------------------------------------------------------------------------
if not sources:
    st.info("Nothing to draw. Try widening the filters.")
    st.stop()

# Diagnostic strip — five metrics now (yearly, quarterly, KRs, inits, $)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Yearly", len(yearly_objs))
c2.metric("Quarterly", len(quarterly_objs))
c3.metric("Key Results", len(filtered_krs))
c4.metric("Initiatives", len(filtered_inits))
total_value = sum(v for v in init_value.values() if v != fallback_value)
c5.metric("Funded $", fmt_money(total_value))

# Gap callouts
gap_msgs = []
if orphan_yearly_ids:
    gap_msgs.append(
        f"**{len(orphan_yearly_ids)} of {len(yearly_objs)} yearly objectives** "
        "have no quarterly children"
    )
if orphan_quarterly_ids:
    gap_msgs.append(
        f"**{len(orphan_quarterly_ids)} of {len(quarterly_objs)} quarterly objectives** "
        "have no KRs"
    )
if orphan_kr_ids:
    gap_msgs.append(
        f"**{len(orphan_kr_ids)} of {len(filtered_krs)} KRs** have no initiatives"
    )
if gap_msgs:
    st.warning("⚠ Planning gaps in current view: " + " · ".join(gap_msgs))

st.divider()

# Compute a fixed x position for each node based on its layer. Without this,
# Plotly's "snap" arrangement infers x from graph topology, which causes nodes
# with no upstream connection (e.g. quarterly objectives without a yearly
# parent in scope) to drift leftward into the wrong column. Pinning x by kind
# guarantees the four-column structure holds visually.
#
# Plotly clamps x to (0, 1) exclusively — values of 0.0 or 1.0 get nudged
# slightly, so we use 0.01 and 0.99 at the extremes for predictability.
LAYER_X = {
    "yearly_objective":    0.01,
    "quarterly_objective": 0.34,
    "key_result":          0.67,
    "initiative":          0.99,
}
nodes_x = [LAYER_X.get(k, 0.5) for k in nodes_kinds]

# Distribute y positions evenly within each column. If every node has the same
# y (e.g. all 0.5), Plotly's snap algorithm packs them all into a small band —
# usually the bottom — leaving the top of the chart empty. Spreading nodes
# across (0.05, 0.95) tells Plotly where each one wants to live, and snap then
# refines from there. Order within a column comes from the order add_node was
# called in, which is already the tree/iteration order we want.
from collections import defaultdict
indices_by_kind: dict = defaultdict(list)
for i, k in enumerate(nodes_kinds):
    indices_by_kind[k].append(i)

nodes_y = [0.5] * len(nodes_kinds)
for kind, indices in indices_by_kind.items():
    n = len(indices)
    if n == 1:
        nodes_y[indices[0]] = 0.5
        continue
    # Spread evenly from 0.03 to 0.97 (more headroom than 0.05/0.95 which
    # leaves outer nodes bumping the chart edges).
    for pos, idx in enumerate(indices):
        nodes_y[idx] = 0.03 + (0.94 * pos / (n - 1))

# Build the Sankey
fig = go.Figure(
    data=[
        go.Sankey(
            arrangement="snap",  # honor x/y we provide; snap refines vertical packing
            node=dict(
                pad=28,
                thickness=22,
                line=dict(color="rgba(0,0,0,0.25)", width=0.6),
                label=nodes_labels,
                color=nodes_colors,
                customdata=nodes_customdata,
                x=nodes_x,
                y=nodes_y,
                hovertemplate="%{customdata}<extra></extra>",
            ),
            link=dict(
                source=sources,
                target=targets,
                value=values,
                color=link_colors,
                customdata=link_hover,
                hovertemplate="%{customdata}<extra></extra>",
            ),
            textfont=dict(
                color="#1f2937",
                size=13,
                family="Inter, system-ui, sans-serif",
            ),
        )
    ]
)

# Count nodes per column, including orphan placeholders that pile into each
# downstream column. With fixed x positions, Plotly must fit every node
# vertically — so the chart needs enough height for the tallest column.
column_node_counts = {
    "yearly":    len(yearly_objs) if not yearly_objs.empty else 0,
    "quarterly": (len(quarterly_objs) if not quarterly_objs.empty else 0)
                 + len(orphan_yearly_ids),
    "kr":        (len(filtered_krs) if not filtered_krs.empty else 0)
                 + len(orphan_quarterly_ids),
    "init":      (len(filtered_inits) if not filtered_inits.empty else 0)
                 + len(orphan_kr_ids),
}
node_count_max = max(max(column_node_counts.values()), 1)
# 110px per node (more breathing room than 90), plus 320px chrome (taller
# top margin for the stacked title+subtitle headers, plus bottom padding).
chart_height = max(640, 110 * node_count_max + 320)

# Four column headers with subtitles, anchored at x = 0.00 / 0.33 / 0.67 / 1.00.
# Title sits at y=1.07; subtitle at y=1.025 immediately below it, in muted gray.
header_color = "#374151"
subtitle_color = "#9CA3AF"
header_font = dict(size=13, color=header_color, family="Inter, system-ui, sans-serif")
subtitle_font = dict(size=10, color=subtitle_color, family="Inter, system-ui, sans-serif")

def header_block(x, anchor, title, subtitle):
    return [
        dict(
            x=x, y=1.07, xref="paper", yref="paper",
            xanchor=anchor, yanchor="bottom",
            text=f"<b>{title}</b>",
            showarrow=False, font=header_font,
        ),
        dict(
            x=x, y=1.025, xref="paper", yref="paper",
            xanchor=anchor, yanchor="bottom",
            text=subtitle,
            showarrow=False, font=subtitle_font,
        ),
    ]

header_annotations = (
    header_block(0.00, "left",   "Yearly Objectives",    "Annual bets.")
    + header_block(0.33, "center", "Quarterly Objectives", "This quarter's goals.")
    + header_block(0.67, "center", "Key Results",          "Measurable outcomes.")
    + header_block(1.00, "right",  "Initiatives",          "The bets that move KRs.")
)

fig.update_layout(
    # Top margin is taller than before to give the stacked title+subtitle
    # headers room to breathe above the chart area.
    margin=dict(l=10, r=10, t=90, b=20),
    height=chart_height,
    paper_bgcolor="white",
    plot_bgcolor="white",
    annotations=header_annotations,
)

st.plotly_chart(fig, use_container_width=True)


# -----------------------------------------------------------------------------
# Legend & explainer
# -----------------------------------------------------------------------------
st.divider()
# Single-line color key. Column titles are already in the chart headers — no
# need to repeat them. This is just a "what does each color mean?" reference.
st.markdown(
    f"<div style='font-size:0.85em;color:#6B7280'>"
    f"<span style='color:{LAYER_COLORS['yearly_objective']}'>■</span> Yearly &nbsp;·&nbsp; "
    f"<span style='color:{LAYER_COLORS['quarterly_objective']}'>■</span> Quarterly &nbsp;·&nbsp; "
    f"<span style='color:{LAYER_COLORS['key_result']}'>■</span> Key Results &nbsp;·&nbsp; "
    f"<span style='color:{LAYER_COLORS['initiative']}'>■</span> Initiatives &nbsp;·&nbsp; "
    f"<span style='color:{LAYER_COLORS['orphan']}'>⚠</span> Orphan (incomplete planning)"
    f"</div>",
    unsafe_allow_html=True,
)

with st.expander("ℹ️ How weights and orphans are computed"):
    st.markdown(
        """
**Weights**
- Each initiative carries its **predicted $ value** from its business case.
- Initiatives with no business case fall back to the median predicted value
  across funded initiatives (or 1.0 if none are funded yet).
- For **multi-KR initiatives**, the initiative's value is **split equally across
  its KR links**.
- KR totals roll up to their quarterly objectives, which roll up to their
  yearly parents — so a fat band on the left means "this annual bet has lots
  of dollars flowing toward it from the quarterly plan."

**Orphans (red)**

What counts as orphan depends on the layer:

- **Yearly objective with no quarterly children** — annual bet nobody's working
  on this quarter. Might be aspirational-only (fine) or genuinely stalled.
- **Quarterly objective with no KRs** — stated goal with no measurable outcome.
  Incomplete planning.
- **KR with no initiatives** — outcome nobody is moving. The most common gap.

A quarterly objective WITHOUT a yearly parent is **not** flagged — matrix
planning (where work in one unit supports another unit's annual goals) is
legitimate and common. Only structural gaps within each layer count as orphans.
        """
    )

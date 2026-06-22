"""
Flow — the planning portfolio as a Sankey.

Three layers: Objective → Key Result → Initiative. Bar widths are predicted $
value from each initiative's business case, falling back to a small placeholder
when no business case exists (so unfunded bets still appear).

Why this view exists: a flat list answers "what do we have?", but a Sankey
answers "where does our portfolio concentrate, and where are the gaps?". You
glance at it and see:
  * Objectives with no KRs (highlighted in red — incomplete planning)
  * KRs with no initiatives (highlighted — outcomes nobody is moving)
  * Where predicted ROI dollars flow (fat bands at the right)
  * Multi-KR initiatives (one node feeding several KRs upstream)
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
    if not period:
        return (9999, 9, period or "")
    try:
        q_part, y_part = period.split("-")
        return (int(y_part), int(q_part.lstrip("Q")), "")
    except (ValueError, AttributeError):
        return (9999, 9, period)


def fmt_money(v) -> str:
    if v is None or pd.isna(v) or v == 0:
        return "—"
    return f"${v:,.0f}"


def truncate(text: str, max_len: int = 38) -> str:
    if not text:
        return ""
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


# Color palette — distinct enough to differentiate layers at a glance,
# with red reserved for "orphan" markers that flag incomplete planning.
LAYER_COLORS = {
    "objective":  "#3B82F6",   # blue
    "key_result": "#10B981",   # green
    "initiative": "#F59E0B",   # amber
    "orphan":     "#EF4444",   # red — for incomplete planning
}
LINK_COLOR = "rgba(180, 180, 180, 0.4)"
ORPHAN_LINK_COLOR = "rgba(239, 68, 68, 0.25)"


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("🌊 Flow")
st.caption(
    "The planning portfolio as a Sankey. Bar widths are predicted $ value. "
    "Red nodes flag gaps — objectives with no KRs, KRs with no initiatives."
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
# Sidebar filters
# -----------------------------------------------------------------------------
ou_name_by_id = org_units.set_index("id")["name"].to_dict()

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

with st.sidebar:
    st.header("Filters")
    selected_ou = st.selectbox("Org unit", options=org_unit_options, index=0)
    selected_period = st.selectbox("Period", options=period_options, index=0)


# -----------------------------------------------------------------------------
# Filter data
# -----------------------------------------------------------------------------
filtered_objs = objectives.copy()
if selected_ou != "All org units":
    selected_ou_id = next(
        (oid for oid, name in ou_name_by_id.items() if name == selected_ou), None
    )
    if selected_ou_id is not None:
        filtered_objs = filtered_objs[filtered_objs["org_unit_id"] == selected_ou_id]
if selected_period != "All periods":
    filtered_objs = filtered_objs[filtered_objs["period"] == selected_period]

if filtered_objs.empty:
    st.info("No objectives match the current filters.")
    st.stop()

obj_ids_in_scope = set(filtered_objs["id"])
filtered_krs = (
    key_results[key_results["objective_id"].isin(obj_ids_in_scope)]
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
# Identify orphans (the diagnostic value of this page)
# -----------------------------------------------------------------------------
obj_has_kr = set(filtered_krs["objective_id"]) if not filtered_krs.empty else set()
orphan_obj_ids = obj_ids_in_scope - obj_has_kr

kr_has_init = set(filtered_links["key_result_id"]) if not filtered_links.empty else set()
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
    node_idx[key] = idx
    return idx


ou_position = {row["id"]: i for i, (_, row) in enumerate(ou_sorted.iterrows())}
objs_sorted = filtered_objs.copy()
objs_sorted["__pos"] = objs_sorted["org_unit_id"].map(ou_position).fillna(999)
objs_sorted["__period_key"] = objs_sorted["period"].apply(period_sort_key)
objs_sorted = objs_sorted.sort_values(["__pos", "__period_key"])

for _, obj in objs_sorted.iterrows():
    is_orphan = obj["id"] in orphan_obj_ids
    ou_name = ou_name_by_id.get(obj["org_unit_id"], "?")
    orphan_note = "<br><b style='color:#EF4444'>⚠ No KRs defined</b>" if is_orphan else ""
    hover = (
        f"<b>{obj['title']}</b><br>"
        f"{ou_name} · {obj.get('period', '?')}"
        f"{orphan_note}"
    )
    add_node("objective", obj["id"], obj["title"], hover, is_orphan=is_orphan)

for _, kr in filtered_krs.iterrows():
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

for _, init in filtered_inits.iterrows():
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

# Objective → KR
for _, kr in filtered_krs.iterrows():
    obj_id = kr["objective_id"]
    if obj_id not in obj_ids_in_scope:
        continue
    obj_idx = node_idx[("objective", obj_id)]
    kr_idx = node_idx[("key_result", kr["id"])]
    is_orphan_kr = kr["id"] in orphan_kr_ids
    w = kr_total_value.get(kr["id"], fallback_value * 0.1)
    sources.append(obj_idx)
    targets.append(kr_idx)
    values.append(w)
    link_hover.append(
        f"{nodes_labels[obj_idx]} → {nodes_labels[kr_idx]}<br>"
        f"Weight: {fmt_money(w) if w > fallback_value * 0.5 else '(placeholder)'}"
    )
    link_colors.append(ORPHAN_LINK_COLOR if is_orphan_kr else LINK_COLOR)

# KR → Initiative
if not filtered_links.empty:
    for _, link in filtered_links.iterrows():
        init_id = link["initiative_id"]
        kr_id = link["key_result_id"]
        kr_idx = node_idx[("key_result", kr_id)]
        init_node_key = ("initiative", init_id)
        if init_node_key not in node_idx:
            continue
        init_idx = node_idx[init_node_key]
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

# Orphan objectives: phantom downstream node so they still render.
# Plotly Sankey requires every node to connect somewhere. We give each orphan
# objective its own phantom target with a clear "define a KR" label so the gap
# is visible AND actionable.
for obj_id in orphan_obj_ids:
    obj_idx = node_idx[("objective", obj_id)]
    p_idx = len(nodes_labels)
    nodes_labels.append("⚠ Define a KR")
    nodes_colors.append(LAYER_COLORS["orphan"])
    nodes_customdata.append(
        "This objective has no KRs yet. Add at least one on the Manage Key Results page."
    )

    sources.append(obj_idx)
    targets.append(p_idx)
    values.append(fallback_value * 0.4)
    link_hover.append("⚠ No KRs defined for this objective")
    link_colors.append(ORPHAN_LINK_COLOR)

# Orphan KRs similarly need a phantom target so they appear at the right column.
for kr_id in orphan_kr_ids:
    kr_idx = node_idx[("key_result", kr_id)]
    p_idx = len(nodes_labels)
    nodes_labels.append("⚠ No initiative")
    nodes_colors.append(LAYER_COLORS["orphan"])
    nodes_customdata.append(
        "This KR has no initiatives moving it. Attach one on the Manage Initiatives page."
    )

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

# Diagnostic strip
c1, c2, c3, c4 = st.columns(4)
c1.metric("Objectives", len(filtered_objs))
c2.metric("Key Results", len(filtered_krs))
c3.metric("Initiatives", len(filtered_inits))
total_value = sum(v for v in init_value.values() if v != fallback_value)
c4.metric("Funded predicted value", fmt_money(total_value))

# Gap callouts
if orphan_obj_ids or orphan_kr_ids:
    gap_msgs = []
    if orphan_obj_ids:
        gap_msgs.append(
            f"**{len(orphan_obj_ids)} of {len(filtered_objs)} objectives** have no KRs"
        )
    if orphan_kr_ids:
        gap_msgs.append(
            f"**{len(orphan_kr_ids)} of {len(filtered_krs)} KRs** have no initiatives"
        )
    st.warning("⚠ Planning gaps in current view: " + " · ".join(gap_msgs))

st.divider()

# Build the Sankey
fig = go.Figure(
    data=[
        go.Sankey(
            arrangement="snap",
            node=dict(
                pad=28,
                thickness=22,
                line=dict(color="rgba(0,0,0,0.25)", width=0.6),
                label=nodes_labels,
                color=nodes_colors,
                customdata=nodes_customdata,
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
                color="#1f2937",   # dark slate; high contrast against light backdrop
                size=14,
                family="Inter, system-ui, sans-serif",
            ),
        )
    ]
)

node_count_max = max(
    len(filtered_objs),
    len(filtered_krs) if not filtered_krs.empty else 1,
    len(filtered_inits) if not filtered_inits.empty else 1,
    len(orphan_obj_ids) + len(orphan_kr_ids) + 1,
)
chart_height = max(520, 80 * node_count_max + 200)

# Column headers above the Sankey columns.
# Plotly Sankey lays out three columns horizontally:
#   x≈0.00  Objectives
#   x≈0.50  Key Results (real + orphan-objective placeholders)
#   x≈1.00  Initiatives (real + orphan-KR placeholders)
# The y=1.06 position floats just above the chart area (we widen the top
# margin below to make space).
header_color = "#374151"  # neutral slate — doesn't compete with node colors
header_annotations = [
    dict(
        x=0.00, y=1.06, xref="paper", yref="paper",
        xanchor="left", yanchor="bottom",
        text="<b>Objectives</b>",
        showarrow=False,
        font=dict(size=14, color=header_color, family="Inter, system-ui, sans-serif"),
    ),
    dict(
        x=0.50, y=1.06, xref="paper", yref="paper",
        xanchor="center", yanchor="bottom",
        text="<b>Key Results</b>",
        showarrow=False,
        font=dict(size=14, color=header_color, family="Inter, system-ui, sans-serif"),
    ),
    dict(
        x=1.00, y=1.06, xref="paper", yref="paper",
        xanchor="right", yanchor="bottom",
        text="<b>Initiatives</b>",
        showarrow=False,
        font=dict(size=14, color=header_color, family="Inter, system-ui, sans-serif"),
    ),
]

# If there are orphans, add a small note centered below the headers so the red
# nodes are explained inline rather than only in the legend below.
if orphan_obj_ids or orphan_kr_ids:
    header_annotations.append(
        dict(
            x=0.5, y=1.015, xref="paper", yref="paper",
            xanchor="center", yanchor="bottom",
            text=f"<span style='color:#EF4444'>⚠ red = orphan (incomplete planning)</span>",
            showarrow=False,
            font=dict(size=11, family="Inter, system-ui, sans-serif"),
        )
    )

fig.update_layout(
    margin=dict(l=10, r=10, t=70, b=20),  # extra top space for the headers
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
lc1, lc2, lc3, lc4 = st.columns(4)
with lc1:
    st.markdown(
        f"<div style='color:{LAYER_COLORS['objective']};font-weight:600'>■ Objectives</div>",
        unsafe_allow_html=True,
    )
    st.caption("Time-boxed qualitative goals.")
with lc2:
    st.markdown(
        f"<div style='color:{LAYER_COLORS['key_result']};font-weight:600'>■ Key Results</div>",
        unsafe_allow_html=True,
    )
    st.caption("Measurable outcomes.")
with lc3:
    st.markdown(
        f"<div style='color:{LAYER_COLORS['initiative']};font-weight:600'>■ Initiatives</div>",
        unsafe_allow_html=True,
    )
    st.caption("The bets that move KRs.")
with lc4:
    st.markdown(
        f"<div style='color:{LAYER_COLORS['orphan']};font-weight:600'>⚠ Orphan</div>",
        unsafe_allow_html=True,
    )
    st.caption("Incomplete — needs work attached.")

with st.expander("ℹ️ How weights and orphans are computed"):
    st.markdown(
        """
**Weights**
- Each initiative carries its **predicted $ value** from its business case.
- Initiatives with no business case fall back to the median predicted value
  across funded initiatives (or 1.0 if none are funded yet).
- For **multi-KR initiatives**, the initiative's value is **split equally across
  its KR links** — same attribution principle the schema enforces (value lives
  on the business case per initiative; impact lives on the joins per KR link).
- KR-level totals are the sum of all initiative shares flowing into the KR.

**Orphans (red)**
- An **objective with no KRs** is incomplete planning — there's a stated goal
  but no measurable outcome. It appears in red with a "⚠ Define a KR" marker
  as a downstream placeholder so the gap is visible.
- A **KR with no initiatives** is an outcome nobody is actively moving. Also
  red, with a "⚠ No initiative" marker downstream.
- This page is deliberately built to make gaps loud — most OKR tools hide
  incomplete planning behind clean lists, which is the opposite of useful.
        """
    )

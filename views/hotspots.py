"""
Hotspots — operational "what needs my attention?" view, organized as expandable team cards.

Cards on the page show each org's rolled-up health. Click "Show specifics"
on any card to see that team's red KRs, blocked initiatives, planning gaps,
and overdue milestones inline. Multiple cards can be expanded at once.

A small "Other concerns" section at the bottom catches contextless
initiatives — things with no org_unit_id and no KR link — only when "All
org units" is picked.
"""

import streamlit as st
import pandas as pd
from datetime import date
from supabase import create_client, Client

# AI helpers — silently no-op when ANTHROPIC_API_KEY isn't configured
from views._ai_helpers import is_ai_enabled, summarize_hotspots
from views._analytics import track_page
from views._ui_helpers import format_number



# Thresholds — kept consistent with Hotspots v1 + the rest of the app
KR_GREEN_THRESHOLD = 0.7
KR_YELLOW_THRESHOLD = 0.4


@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


sb = get_supabase()


@st.cache_data(ttl=60)
def load_all():
    try:
        check_ins_df = pd.DataFrame(
            sb.table("check_in")
            .select("*")
            .order("created_at", desc=True)
            .execute()
            .data
        )
    except Exception:
        check_ins_df = pd.DataFrame()
    return {
        "org_units": pd.DataFrame(sb.table("org_unit").select("*").execute().data),
        "objectives": pd.DataFrame(sb.table("objective").select("*").execute().data),
        "key_results": pd.DataFrame(sb.table("key_result").select("*").execute().data),
        "initiatives": pd.DataFrame(sb.table("initiative").select("*").execute().data),
        "links": pd.DataFrame(sb.table("initiative_key_result").select("*").execute().data),
        "check_ins": check_ins_df,
    }


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def period_sort_key(period):
    if not period:
        return (9999, 9, period or "")
    if isinstance(period, str) and period.startswith("FY"):
        try:
            return (int(period[2:]), 0, "")
        except ValueError:
            return (9999, 9, period)
    try:
        q, y = period.split("-")
        return (int(y), int(q.lstrip("Q")), "")
    except (ValueError, AttributeError):
        return (9999, 9, period)


def year_from_period(period):
    if not period:
        return None
    if isinstance(period, str) and period.startswith("FY"):
        try:
            return int(period[2:])
        except ValueError:
            return None
    try:
        return int(period.split("-")[1])
    except (ValueError, AttributeError, IndexError):
        return None


def kr_progress(start, target, current):
    if start is None or target is None or current is None:
        return 0.0
    try:
        if target == start:
            return 0.0
        return max(0.0, min(1.0, (current - start) / (target - start)))
    except (TypeError, ZeroDivisionError):
        return 0.0


def grade_color(g):
    if g >= KR_GREEN_THRESHOLD:
        return "🟢"
    if g >= KR_YELLOW_THRESHOLD:
        return "🟡"
    return "🔴"


def safe_str(v):
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


def latest_check_in_note(check_ins, kr_id):
    if check_ins.empty:
        return ""
    rows = check_ins[check_ins["key_result_id"] == kr_id]
    if rows.empty:
        return ""
    rows = rows.sort_values("created_at", ascending=False)
    note = rows.iloc[0].get("note")
    return safe_str(note).strip()


# Color palettes per band — same as v1
COLOR_BAND = {
    "🟢": {"bar": "#22C55E", "tint": "#F0FDF4", "label": "On track"},
    "🟡": {"bar": "#F59E0B", "tint": "#FFFBEB", "label": "Watch"},
    "🔴": {"bar": "#EF4444", "tint": "#FEF2F2", "label": "At risk"},
    "⚪": {"bar": "#9CA3AF", "tint": "#F9FAFB", "label": "No signal"},
}

# Exec RAG icons (mirrors Initiative Updates convention)
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


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
track_page("Hotspots")
st.title("🔥 Hotspots")
st.caption(
    "Experimental layout — same data as Hotspots, organized differently. "
    "Cards are expandable: click any card to see that team's specific "
    "problems inline."
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
check_ins = data["check_ins"]

if org_units.empty:
    st.warning("No org units yet.")
    st.stop()


# -----------------------------------------------------------------------------
# Pickers
# -----------------------------------------------------------------------------
ou_name_by_id = org_units.set_index("id")["name"].to_dict()

level_order = {"company": 0, "segment": 1, "team": 2}
children_by_parent: dict = {}
parent_by_id: dict = {}
for _, row in org_units.iterrows():
    pid = row["parent_unit_id"]
    if pid != pid:
        pid = None
    children_by_parent.setdefault(pid, []).append(row)
    parent_by_id[row["id"]] = pid

tree_labels: list[str] = []
tree_label_to_id: dict = {}


def _walk_org_tree(parent_id, depth):
    siblings = sorted(
        children_by_parent.get(parent_id, []),
        key=lambda r: (level_order.get(r.get("level"), 99), r["name"]),
    )
    for r in siblings:
        prefix = "↳ " * depth
        label = f"{prefix}{r['name']}"
        tree_labels.append(label)
        tree_label_to_id[label] = r["id"]
        _walk_org_tree(r["id"], depth + 1)


_walk_org_tree(None, 0)

ALL_ORGS_LABEL = "All org units"
org_dropdown_options = [ALL_ORGS_LABEL] + tree_labels

existing_quarterly = (
    [p for p in objectives["period"].dropna().unique() if not str(p).startswith("FY")]
    if not objectives.empty else []
)
default_quarters = [
    "Q1-2025", "Q2-2025", "Q3-2025", "Q4-2025",
    "Q1-2026", "Q2-2026", "Q3-2026", "Q4-2026",
    "Q1-2027", "Q2-2027", "Q3-2027", "Q4-2027",
]
period_options = sorted(
    set(existing_quarterly) | set(default_quarters), key=period_sort_key
)

_saved_org_id = st.session_state.get("scope_org_id")
_default_org_idx = 0
if _saved_org_id:
    for _i, _lbl in enumerate(org_dropdown_options):
        if tree_label_to_id.get(_lbl) == _saved_org_id:
            _default_org_idx = _i
            break

_saved_period = st.session_state.get("scope_period")
if _saved_period and _saved_period in period_options:
    default_period_idx = period_options.index(_saved_period)
elif "Q3-2026" in period_options:
    default_period_idx = period_options.index("Q3-2026")
else:
    default_period_idx = 0

pc1, pc2 = st.columns([2, 1])
with pc1:
    selected_org_label = st.selectbox(
        "**Working on**",
        options=org_dropdown_options,
        index=_default_org_idx,
        help=(
            "Pick a specific org unit (shows its family — self + ancestors + "
            "descendants) or 'All org units' for company-wide view."
        ),
    )
with pc2:
    selected_period = st.selectbox(
        "**Period**", options=period_options, index=default_period_idx,
    )

# Persist scope selection so it carries across pages. Selecting "All org
# units" clears the scope (so other pages default to their broadest view too).
if selected_org_label != ALL_ORGS_LABEL:
    _scope_id = tree_label_to_id.get(selected_org_label)
    if _scope_id:
        st.session_state["scope_org_id"] = _scope_id
        st.session_state["scope_org_name"] = ou_name_by_id.get(_scope_id, selected_org_label)
else:
    st.session_state.pop("scope_org_id", None)
    st.session_state.pop("scope_org_name", None)
st.session_state["scope_period"] = selected_period

selected_year = year_from_period(selected_period)
yearly_period = f"FY{selected_year}" if selected_year is not None else None


# -----------------------------------------------------------------------------
# Determine which org units are in scope
# -----------------------------------------------------------------------------
if selected_org_label == ALL_ORGS_LABEL:
    in_scope_ou_ids = set(org_units["id"].tolist())
else:
    selected_ou_id = tree_label_to_id[selected_org_label]
    family = {selected_ou_id}
    cur = parent_by_id.get(selected_ou_id)
    visited = set()
    while cur is not None and cur not in visited:
        family.add(cur)
        visited.add(cur)
        cur = parent_by_id.get(cur)
    stack = list(children_by_parent.get(selected_ou_id, []))
    visited2 = set()
    while stack:
        row = stack.pop()
        rid = row["id"]
        if rid in visited2:
            continue
        visited2.add(rid)
        family.add(rid)
        stack.extend(children_by_parent.get(rid, []))
    in_scope_ou_ids = family


# -----------------------------------------------------------------------------
# Pre-compute objectives / KRs / initiatives / links in scope
# -----------------------------------------------------------------------------
in_scope_periods = {selected_period}
if yearly_period:
    in_scope_periods.add(yearly_period)

in_scope_objs = (
    objectives[
        objectives["org_unit_id"].isin(in_scope_ou_ids)
        & objectives["period"].isin(in_scope_periods)
    ]
    if not objectives.empty else pd.DataFrame()
)
in_scope_obj_ids = set(in_scope_objs["id"]) if not in_scope_objs.empty else set()

in_scope_krs = (
    key_results[key_results["objective_id"].isin(in_scope_obj_ids)]
    if in_scope_obj_ids and not key_results.empty else pd.DataFrame()
)
in_scope_kr_ids = set(in_scope_krs["id"]) if not in_scope_krs.empty else set()

in_scope_links = (
    links[links["key_result_id"].isin(in_scope_kr_ids)]
    if in_scope_kr_ids and not links.empty else pd.DataFrame()
)
in_scope_init_ids = (
    set(in_scope_links["initiative_id"].tolist())
    if not in_scope_links.empty else set()
)
in_scope_inits = (
    initiatives[initiatives["id"].isin(in_scope_init_ids)]
    if in_scope_init_ids and not initiatives.empty else pd.DataFrame()
)

obj_title_by_id = (
    objectives.set_index("id")["title"].to_dict() if not objectives.empty else {}
)


# -----------------------------------------------------------------------------
# Roll-up math — same as v1
# -----------------------------------------------------------------------------
def _objs_for_ou(ou_id):
    return objectives[
        (objectives["org_unit_id"] == ou_id)
        & objectives["period"].isin(in_scope_periods)
    ] if not objectives.empty else pd.DataFrame()


def _krs_for_objs(obj_ids):
    return key_results[key_results["objective_id"].isin(obj_ids)] if obj_ids and not key_results.empty else pd.DataFrame()


def _inits_for_krs(kr_ids):
    if not kr_ids or links.empty:
        return pd.DataFrame()
    lnks = links[links["key_result_id"].isin(kr_ids)]
    init_ids = set(lnks["initiative_id"].tolist())
    if not init_ids:
        return pd.DataFrame()
    return initiatives[initiatives["id"].isin(init_ids)]


def _worst_initiative_signal(init):
    """The 'warning tier' for one initiative — worst of milestone_status and
    exec_rag. Returns: 'blocked', 'off_track', 'at_risk', or None (no warning).

    Skips done/killed initiatives — those aren't current work, so a stale
    milestone or exec flag on them isn't an active warning."""
    if init.get("status") in ("done", "killed"):
        return None
    severity_order = {"blocked": 0, "off_track": 1, "at_risk": 2}
    worst = None
    worst_severity = 99
    for field in ("milestone_status", "exec_rag"):
        v = init.get(field)
        if isinstance(v, str) and v in severity_order:
            if severity_order[v] < worst_severity:
                worst = v
                worst_severity = severity_order[v]
    return worst


def _direct_health(ou_id):
    """Direct health stats — for this OU only, not its descendants.

    Initiatives are gathered from TWO sources, deduped by initiative id:
      1. Initiatives linked (via KR) to a KR under this OU's objectives
      2. Initiatives whose own org_unit_id == this OU (covers orphans —
         initiatives that have an owning team but no KR link)
    """
    ou_objs = _objs_for_ou(ou_id)
    ou_obj_ids = set(ou_objs["id"]) if not ou_objs.empty else set()
    ou_krs = _krs_for_objs(ou_obj_ids)
    linked_inits = _inits_for_krs(set(ou_krs["id"]) if not ou_krs.empty else set())

    # Initiatives explicitly owned by this OU (org_unit_id == ou_id)
    if not initiatives.empty and "org_unit_id" in initiatives.columns:
        owned_inits = initiatives[initiatives["org_unit_id"] == ou_id]
    else:
        owned_inits = pd.DataFrame()

    # Combine, dedupe by id
    if linked_inits.empty and owned_inits.empty:
        all_ou_inits = pd.DataFrame()
    elif linked_inits.empty:
        all_ou_inits = owned_inits
    elif owned_inits.empty:
        all_ou_inits = linked_inits
    else:
        all_ou_inits = pd.concat([linked_inits, owned_inits]).drop_duplicates(subset=["id"])

    kr_green = kr_yellow = kr_red = 0
    for _, kr in ou_krs.iterrows():
        g = kr_progress(kr.get("start_value"), kr.get("target_value"), kr.get("current_value"))
        if g >= KR_GREEN_THRESHOLD:
            kr_green += 1
        elif g >= KR_YELLOW_THRESHOLD:
            kr_yellow += 1
        else:
            kr_red += 1

    init_blocked_or_off = 0
    init_at_risk = 0
    for _, init in all_ou_inits.iterrows():
        signal = _worst_initiative_signal(init)
        if signal in ("blocked", "off_track"):
            init_blocked_or_off += 1
        elif signal == "at_risk":
            init_at_risk += 1

    return {
        "kr_green": kr_green,
        "kr_yellow": kr_yellow,
        "kr_red": kr_red,
        "init_blocked_or_off": init_blocked_or_off,
        "init_at_risk": init_at_risk,
    }


def _rollup(ou_id, memo):
    if ou_id in memo:
        return memo[ou_id]
    h = _direct_health(ou_id).copy()
    for child in children_by_parent.get(ou_id, []):
        child_h = _rollup(child["id"], memo)
        for k in h:
            h[k] += child_h[k]
    memo[ou_id] = h
    return h


def _color_for_rollup(h):
    if h["kr_red"] > 0 or h["init_blocked_or_off"] > 0:
        return "🔴"
    if h["kr_yellow"] > 0 or h["init_at_risk"] > 0:
        return "🟡"
    if h["kr_green"] > 0:
        return "🟢"
    return "⚪"


rollup_memo: dict = {}


# -----------------------------------------------------------------------------
# Per-org specifics — what shows inside an expanded card
# -----------------------------------------------------------------------------
def _ou_family_ids(ou_id):
    """Self + descendants for this OU. Used for 'show this team's stuff' inside
    an expanded card. Ancestors deliberately excluded — drilling into a card
    shows what's beneath it, not what's above."""
    result = {ou_id}
    stack = list(children_by_parent.get(ou_id, []))
    visited = set()
    while stack:
        row = stack.pop()
        rid = row["id"]
        if rid in visited:
            continue
        visited.add(rid)
        result.add(rid)
        stack.extend(children_by_parent.get(rid, []))
    return result


def _problems_for_ou(ou_id):
    """Compute all problem buckets scoped to this org and its descendants.
    Returns a dict of bucket name → list of items.

    Initiatives included in the buckets come from BOTH:
      * Initiatives linked (via KR) to KRs under this family's objectives
      * Initiatives whose org_unit_id is in this family (covers orphans —
        initiatives owned by the team that aren't linked to any KR)
    """
    fam_ou_ids = _ou_family_ids(ou_id) & in_scope_ou_ids
    fam_objs = (
        in_scope_objs[in_scope_objs["org_unit_id"].isin(fam_ou_ids)]
        if not in_scope_objs.empty else pd.DataFrame()
    )
    fam_obj_ids = set(fam_objs["id"]) if not fam_objs.empty else set()
    fam_krs = (
        key_results[key_results["objective_id"].isin(fam_obj_ids)]
        if fam_obj_ids and not key_results.empty else pd.DataFrame()
    )
    fam_kr_ids = set(fam_krs["id"]) if not fam_krs.empty else set()
    fam_links = (
        links[links["key_result_id"].isin(fam_kr_ids)]
        if fam_kr_ids and not links.empty else pd.DataFrame()
    )
    fam_init_ids_from_links = (
        set(fam_links["initiative_id"].tolist())
        if not fam_links.empty else set()
    )
    linked_fam_inits = (
        initiatives[initiatives["id"].isin(fam_init_ids_from_links)]
        if fam_init_ids_from_links and not initiatives.empty else pd.DataFrame()
    )
    # Initiatives directly owned by any org in this family
    if not initiatives.empty and "org_unit_id" in initiatives.columns:
        owned_fam_inits = initiatives[initiatives["org_unit_id"].isin(fam_ou_ids)]
    else:
        owned_fam_inits = pd.DataFrame()
    if linked_fam_inits.empty and owned_fam_inits.empty:
        fam_inits = pd.DataFrame()
    elif linked_fam_inits.empty:
        fam_inits = owned_fam_inits
    elif owned_fam_inits.empty:
        fam_inits = linked_fam_inits
    else:
        fam_inits = pd.concat([linked_fam_inits, owned_fam_inits]).drop_duplicates(subset=["id"])

    ou_for_obj = (
        objectives.set_index("id")["org_unit_id"].to_dict()
        if not objectives.empty else {}
    )

    # 1. Red KRs
    red_krs = []
    for _, kr in fam_krs.iterrows():
        g = kr_progress(kr.get("start_value"), kr.get("target_value"), kr.get("current_value"))
        if g < KR_YELLOW_THRESHOLD:
            red_krs.append({
                "kr": kr, "grade": g,
                "ou_name": ou_name_by_id.get(ou_for_obj.get(kr.get("objective_id")), "?"),
                "obj_title": obj_title_by_id.get(kr.get("objective_id"), "?"),
            })
    red_krs.sort(key=lambda r: r["grade"])

    # 2a. Blocked/off-track initiatives (red tier) — uses worst-of milestone
    # and exec_rag, skips done/killed
    blocked_offtrack = []
    for _, init in fam_inits.iterrows():
        signal = _worst_initiative_signal(init)
        if signal in ("blocked", "off_track"):
            blocked_offtrack.append({
                "init": init, "severity": 0 if signal == "blocked" else 1,
                "via": signal,
            })
    blocked_offtrack.sort(key=lambda r: r["severity"])

    # 2b. At-risk initiatives (yellow tier) — worst-of signal == at_risk
    # (catches milestone-yellow OR exec-yellow when neither is worse)
    at_risk_inits = []
    for _, init in fam_inits.iterrows():
        if _worst_initiative_signal(init) == "at_risk":
            at_risk_inits.append({"init": init})
    at_risk_inits.sort(key=lambda r: safe_str(r["init"].get("title")).lower())

    # NOTE: The previous standalone "exec_flagged" bucket has been removed.
    # Now that blocked_offtrack and at_risk both consider exec_rag via the
    # worst-of signal, every exec warning is already surfaced in one of those
    # buckets. The exec ↔ team divergence (when they differ) is shown inline
    # in the rendered output instead of being its own bucket. Less duplication.

    # 3. Planning gap KRs
    planning_gap_krs = []
    for _, kr in fam_krs.iterrows():
        kr_id = kr["id"]
        current = kr.get("current_value") or 0
        target = kr.get("target_value") or 0
        gap = target - current
        if gap == 0:
            continue
        klinks = fam_links[fam_links["key_result_id"] == kr_id] if not fam_links.empty else pd.DataFrame()
        if klinks.empty:
            continue
        predictions = klinks["predicted_kr_impact"].dropna()
        if predictions.empty:
            continue
        predicted_total = float(predictions.sum())
        if abs(predicted_total) < abs(gap) * 0.5:
            coverage = abs(predicted_total) / abs(gap) if abs(gap) > 0 else 0
            planning_gap_krs.append({
                "kr": kr, "predicted_total": predicted_total,
                "gap": gap, "coverage": coverage,
                "ou_name": ou_name_by_id.get(ou_for_obj.get(kr.get("objective_id")), "?"),
                "obj_title": obj_title_by_id.get(kr.get("objective_id"), "?"),
            })
    planning_gap_krs.sort(key=lambda r: r["coverage"])

    # 5. Past milestone date
    today = date.today()
    past_ms_inits = []
    for _, init in fam_inits.iterrows():
        ms_date = parse_date_safe(init.get("next_milestone_date"))
        if ms_date and ms_date < today and init.get("status") not in ("done", "killed"):
            past_ms_inits.append({
                "init": init,
                "days_overdue": (today - ms_date).days,
                "ms_date": ms_date,
            })
    past_ms_inits.sort(key=lambda r: -r["days_overdue"])

    return {
        "red_krs": red_krs,
        "blocked_offtrack": blocked_offtrack,
        "at_risk_inits": at_risk_inits,
        "planning_gap_krs": planning_gap_krs,
        "past_milestone_inits": past_ms_inits,
    }


# -----------------------------------------------------------------------------
# Rendering helpers for expanded card content
# -----------------------------------------------------------------------------
def _render_red_kr(r):
    kr = r["kr"]
    unit = kr.get("metric_unit") or ""
    owner = safe_str(kr.get("owner")) or "—"
    last_note = latest_check_in_note(check_ins, kr["id"])
    note_part = f' &nbsp;·&nbsp; <i>"{last_note}"</i>' if last_note else ""
    st.markdown(
        f"<div style='margin-left:16px;line-height:1.55;margin-bottom:8px'>"
        f"<b>{kr['title']}</b> "
        f"<span style='color:#6B7280;font-size:0.9em'>"
        f"(under: {r['obj_title']})</span><br>"
        f"<span style='color:#6B7280;font-size:0.9em'>"
        f"current <b>{format_number(kr.get('current_value'))} {unit}</b> · "
        f"target {format_number(kr.get('target_value'))} {unit} · "
        f"{r['grade']:.0%} to goal · owner: {owner}"
        f"{note_part}"
        f"</span></div>",
        unsafe_allow_html=True,
    )


def _render_problem_init(p, ms_icon_override=None):
    """Render one initiative warning row. Shows the worst-of signal as the
    primary state, with an inline "exec X · team Y" annotation when the two
    fields disagree."""
    init = p["init"]
    ms = init.get("milestone_status")
    exec_rag = init.get("exec_rag")
    worst = _worst_initiative_signal(init)

    # Icon: caller can override (for the at_risk yellow tier render), else
    # use the worst-of signal's icon
    icon = ms_icon_override or EXEC_RAG_ICONS.get(worst, "🔴")
    label = MS_LABELS.get(worst, "")

    # Build the "(via exec, divergent from team)" annotation when exec and
    # milestone disagree. This is what the previous exec_flagged bucket
    # surfaced — now shown inline.
    severity_order = {"blocked": 0, "off_track": 1, "at_risk": 2, "on_track": 3}
    annotation = ""
    if isinstance(ms, str) and isinstance(exec_rag, str) and ms != exec_rag:
        # Surface the divergence — useful when (say) exec marks "blocked"
        # but team marks "at_risk" (escalation gap), or vice versa.
        ms_str = MS_LABELS.get(ms, ms)
        exec_str = MS_LABELS.get(exec_rag, exec_rag)
        annotation = (
            f" · <span style='color:#6B7280'>exec: {EXEC_RAG_ICONS.get(exec_rag, '')} {exec_str}"
            f" / team: {EXEC_RAG_ICONS.get(ms, '')} {ms_str}</span>"
        )
    elif isinstance(exec_rag, str) and exec_rag in severity_order and not isinstance(ms, str):
        # Exec set but milestone is null — show that the signal is exec-only
        annotation = f" · <span style='color:#6B7280'>via exec ({MS_LABELS.get(exec_rag, exec_rag)})</span>"
    elif isinstance(ms, str) and ms in severity_order and not isinstance(exec_rag, str):
        # Milestone set but exec is null — show that the signal is team-only
        annotation = f" · <span style='color:#6B7280'>via team ({MS_LABELS.get(ms, ms)})</span>"

    owner = safe_str(init.get("owner")) or "—"
    exec_narrative = safe_str(init.get("exec_narrative")).strip()
    narrative_part = (
        f' &nbsp;·&nbsp; <i>"{exec_narrative}"</i>' if exec_narrative else ""
    )
    next_ms = safe_str(init.get("next_milestone_text")).strip()
    next_date = parse_date_safe(init.get("next_milestone_date"))
    ms_part = ""
    if next_ms:
        ms_part = f" · next: {next_ms}"
        if next_date:
            ms_part += f" ({next_date.isoformat()})"
    label_part = f" ({label})" if label else ""
    st.markdown(
        f"<div style='margin-left:16px;line-height:1.55;margin-bottom:8px'>"
        f"{icon} <b>{init['title']}</b>"
        f"<span style='color:#6B7280;font-size:0.9em'>{label_part}{annotation}</span><br>"
        f"<span style='color:#6B7280;font-size:0.9em'>"
        f"owner: {owner} · delivery {init.get('progress_pct') or 0}%"
        f"{ms_part}{narrative_part}"
        f"</span></div>",
        unsafe_allow_html=True,
    )


def _render_planning_gap(r):
    kr = r["kr"]
    unit = kr.get("metric_unit") or ""
    st.markdown(
        f"<div style='margin-left:16px;line-height:1.55;margin-bottom:8px'>"
        f"<b>{kr['title']}</b> "
        f"<span style='color:#6B7280;font-size:0.9em'>"
        f"(under: {r['obj_title']})</span><br>"
        f"<span style='color:#6B7280;font-size:0.9em'>"
        f"predicted total: <b>{r['predicted_total']:+g} {unit}</b> · "
        f"gap to target: {r['gap']:+g} {unit} · "
        f"<b>{r['coverage']:.0%} of gap covered</b>"
        f"</span></div>",
        unsafe_allow_html=True,
    )


def _render_past_milestone(p):
    init = p["init"]
    owner = safe_str(init.get("owner")) or "—"
    ms_text = safe_str(init.get("next_milestone_text")).strip() or "(no milestone text)"
    st.markdown(
        f"<div style='margin-left:16px;line-height:1.55;margin-bottom:8px'>"
        f"<b>{init['title']}</b> "
        f"<span style='color:#6B7280;font-size:0.9em'>"
        f"· {p['days_overdue']} day{'s' if p['days_overdue'] != 1 else ''} overdue"
        f"</span><br>"
        f"<span style='color:#6B7280;font-size:0.9em'>"
        f"milestone: <i>{ms_text}</i> (due {p['ms_date'].isoformat()}) · "
        f"status: {init.get('status') or '—'} · owner: {owner}"
        f"</span></div>",
        unsafe_allow_html=True,
    )


def _render_expanded_card_content(ou_id):
    """Render the specifics for an expanded card — this team's problems."""
    problems = _problems_for_ou(ou_id)
    total_p = sum(len(v) for v in problems.values())

    if total_p == 0:
        st.success(
            "✓ Nothing flagged for this team in scope. KRs on track, "
            "initiatives not blocked or escalated."
        )
        return

    # Render each bucket if non-empty
    if problems["red_krs"]:
        st.markdown(f"**🔴 KRs below 40% to target ({len(problems['red_krs'])})**")
        for r in problems["red_krs"]:
            _render_red_kr(r)

    if problems["blocked_offtrack"]:
        st.markdown(
            f"**🚧 Blocked or off-track initiatives ({len(problems['blocked_offtrack'])})**"
        )
        for p in problems["blocked_offtrack"]:
            _render_problem_init(p)

    if problems["at_risk_inits"]:
        st.markdown(
            f"**🟡 At-risk initiatives ({len(problems['at_risk_inits'])})**"
        )
        for p in problems["at_risk_inits"]:
            _render_problem_init(p, ms_icon_override="🟡")

    if problems["planning_gap_krs"]:
        st.markdown(
            f"**⚠️ KRs with insufficient predicted impact "
            f"({len(problems['planning_gap_krs'])})**"
        )
        st.caption(
            "_Predicted total impact covers less than 50% of the gap to target._"
        )
        for r in problems["planning_gap_krs"]:
            _render_planning_gap(r)

    if problems["past_milestone_inits"]:
        st.markdown(
            f"**📅 Initiatives past milestone date "
            f"({len(problems['past_milestone_inits'])})**"
        )
        for p in problems["past_milestone_inits"]:
            _render_past_milestone(p)


# -----------------------------------------------------------------------------
# Card rendering — collapsed and expanded states
# -----------------------------------------------------------------------------
def _render_org_card_v2(r, h, depth):
    """Render a card. Header shows: color bar, name, label, mini stacked bar,
    KR breakdown text, init warning summary. Click 'Show specifics' to expand
    inline — that toggle persists in session state per-OU."""
    ou_id = r["id"]
    color = _color_for_rollup(h)
    band = COLOR_BAND[color]
    indent_px = depth * 24

    kr_total = h["kr_green"] + h["kr_yellow"] + h["kr_red"]

    expand_key = f"hotspots_v2_expanded_{ou_id}"
    is_expanded = st.session_state.get(expand_key, False)

    # Open the colored container div
    st.markdown(
        f"<div style='margin-left:{indent_px}px;"
        f"border-left:6px solid {band['bar']};"
        f"background:{band['tint']};"
        f"padding:10px 14px;border-radius:4px;margin-bottom:8px'>",
        unsafe_allow_html=True,
    )

    # Header line + toggle button
    c_name, c_btn = st.columns([4, 1])
    with c_name:
        st.markdown(
            f"<div style='font-size:1.05em'>"
            f"{color} &nbsp; <b>{r['name']}</b> &nbsp;"
            f"<span style='color:#6B7280;font-size:0.85em'>{band['label']}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with c_btn:
        toggle_label = "▾ Hide specifics" if is_expanded else "▸ Show specifics"
        if st.button(toggle_label, key=f"toggle_{ou_id}", use_container_width=True):
            st.session_state[expand_key] = not is_expanded
            st.rerun()

    # KR breakdown
    if kr_total > 0:
        pct_green = (h["kr_green"] / kr_total) * 100
        pct_yellow = (h["kr_yellow"] / kr_total) * 100
        pct_red = (h["kr_red"] / kr_total) * 100
        st.markdown(
            f"<div style='display:flex;height:8px;border-radius:4px;"
            f"overflow:hidden;margin:6px 0 8px 0;background:#E5E7EB'>"
            f"{'<div style=\"background:#22C55E;width:' + str(pct_green) + '%\"></div>' if pct_green > 0 else ''}"
            f"{'<div style=\"background:#F59E0B;width:' + str(pct_yellow) + '%\"></div>' if pct_yellow > 0 else ''}"
            f"{'<div style=\"background:#EF4444;width:' + str(pct_red) + '%\"></div>' if pct_red > 0 else ''}"
            f"</div>",
            unsafe_allow_html=True,
        )
        kr_parts = []
        if h["kr_green"] > 0:
            kr_parts.append(f"🟢 {h['kr_green']}")
        if h["kr_yellow"] > 0:
            kr_parts.append(f"🟡 {h['kr_yellow']}")
        if h["kr_red"] > 0:
            kr_parts.append(f"🔴 {h['kr_red']}")
        kr_text = " · ".join(kr_parts) + f" &nbsp;<span style='color:#9CA3AF'>({kr_total} KRs total)</span>"
    else:
        kr_text = "<span style='color:#9CA3AF'>no KRs in scope</span>"

    init_parts = []
    if h["init_blocked_or_off"] > 0:
        init_parts.append(f"🚧 {h['init_blocked_or_off']} blocked/off-track")
    if h["init_at_risk"] > 0:
        init_parts.append(f"🟡 {h['init_at_risk']} at-risk")
    init_text = " · ".join(init_parts) if init_parts else "<span style='color:#9CA3AF'>no initiative warnings</span>"

    st.markdown(
        f"<div style='color:#374151;font-size:0.9em;line-height:1.5'>"
        f"<b>KRs:</b> {kr_text}<br>"
        f"<b>Initiatives:</b> {init_text}"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Expanded specifics — inline if toggled on
    if is_expanded:
        st.markdown(
            "<hr style='border:none;border-top:1px solid #E5E7EB;margin:12px 0'>",
            unsafe_allow_html=True,
        )
        _render_expanded_card_content(ou_id)

    # Close the colored container
    st.markdown("</div>", unsafe_allow_html=True)


def _render_rollup(parent_id, depth):
    siblings = sorted(
        children_by_parent.get(parent_id, []),
        key=lambda r: (level_order.get(r.get("level"), 99), r["name"]),
    )
    for r in siblings:
        ou_id = r["id"]
        if ou_id not in in_scope_ou_ids:
            _render_rollup(ou_id, depth + 1)
            continue
        h = _rollup(ou_id, rollup_memo)
        _render_org_card_v2(r, h, depth)
        _render_rollup(ou_id, depth + 1)


# -----------------------------------------------------------------------------
# AI-generated exec summary
# -----------------------------------------------------------------------------
# Runs Sonnet 4.6 over a compact structured brief and shows a 3-5 sentence
# "what should I focus on" summary above the org cards. Cached in session
# state keyed by scope + a hash of the underlying data, so switching scopes
# regenerates but reloading the page doesn't re-hit the API.
#
# Silently omitted if ANTHROPIC_API_KEY isn't configured.
if is_ai_enabled():
    # Build the structured brief. Only computed for the in-scope orgs so
    # switching to "All org units" vs a specific team produces materially
    # different summaries.
    def _build_hotspots_brief():
        """Compact structured brief for the AI. Reuses the same rollup and
        problem-bucket math the cards use — the summary is generated from
        the same data a leader is looking at, not raw tables."""
        # Determine which orgs are in scope for the summary
        if selected_org_label == ALL_ORGS_LABEL:
            scope_ou_ids = set(in_scope_ou_ids)
            scope_label = f"All org units · {selected_period}"
        else:
            root_id = tree_label_to_id[selected_org_label]
            scope_ou_ids = _ou_family_ids(root_id) & in_scope_ou_ids
            scope_label = (
                f"{ou_name_by_id.get(root_id, selected_org_label)} · "
                f"{selected_period}"
            )

        # Aggregate totals across all in-scope orgs
        totals = {
            "kr_red": 0, "kr_yellow": 0, "kr_green": 0,
            "init_blocked_or_off": 0, "init_at_risk": 0, "init_on_track": 0,
        }
        team_briefs = []

        for ou_id in scope_ou_ids:
            h = _direct_health(ou_id)
            for k in totals:
                totals[k] += h.get(k, 0)

            # Skip orgs that have nothing to report (no KRs, no initiatives)
            _has_content = any(
                h.get(k, 0) > 0 for k in
                ("kr_red", "kr_yellow", "kr_green",
                 "init_blocked_or_off", "init_at_risk", "init_on_track")
            )
            if not _has_content:
                continue

            probs = _problems_for_ou(ou_id)
            rollup_h = _rollup(ou_id, rollup_memo)
            team_briefs.append({
                "name": ou_name_by_id.get(ou_id, "?"),
                "rollup_color": _color_for_rollup(rollup_h),
                "red_krs": [
                    {
                        "title": r["kr"].get("title", "?"),
                        "grade": r["grade"],
                        "unit": r["kr"].get("metric_unit", ""),
                    }
                    for r in probs.get("red_krs", [])[:3]
                ],
                "blocked_or_offtrack": [
                    {
                        "title": p["init"].get("title", "?"),
                        "milestone_status": p["init"].get("milestone_status"),
                        "exec_rag": p["init"].get("exec_rag"),
                    }
                    for p in probs.get("blocked_offtrack", [])[:3]
                ],
                "at_risk": [
                    {"title": p["init"].get("title", "?")}
                    for p in probs.get("at_risk_inits", [])[:2]
                ],
                "past_milestone": [
                    {
                        "title": p["init"].get("title", "?"),
                        "due_date": str(p.get("due_date", "?")),
                    }
                    for p in probs.get("past_milestone", [])[:2]
                ],
            })

        # Sort teams by severity (worst first) so the AI reads the concerning
        # ones early
        severity_order = {"🔴": 0, "🟡": 1, "🟢": 2, "⚪": 3}
        team_briefs.sort(key=lambda t: severity_order.get(t["rollup_color"], 9))

        return {
            "scope_label": scope_label,
            "totals": totals,
            "teams": team_briefs,
            "cross_functional_patterns": _cross_patterns,
        }

    # ---- Cross-functional pattern computation ----
    # Compute BEFORE the brief so cross-functional data can flow into the
    # AI summary. Result is reused by the display panel further down.
    def _compute_cross_functional_early(initiatives_df, key_results_df, objectives_df, links_df, org_units_df):
        """Identify initiatives whose owning team differs from the team owning
        the linked KRs. See fuller docstring on the display code below."""
        if initiatives_df.empty or links_df.empty:
            return [], {}
        _obj_by_id = objectives_df.set_index("id").to_dict("index") if not objectives_df.empty else {}
        _kr_by_id = key_results_df.set_index("id").to_dict("index") if not key_results_df.empty else {}
        _ou_by_id = org_units_df.set_index("id")["name"].to_dict() if not org_units_df.empty else {}
        patterns = []
        contributes = {}
        receives = {}
        for _, init in initiatives_df.iterrows():
            init_ou_id = init.get("org_unit_id")
            if not init_ou_id or (isinstance(init_ou_id, float) and pd.isna(init_ou_id)):
                continue
            if init.get("status") in ("done", "killed"):
                continue
            _init_links = links_df[links_df["initiative_id"] == init["id"]]
            if _init_links.empty:
                continue
            for _, _lk in _init_links.iterrows():
                kr_id = _lk["key_result_id"]
                kr = _kr_by_id.get(kr_id)
                if not kr:
                    continue
                obj = _obj_by_id.get(kr.get("objective_id"))
                if not obj:
                    continue
                kr_ou_id = obj.get("org_unit_id")
                if not kr_ou_id or kr_ou_id == init_ou_id:
                    continue
                patterns.append({
                    "initiative_id": init["id"],
                    "initiative_title": init.get("title", "?"),
                    "initiative_status": init.get("status"),
                    "initiative_ms": init.get("milestone_status"),
                    "initiative_rag": init.get("exec_rag"),
                    "contributing_team_id": init_ou_id,
                    "contributing_team": _ou_by_id.get(init_ou_id, "?"),
                    "receiving_team_id": kr_ou_id,
                    "receiving_team": _ou_by_id.get(kr_ou_id, "?"),
                    "kr_title": kr.get("title", "?"),
                })
                contributes.setdefault(init_ou_id, set()).add(kr_ou_id)
                receives.setdefault(kr_ou_id, set()).add(init_ou_id)
        return patterns, {"contributes_to_others": contributes, "receives_from_others": receives}

    _cross_patterns, _cross_aggregate = _compute_cross_functional_early(
        initiatives, key_results, objectives, links, org_units
    )

    # Cache key: scope + a hash of the totals (a simple proxy for "did the
    # underlying data change"). If data changes, cache invalidates on its own.
    _brief = _build_hotspots_brief()
    _cache_key = f"hotspots_ai_summary_{selected_org_label}_{selected_period}"
    _brief_signature = str(_brief["totals"])  # cheap change-detection
    _sig_key = f"{_cache_key}__sig"

    # Regenerate if scope changed, if data changed, or if user clicked refresh
    _need_regen = (
        _cache_key not in st.session_state
        or st.session_state.get(_sig_key) != _brief_signature
    )

    with st.container(border=True):
        _hc1, _hc2 = st.columns([5, 1])
        with _hc1:
            st.markdown(
                "<div style='font-weight:600;font-size:1em;color:#374151'>"
                "✨ AI-generated summary</div>",
                unsafe_allow_html=True,
            )
        with _hc2:
            if st.button(
                "🔄 Refresh",
                key="refresh_hotspots_summary",
                use_container_width=True,
                help="Regenerate the summary from the current data.",
            ):
                _need_regen = True
                st.session_state.pop(_cache_key, None)

        if _need_regen:
            with st.spinner("Reading the data..."):
                _summary = summarize_hotspots(_brief)
            if _summary:
                st.session_state[_cache_key] = _summary
                st.session_state[_sig_key] = _brief_signature
            else:
                # API failed. Show previous summary if we have one, else a
                # small note. Don't crash the page.
                if _cache_key not in st.session_state:
                    st.caption(
                        "_Summary temporarily unavailable — the org cards "
                        "below reflect the current state directly._"
                    )
                else:
                    st.caption(
                        "_Couldn't refresh; showing the previous summary._"
                    )

        _cached_summary = st.session_state.get(_cache_key)
        if _cached_summary:
            st.markdown(
                f"<div style='color:#1F2937;font-size:0.95em;"
                f"line-height:1.55;margin-top:6px'>{_cached_summary}</div>",
                unsafe_allow_html=True,
            )
        st.caption(
            "_Generated by Claude Sonnet from the same data shown below. "
            "May miss nuance the cards make visible._"
        )


# -----------------------------------------------------------------------------
# Cross-functional patterns panel
# -----------------------------------------------------------------------------
# Uses _cross_patterns and _cross_aggregate computed above (before the AI
# summary, so the pattern data can also flow into the summary prompt).

if _cross_patterns:
    with st.container(border=True):
        st.markdown(
            "<div style='font-weight:600;font-size:1em;color:#374151'>"
            "🔗 Cross-functional patterns</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "Where work owned by one team is moving another team's KRs. "
            "This is where TPM coordination happens — the seams between "
            "teams where alignment, dependency, and handoff live."
        )

        # ---- Rendered list of cross-team initiative → KR links ----
        # A little map from milestone_status → dot for visual scannability
        _ms_dot = {
            "on_track": "🟢", "at_risk": "🟡", "blocked": "🔴",
        }
        _rag_dot = {
            "on_track": "🟢", "at_risk": "🟡", "off_track": "🔴",
        }

        st.markdown(
            "<div style='font-size:0.88em;color:#6B7280;margin:8px 0 4px'>"
            f"<b>{len(_cross_patterns)} cross-functional link"
            f"{'s' if len(_cross_patterns) != 1 else ''}:</b>"
            "</div>",
            unsafe_allow_html=True,
        )

        for _p in sorted(_cross_patterns, key=lambda p: (p["contributing_team"], p["initiative_title"])):
            _ms = _ms_dot.get(_p.get("initiative_ms") or "", "⚪")
            _rag = _rag_dot.get(_p.get("initiative_rag") or "", "⚪")
            # Format the pattern as: [dot dot] Contributing team's *Init* → moving Receiving team's *KR*
            st.markdown(
                f"<div style='margin:4px 0 4px 12px;font-size:0.92em;line-height:1.5'>"
                f"{_ms}{_rag} <b>{_p['contributing_team']}</b>'s "
                f"<i>{_p['initiative_title']}</i>  "
                f"<span style='color:#9CA3AF'>→ moving</span>  "
                f"<b>{_p['receiving_team']}</b>'s <i>{_p['kr_title']}</i>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # ---- Coordination-load tally ----
        # For each org unit that shows up, count how many other-team relationships
        # they're on the giving vs receiving side of. Highlights asymmetries.
        _all_teams_involved = set(_cross_aggregate["contributes_to_others"].keys()) | set(_cross_aggregate["receives_from_others"].keys())

        if len(_all_teams_involved) >= 2:
            st.markdown(
                "<div style='font-size:0.88em;color:#6B7280;margin:14px 0 4px'>"
                "<b>Coordination load by team:</b>"
                "</div>",
                unsafe_allow_html=True,
            )
            _load_rows = []
            for _ou_id in _all_teams_involved:
                _team_name = org_units.set_index("id")["name"].get(_ou_id, "?") if not org_units.empty else "?"
                _contributing_to_count = len(_cross_aggregate["contributes_to_others"].get(_ou_id, set()))
                _receiving_from_count = len(_cross_aggregate["receives_from_others"].get(_ou_id, set()))
                _load_rows.append((_team_name, _contributing_to_count, _receiving_from_count))

            for _team_name, _giving, _receiving in sorted(_load_rows, key=lambda r: -(r[1] + r[2])):
                # Interesting when giving vs receiving is imbalanced
                _imbalance_note = ""
                if _giving > 0 and _receiving == 0:
                    _imbalance_note = "  <span style='color:#9CA3AF;font-size:0.9em'>· providing service to others, not receiving</span>"
                elif _receiving > 0 and _giving == 0:
                    _imbalance_note = "  <span style='color:#9CA3AF;font-size:0.9em'>· dependent on others' work, not contributing back</span>"
                st.markdown(
                    f"<div style='margin:3px 0 3px 12px;font-size:0.9em'>"
                    f"<b>{_team_name}</b>: contributing to "
                    f"{_giving} team{'s' if _giving != 1 else ''}, "
                    f"receiving from {_receiving} team{'s' if _receiving != 1 else ''}"
                    f"{_imbalance_note}"
                    f"</div>",
                    unsafe_allow_html=True,
                )


# -----------------------------------------------------------------------------
# Render the page
# -----------------------------------------------------------------------------
st.divider()
st.header("🩺 Org Health Roll-Up")
if selected_org_label == ALL_ORGS_LABEL:
    st.caption(
        f"Each org's health for {selected_period} and FY{selected_year} "
        "aspirational KRs. Click **Show specifics** on any card to see "
        "that team's red KRs, blocked initiatives, and other problems "
        "inline."
    )
else:
    st.caption(
        f"Showing the **{ou_name_by_id.get(tree_label_to_id[selected_org_label])}** "
        f"family. Health for {selected_period} and FY{selected_year} "
        "aspirational KRs."
    )

_render_rollup(None, 0)


# -----------------------------------------------------------------------------
# Other concerns — initiatives that have NEITHER a KR link nor an org_unit_id
# -----------------------------------------------------------------------------
# An initiative with org_unit_id set now shows under its owning team's card
# (whether or not it's linked to a KR). The Other concerns section is for the
# truly-contextless case: no org, no KR, and we don't know where to put it.
# Only shown when 'All org units' is picked, since these have no scope.
if selected_org_label == ALL_ORGS_LABEL:
    all_links_init_ids = (
        set(links["initiative_id"].tolist()) if not links.empty else set()
    )
    if not initiatives.empty:
        has_no_kr_link = ~initiatives["id"].isin(all_links_init_ids)
        has_no_org = (
            initiatives["org_unit_id"].isna()
            if "org_unit_id" in initiatives.columns
            else pd.Series([True] * len(initiatives), index=initiatives.index)
        )
        contextless = initiatives[has_no_kr_link & has_no_org]
    else:
        contextless = pd.DataFrame()

    if not contextless.empty:
        st.divider()
        st.header(
            f"🪨 Other concerns: contextless initiatives "
            f"({len(contextless)})"
        )
        st.caption(
            "_These initiatives have neither a linked KR nor an owning org "
            "unit, so they have no context for reporting. Set an owning org "
            "unit on **Manage → Create Initiative**, link them to a KR, or "
            "delete if no longer relevant._"
        )
        for _, init in contextless.sort_values("title").iterrows():
            owner = safe_str(init.get("owner")) or "—"
            status = init.get("status") or "—"
            st.markdown(
                f"<div style='margin-left:8px;line-height:1.55'>"
                f"<b>{init['title']}</b> "
                f"<span style='color:#6B7280;font-size:0.9em'>"
                f"· status: {status} · owner: {owner}"
                f"</span></div>",
                unsafe_allow_html=True,
            )
            st.write("")


# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.divider()
st.caption(
    "Experimental v2 — same data as Hotspots, organized as expandable team "
    "cards instead of a flat triage list. Try both, pick the one that lands."
)

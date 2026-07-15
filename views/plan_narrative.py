"""
Plan Narrative — a read-only cascade view of the planning portfolio.

What this page is for:
  Thinking. Not editing, not visualizing flows — just reading the plan as a
  document, top to bottom, so you can spot logic gaps and multi-KR initiatives.

What's on the page:
  1. Cascade: Strategy → Yearly Objective → Quarterly Objective → Key Result
     Scoped by org unit + period, with walk-up of ancestor units so the team's
     quarterlies sit inside the broader strategy context.
  2. Initiatives section: every initiative in scope (i.e. linked to at least
     one in-scope KR), with the KRs it moves listed underneath. Multi-KR
     initiatives surface naturally because their "Moves these KRs" list has
     more than one bullet.

How this differs from Flow:
  Flow is a Sankey — weighted, visual, "where does the portfolio concentrate?"
  Summary is a document — textual, structural, "what's the planning story?"
  Both exist for the same reason a company has both a strategy slide AND a
  strategy memo: same content, different cognitive surface.

How this differs from Plan a Quarter:
  Plan a Quarter is a workspace — editing, KR updates, new objectives, new
  initiatives. Summary is read-only and broader-scope (shows ancestor strategy
  context, not just this quarter's bets).
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client
from views._analytics import track_page



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
    }


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def period_sort_key(period: str) -> tuple:
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


def year_from_period(period: str):
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


def safe_str(v) -> str:
    return v if isinstance(v, str) else ""


def format_kr_value(kr) -> str:
    """Compact 'Start → Current → Target unit' string."""
    unit = kr.get("metric_unit") or ""
    start = kr.get("start_value")
    current = kr.get("current_value")
    target = kr.get("target_value")
    if current is None:
        return f"_no current value_ · target {target} {unit}"
    return f"{current} / {target} {unit}"


def indicator_badge(t) -> str:
    """Small HTML badge for inline display next to a KR title.
    Summary renders via cascade_line which permits HTML, so we use a
    proper styled badge here rather than the plain-emoji fallback used
    on pages that go through st.expander labels."""
    if t == "lagging":
        return (
            " <span style='background:#FEE2E2;color:#991B1B;padding:1px 6px;"
            "border-radius:8px;font-size:0.75em'>🎯 LAGGING</span>"
        )
    if t == "leading":
        return (
            " <span style='background:#DBEAFE;color:#1E40AF;padding:1px 6px;"
            "border-radius:8px;font-size:0.75em'>📡 LEADING</span>"
        )
    return ""


# Each cascade level adds this many pixels of left padding. Generous enough
# that nested levels are obviously below their parents at a glance.
INDENT_PX = 28


def cascade_line(level: int, html: str) -> None:
    """Render one line of the cascade with depth-based left padding.

    Streamlit collapses leading whitespace in markdown, so we use inline
    CSS margin-left instead. Each level shifts the line right by INDENT_PX
    pixels — about three characters at default font size, enough to be
    visually obvious without wasting horizontal space.
    """
    st.markdown(
        f"<div style='margin-left:{level * INDENT_PX}px;line-height:1.55'>{html}</div>",
        unsafe_allow_html=True,
    )


def cascade_caption(level: int, text: str) -> None:
    """Muted-gray caption-style line, indented to match its parent."""
    st.markdown(
        f"<div style='margin-left:{level * INDENT_PX}px;"
        f"color:#6B7280;font-size:0.9em;line-height:1.5;margin-bottom:4px'>"
        f"{text}</div>",
        unsafe_allow_html=True,
    )


def obj_status_chip(status: str) -> str:
    """Status badge for objectives — categorical, not progress.

    Active objectives are the default and get no chip (the page would be
    a sea of green dots otherwise). Only non-active statuses surface, in
    muted gray so they don't compete with KR progress colors below.
    """
    if status == "active" or not status:
        return ""
    return (
        f" <span style='color:#6B7280;font-size:0.8em;"
        f"background:#F3F4F6;padding:1px 6px;border-radius:8px'>"
        f"{status}</span>"
    )


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
track_page("Executive Narrative")
st.title("📄 Executive Narrative")
st.caption(
    "The plan as a document. Strategy cascades into yearly and quarterly "
    "objectives with their KRs, then every initiative in scope is listed "
    "with the KRs it moves. Read-only — for thinking, not editing."
)
st.markdown(
    "<div style='color:#6B7280;font-size:0.85em'>"
    "🟢🟡🔴 dots show <b>KR progress</b> against target "
    "(green ≥70%, yellow ≥40%, red below). "
    "Objectives don't get progress dots — only a small chip when they're "
    "non-active (closed, archived)."
    "</div>",
    unsafe_allow_html=True,
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

if org_units.empty:
    st.warning("No org units yet.")
    st.stop()


# -----------------------------------------------------------------------------
# Pickers: org unit (tree) + period
# -----------------------------------------------------------------------------
ou_name_by_id = org_units.set_index("id")["name"].to_dict()

# Build the org-unit tree picker (same pattern as Plan a Quarter)
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


def _walk_org_tree(parent_id, depth: int):
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

# Quarterly periods only — yearly objectives surface via the FY{year} derived
# from the picked quarter, so the user doesn't have to think about both.
existing_quarterly = (
    [p for p in objectives["period"].dropna().unique() if not str(p).startswith("FY")]
    if not objectives.empty else []
)
default_quarters = [
    "Q1-2025", "Q2-2025", "Q3-2025", "Q4-2025",
    "Q1-2026", "Q2-2026", "Q3-2026", "Q4-2026",
    "Q1-2027", "Q2-2027", "Q3-2027", "Q4-2027",
]
period_options = sorted(set(existing_quarterly) | set(default_quarters), key=period_sort_key)

pc1, pc2 = st.columns([2, 1])
with pc1:
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
        help="Pick the org unit you want a summary for. Persists across pages.",
    )
with pc2:
    _saved_period = st.session_state.get("scope_period")
    if _saved_period and _saved_period in period_options:
        default_period_idx = period_options.index(_saved_period)
    elif "Q3-2026" in period_options:
        default_period_idx = period_options.index("Q3-2026")
    else:
        default_period_idx = 0
    selected_period = st.selectbox(
        "**Period**", options=period_options, index=default_period_idx
    )

selected_ou_id = tree_label_to_id[selected_ou_label]
selected_ou_name = ou_name_by_id[selected_ou_id]
selected_year = year_from_period(selected_period)
yearly_period = f"FY{selected_year}" if selected_year is not None else None

# Persist scope
st.session_state["scope_org_id"] = selected_ou_id
st.session_state["scope_org_name"] = selected_ou_name
st.session_state["scope_period"] = selected_period


# -----------------------------------------------------------------------------
# Walk org tree to determine what to show: ancestors (for context) + self +
# descendants (so picking a parent org includes its teams' plans)
# -----------------------------------------------------------------------------
# Ancestors, root-first — provides the strategic context above the selection
ids_up: list = []
visited: set = set()
cur = selected_ou_id
while cur is not None and cur not in visited:
    ids_up.append(cur)
    visited.add(cur)
    cur = parent_by_id.get(cur)
ancestors_and_self = list(reversed(ids_up))  # root-first, ending at selected

# Descendants of selected, walked breadth-first so nearer children come first
descendant_ids: list = []
_stack = [c["id"] for c in children_by_parent.get(selected_ou_id, [])]
_seen: set = set()
while _stack:
    _cid = _stack.pop(0)
    if _cid in _seen:
        continue
    _seen.add(_cid)
    descendant_ids.append(_cid)
    _stack.extend(c["id"] for c in children_by_parent.get(_cid, []))

# Combined render order: ancestors → self → descendants
chain_ids = ancestors_and_self + descendant_ids


# -----------------------------------------------------------------------------
# CASCADE: Strategy → Yearly Objective → Quarterly Objective → KR
# -----------------------------------------------------------------------------
st.divider()
st.header("Planning Cascade")
st.caption(
    f"How the plan reads, top to bottom — {selected_ou_name} · {selected_period}. "
    "Ancestors appear at the top for strategic context; descendant teams follow "
    "the selected unit so the whole family reads in one flow."
)

obj_title_by_id = (
    objectives.set_index("id")["title"].to_dict() if not objectives.empty else {}
)

# Track which KRs we've rendered as quarterly so the in-scope-KR set is known
# when building the initiatives section below.
quarterly_kr_ids_in_scope: set = set()

for depth, ou_id in enumerate(chain_ids):
    ou_here = ou_name_by_id.get(ou_id, "?")
    is_current = ou_id == selected_ou_id

    # Org-unit header (no extra indent; the page already has body margin)
    marker = "  ←  *current scope*" if is_current else ""
    st.markdown(f"#### {ou_here}{marker}")

    # Strategies for this unit + selected fiscal year
    unit_strategies = (
        strategies[
            (strategies["org_unit_id"] == ou_id)
            & (strategies["fiscal_year"] == selected_year)
        ]
        if not strategies.empty and selected_year is not None
        else pd.DataFrame()
    )

    if unit_strategies.empty:
        cascade_caption(1, f"_No strategy defined at this level for FY{selected_year}._")
        continue

    for _, strat in unit_strategies.sort_values("title").iterrows():
        # Strategy line at level 1
        cascade_line(1, f"📜 <b>Strategy:</b> {strat['title']}")
        sdesc = strat.get("description")
        if isinstance(sdesc, str) and sdesc.strip():
            cascade_caption(1, sdesc.strip())

        # Yearly objectives under this strategy
        strat_yearly = (
            objectives[
                (objectives["strategy_id"] == strat["id"])
                & (objectives["period"] == yearly_period)
            ]
            if not objectives.empty and yearly_period
            else pd.DataFrame()
        )

        if strat_yearly.empty:
            cascade_caption(2, "_No yearly objectives under this strategy._")
            continue

        for _, yo in strat_yearly.sort_values("title").iterrows():
            yo_status = yo.get("status", "active")
            cascade_line(
                2,
                f"<b>Yearly:</b> {yo['title']}{obj_status_chip(yo_status)}",
            )

            # Aspirational KRs on the yearly objective (level 3)
            yearly_krs = (
                key_results[key_results["objective_id"] == yo["id"]]
                if not key_results.empty
                else pd.DataFrame()
            )
            if not yearly_krs.empty:
                for _, ykr in yearly_krs.sort_values("title").iterrows():
                    grade = kr_progress(
                        ykr.get("start_value"),
                        ykr.get("target_value"),
                        ykr.get("current_value"),
                    )
                    cascade_line(
                        3,
                        f"{grade_color(grade)} <i>Aspirational KR:</i> "
                        f"{ykr['title']}{indicator_badge(ykr.get('indicator_type'))} "
                        f"<span style='color:#6B7280;font-size:0.9em'>"
                        f"[{format_kr_value(ykr)}]</span>",
                    )

            # Quarterly objectives that ladder up to THIS yearly.
            # Only render quarterlies when we're at the CURRENT org unit — otherwise
            # ancestor sections would balloon with every team's quarterly bets.
            quarterly_under_yo = (
                objectives[
                    (objectives["parent_objective_id"] == yo["id"])
                    & (objectives["period"] == selected_period)
                ]
                if not objectives.empty
                else pd.DataFrame()
            )
            if not quarterly_under_yo.empty and is_current:
                for _, qo in quarterly_under_yo.sort_values("title").iterrows():
                    qo_status = qo.get("status", "active")
                    cascade_line(
                        3,
                        f"<b>Quarterly ({selected_period}):</b> {qo['title']}"
                        f"{obj_status_chip(qo_status)}",
                    )
                    # KRs on this quarterly (level 4)
                    qkrs = (
                        key_results[key_results["objective_id"] == qo["id"]]
                        if not key_results.empty
                        else pd.DataFrame()
                    )
                    for _, qkr in qkrs.sort_values("title").iterrows():
                        quarterly_kr_ids_in_scope.add(qkr["id"])
                        grade = kr_progress(
                            qkr.get("start_value"),
                            qkr.get("target_value"),
                            qkr.get("current_value"),
                        )
                        cascade_line(
                            4,
                            f"{grade_color(grade)} <i>KR:</i> "
                            f"{qkr['title']}{indicator_badge(qkr.get('indicator_type'))} "
                            f"<span style='color:#6B7280;font-size:0.9em'>"
                            f"[{format_kr_value(qkr)}]</span>",
                        )

    st.write("")  # tiny gap between org-unit blocks

# Unaligned section — quarterlies in scope with no in-scope yearly parent.
# Uses the same family (selected + descendants) as the cascade above so a
# child-team's unaligned quarterly still surfaces when a parent org is picked.
_family_org_ids = set(chain_ids) if 'chain_ids' in dir() else {selected_ou_id}
unparented_q = (
    objectives[
        objectives["org_unit_id"].isin(_family_org_ids)
        & (objectives["period"] == selected_period)
    ]
    if not objectives.empty else pd.DataFrame()
)
if not unparented_q.empty:
    truly_unaligned = []
    for _, qo in unparented_q.iterrows():
        parent_id = qo.get("parent_objective_id")
        if parent_id != parent_id:
            parent_id = None
        parent_in_scope = False
        if parent_id:
            parent_obj_row = objectives[objectives["id"] == parent_id]
            if not parent_obj_row.empty:
                p_period = parent_obj_row.iloc[0].get("period")
                if isinstance(p_period, str) and p_period.startswith("FY"):
                    parent_in_scope = True
        if not parent_in_scope:
            truly_unaligned.append(qo)

    if truly_unaligned:
        st.markdown("##### 🔸 Unaligned (no yearly parent)")
        st.caption(
            "These quarterlies don't ladder up to any yearly objective in this "
            "org unit's scope. Legitimate (matrix work), but called out."
        )
        for qo in truly_unaligned:
            qo_status = qo.get("status", "active")
            cascade_line(
                1,
                f"<b>Quarterly ({selected_period}):</b> {qo['title']}"
                f"{obj_status_chip(qo_status)}",
            )
            qkrs = (
                key_results[key_results["objective_id"] == qo["id"]]
                if not key_results.empty else pd.DataFrame()
            )
            for _, qkr in qkrs.sort_values("title").iterrows():
                quarterly_kr_ids_in_scope.add(qkr["id"])
                grade = kr_progress(
                    qkr.get("start_value"),
                    qkr.get("target_value"),
                    qkr.get("current_value"),
                )
                cascade_line(
                    2,
                    f"{grade_color(grade)} <i>KR:</i> "
                    f"{qkr['title']}{indicator_badge(qkr.get('indicator_type'))} "
                    f"<span style='color:#6B7280;font-size:0.9em'>"
                    f"[{format_kr_value(qkr)}]</span>",
                )


# -----------------------------------------------------------------------------
# INITIATIVES SECTION
# -----------------------------------------------------------------------------
st.divider()

# Find every initiative linked to at least one in-scope KR
in_scope_links = (
    links[links["key_result_id"].isin(quarterly_kr_ids_in_scope)]
    if not links.empty and quarterly_kr_ids_in_scope else pd.DataFrame()
)
init_ids_in_scope = (
    set(in_scope_links["initiative_id"].tolist())
    if not in_scope_links.empty else set()
)
inits_in_scope = (
    initiatives[initiatives["id"].isin(init_ids_in_scope)]
    if init_ids_in_scope and not initiatives.empty else pd.DataFrame()
)

st.header(f"Initiatives in scope ({len(inits_in_scope)})")
st.caption(
    "Every initiative linked to at least one in-scope KR. Multi-KR initiatives "
    "have more than one bullet under 'Moves these KRs' — the natural way to "
    "spot bets that pull multiple levers."
)

if inits_in_scope.empty:
    st.info(
        "No initiatives are linked to any KR in this scope. Either no bets "
        "are proposed yet, or none ladder up to the KRs in this org+period."
    )
else:
    # For each initiative, gather its KR links (filtered to in-scope KRs only)
    kr_title_by_id = (
        key_results.set_index("id")["title"].to_dict()
        if not key_results.empty else {}
    )
    kr_unit_by_id = (
        key_results.set_index("id")["metric_unit"].to_dict()
        if not key_results.empty else {}
    )

    # Sort: status (active first), then by # of in-scope KRs moved (descending)
    status_rank = {"active": 0, "proposed": 1, "done": 2, "killed": 3}
    init_rows = []
    for _, init in inits_in_scope.iterrows():
        init_links = in_scope_links[in_scope_links["initiative_id"] == init["id"]]
        init_rows.append({
            "init": init,
            "links": init_links,
            "status_rank": status_rank.get(init.get("status"), 99),
            "kr_count": len(init_links),
        })
    init_rows.sort(key=lambda r: (r["status_rank"], -r["kr_count"], safe_str(r["init"].get("title"))))

    for row in init_rows:
        init = row["init"]
        init_links_local = row["links"]
        status = init.get("status", "—")
        status_icon = {
            "proposed": "💭",
            "active": "🟢",
            "done": "✅",
            "killed": "🪦",
        }.get(status, "")
        owner = safe_str(init.get("owner")) or "—"
        delivery = init.get("progress_pct") or 0
        multi_kr_tag = (
            f" &nbsp;<span style='background:#FEF3C7;color:#92400E;padding:1px 6px;"
            f"border-radius:8px;font-size:0.75em'>📌 moves {row['kr_count']} KRs</span>"
            if row["kr_count"] > 1 else ""
        )

        st.markdown(
            f"#### {status_icon} {init['title']}{multi_kr_tag}",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<span style='color:#6B7280;font-size:0.9em'>"
            f"Status: {status} · Owner: {owner} · Delivery: {delivery}%"
            f"</span>",
            unsafe_allow_html=True,
        )

        idesc = init.get("description")
        if isinstance(idesc, str) and idesc.strip():
            st.caption(idesc.strip())

        st.markdown("**Moves these KRs:**")
        for _, lk in init_links_local.iterrows():
            kr_id = lk["key_result_id"]
            kr_title = kr_title_by_id.get(kr_id, "?")
            kr_unit = kr_unit_by_id.get(kr_id) or ""
            predicted = lk.get("predicted_kr_impact")
            actual = lk.get("actual_kr_impact")
            if predicted is None or predicted != predicted:  # NaN
                impact_str = "_no prediction yet_"
            else:
                impact_str = f"predicted +{predicted:g} {kr_unit}"
            actual_str = ""
            if actual is not None and actual == actual and actual != 0:
                actual_str = f" &nbsp;·&nbsp; <i>actual +{actual:g} {kr_unit}</i>"
            st.markdown(
                f"&nbsp;&nbsp;→ {kr_title} "
                f"<span style='color:#6B7280;font-size:0.9em'>"
                f"({impact_str}{actual_str})</span>",
                unsafe_allow_html=True,
            )

        st.write("")  # gap between initiatives


# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.divider()
st.caption(
    "This page is for reading and thinking. For weighted portfolio visuals, "
    "see **Plan Flow**. For editing, see **Plan a Quarter** or **Annual Strategy & "
    "Objectives**."
)

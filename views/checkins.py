"""
Check-ins — a lightweight surface for updating KR current values.

Different from Plan a Quarter:
  * That page is for PLANNING — titles, targets, parent objectives, initiatives,
    business cases. Lots of structural editing.
  * This page is for EXECUTION — weekly update of "where are we now?" on each
    KR. Only the current_value and an optional note are editable. Title,
    target, unit, parent objective, owner — all locked.

Why a separate page: mature OKR systems (Lattice, Workboard, Gtmhub) all have
a dedicated check-in surface for a reason. It keeps the cadence quick, the
form narrow, and prevents accidental drift of structural fields during a
weekly status update.

Scope:
  Pick an org unit + a period. The page shows both the QUARTERLY KRs (tracked
  weekly) and the YEARLY aspirational KRs for the same fiscal year (typically
  updated quarterly during reviews). Both horizons in one check-in surface.

History:
  Saving a check-in with a non-empty note also inserts a row in `check_in`
  for time-series history. Saving with no note only updates the KR's
  current_value (no history entry). Each row has a small "▸ history (N)"
  disclosure showing the last 5 check-ins for that KR.

Save behavior:
  All edits are tracked in session state. One "Save all changes" button at the
  bottom commits everything. Discard reverts.
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
    # check_in table is new; tolerate its absence so the page still works
    # before the migration is applied.
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
        "check_ins": check_ins_df,
    }


def clear_cache():
    load_all.clear()


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
    if period.startswith("FY"):
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
    """Return a str safely, treating pandas NaN as empty."""
    if isinstance(v, str):
        return v
    return ""


def fmt_date(ts) -> str:
    """Format a timestamp as 'Nov 12'."""
    try:
        dt = pd.to_datetime(ts)
        return dt.strftime("%b %d")
    except Exception:
        return "?"


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("📈 Check-ins")
st.caption(
    "Update current values and add a note on each KR. Pick an org unit and "
    "period — the page shows quarterly KRs *and* yearly aspirational KRs for "
    "the same fiscal year. Only current values and notes are editable; "
    "everything else is locked."
)

try:
    data = load_all()
except Exception as e:
    st.error(f"Couldn't reach Supabase: {e}")
    st.stop()

org_units = data["org_units"]
objectives = data["objectives"]
key_results = data["key_results"]
check_ins = data["check_ins"]

if org_units.empty:
    st.warning("No org units yet. Add at least one on **Manage → Org Units** first.")
    st.stop()

if key_results.empty:
    st.warning(
        "No KRs defined yet. Use **Plan a Quarter** or **Annual Strategy & "
        "Objectives** to add some first."
    )
    st.stop()


# -----------------------------------------------------------------------------
# Pickers: org unit (tree) + period (quarterly)
# -----------------------------------------------------------------------------
ou_name_by_id = org_units.set_index("id")["name"].to_dict()

ou_sorted = org_units.copy()
level_order = {"company": 0, "segment": 1, "team": 2}
ou_sorted["__order"] = ou_sorted["level"].map(level_order).fillna(99)
ou_sorted = ou_sorted.sort_values(["__order", "name"])

# Build indented tree labels
children_by_parent: dict = {}
for _, row in org_units.iterrows():
    pid = row["parent_unit_id"]
    if pid != pid:
        pid = None
    children_by_parent.setdefault(pid, []).append(row)

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

# Quarterly periods derived from data + sensible defaults
existing_quarterly = (
    [p for p in objectives["period"].dropna().unique() if not str(p).startswith("FY")]
    if not objectives.empty
    else []
)
default_quarters = [
    "Q1-2025", "Q2-2025", "Q3-2025", "Q4-2025",
    "Q1-2026", "Q2-2026", "Q3-2026", "Q4-2026",
    "Q1-2027", "Q2-2027", "Q3-2027", "Q4-2027",
]
period_options = sorted(
    set(existing_quarterly) | set(default_quarters), key=period_sort_key
)

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
        help="Pick the org unit whose KRs you want to update. Persists across pages.",
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

# Persist scope
st.session_state["scope_org_id"] = selected_ou_id
st.session_state["scope_org_name"] = selected_ou_name
st.session_state["scope_period"] = selected_period


# -----------------------------------------------------------------------------
# Find KRs in scope
# -----------------------------------------------------------------------------
quarterly_objs = (
    objectives[
        (objectives["org_unit_id"] == selected_ou_id)
        & (objectives["period"] == selected_period)
    ]
    if not objectives.empty
    else pd.DataFrame()
)
quarterly_obj_ids = set(quarterly_objs["id"]) if not quarterly_objs.empty else set()
quarterly_krs = (
    key_results[key_results["objective_id"].isin(quarterly_obj_ids)]
    if quarterly_obj_ids
    else pd.DataFrame()
)

yearly_period = f"FY{selected_year}" if selected_year is not None else None
yearly_objs = (
    objectives[
        (objectives["org_unit_id"] == selected_ou_id)
        & (objectives["period"] == yearly_period)
    ]
    if yearly_period and not objectives.empty
    else pd.DataFrame()
)
yearly_obj_ids = set(yearly_objs["id"]) if not yearly_objs.empty else set()
yearly_krs = (
    key_results[key_results["objective_id"].isin(yearly_obj_ids)]
    if yearly_obj_ids
    else pd.DataFrame()
)


# -----------------------------------------------------------------------------
# Session state for pending edits
# -----------------------------------------------------------------------------
# Keyed per (org_unit, period). Stores pending value AND note edits per KR.
# Structure: { kr_id: { "value": float, "note": str } }
scope_key = f"{selected_ou_id}::{selected_period}"
pending_state_key = f"checkin_pending::{scope_key}"
if pending_state_key not in st.session_state:
    st.session_state[pending_state_key] = {}

pending: dict = st.session_state[pending_state_key]


def _kr_check_in_history(kr_id, limit: int = 5):
    """Return the last N check-ins for a KR, most recent first."""
    if check_ins.empty:
        return pd.DataFrame()
    rows = check_ins[check_ins["key_result_id"] == kr_id]
    if rows.empty:
        return rows
    # Sort defensively (load_all already orders desc, but session state may shift it)
    return rows.sort_values("created_at", ascending=False).head(limit)


def _render_kr_row(kr, obj_title: str):
    """Render one KR as a check-in row with editable current value + note,
    plus a 'history' disclosure for prior check-ins."""
    kr_id = kr["id"]
    unit = kr.get("metric_unit") or ""
    start = kr.get("start_value")
    target = kr.get("target_value")
    stored_current = kr.get("current_value")
    owner_str = safe_str(kr.get("owner")) or "—"

    pending_entry = pending.get(kr_id, {})
    display_current = pending_entry.get("value", stored_current)
    display_note = pending_entry.get("note", "")

    grade = kr_progress(start, target, display_current)
    is_pending = kr_id in pending
    edited_marker = (
        " &nbsp;·&nbsp; <span style='color:#F59E0B'>● pending</span>"
        if is_pending else ""
    )

    # Header row: dot · title · owner · start → current → target
    h1, h2, h_owner, h3, h4, h5 = st.columns([0.4, 3.4, 1.0, 1.0, 1.3, 1.3])
    with h1:
        st.markdown(
            f"<div style='padding-top:26px;font-size:1.1em'>{grade_color(grade)}</div>",
            unsafe_allow_html=True,
        )
    with h2:
        st.markdown(
            f"**{kr['title']}**{edited_marker}<br>"
            f"<span style='color:#6B7280;font-size:0.85em'>"
            f"under: {obj_title}"
            f"</span>",
            unsafe_allow_html=True,
        )
    with h_owner:
        # Owner column — subdued label, owner name in normal weight so it
        # reads alongside the values without competing with the KR title.
        st.markdown(
            f"<div style='padding-top:18px;color:#6B7280;font-size:0.85em'>Owner</div>"
            f"<div style='font-size:0.95em'>{owner_str}</div>",
            unsafe_allow_html=True,
        )
    with h3:
        st.markdown(
            f"<div style='padding-top:26px;color:#6B7280;font-size:0.9em'>"
            f"Start: <b>{start} {unit}</b></div>",
            unsafe_allow_html=True,
        )
    with h4:
        new_value = st.number_input(
            f"Current ({unit})" if unit else "Current",
            value=float(display_current or 0),
            step=1.0,
            format="%.2f",
            key=f"current_{kr_id}_{scope_key}",
            label_visibility="visible",
        )
    with h5:
        st.markdown(
            f"<div style='padding-top:26px;color:#6B7280;font-size:0.9em'>"
            f"Target: <b>{target} {unit}</b><br>"
            f"<span style='color:#9CA3AF'>{grade:.0%} to goal</span></div>",
            unsafe_allow_html=True,
        )

    # Note input — full width below the row
    note_value = st.text_input(
        "Note for this check-in (optional)",
        value=display_note,
        key=f"note_{kr_id}_{scope_key}",
        placeholder=(
            "Why is this where it is? Any context for the exec review? "
            "(Saved to history when you save.)"
        ),
    )

    # Track pending state
    value_changed = new_value != (stored_current or 0)
    note_changed = bool(note_value.strip())
    if value_changed or note_changed:
        pending[kr_id] = {
            "value": new_value,
            "note": note_value.strip(),
            # Keep a flag so the save loop knows whether to write a check_in row
            "value_changed": value_changed,
            "note_changed": note_changed,
        }
    elif kr_id in pending:
        del pending[kr_id]

    # History disclosure — collapsed by default
    history_df = _kr_check_in_history(kr_id, limit=5)
    history_count = len(history_df)
    if history_count > 0:
        with st.expander(f"▸ history ({history_count})", expanded=False):
            for _, row in history_df.iterrows():
                date_str = fmt_date(row.get("created_at"))
                value = row.get("value")
                note = safe_str(row.get("note")).strip()
                note_part = f' · _"{note}"_' if note else " · _(no note)_"
                st.markdown(
                    f"<span style='color:#6B7280;font-size:0.9em'>"
                    f"<b>{date_str}</b> · {value} {unit}{note_part}"
                    f"</span>",
                    unsafe_allow_html=True,
                )

    st.divider()


# -----------------------------------------------------------------------------
# Render: Quarterly KRs section
# -----------------------------------------------------------------------------
obj_title_by_id = (
    objectives.set_index("id")["title"].to_dict() if not objectives.empty else {}
)

st.divider()
st.subheader(
    f"Quarterly Key Results — {selected_period} "
    f"({len(quarterly_krs)})"
)
st.caption("Updated weekly. These are the outcomes being moved by this quarter's bets.")

if quarterly_krs.empty:
    st.info(
        f"No quarterly KRs for **{selected_ou_name}** in {selected_period}. "
        "Add KRs to quarterly objectives on the **Plan a Quarter** page."
    )
else:
    quarterly_krs_sorted = quarterly_krs.copy()
    quarterly_krs_sorted["__obj_title"] = quarterly_krs_sorted["objective_id"].map(
        obj_title_by_id
    )
    quarterly_krs_sorted = quarterly_krs_sorted.sort_values(["__obj_title", "title"])
    for _, kr in quarterly_krs_sorted.iterrows():
        obj_title = obj_title_by_id.get(kr["objective_id"], "?")
        _render_kr_row(kr, obj_title)


# -----------------------------------------------------------------------------
# Render: Yearly KRs section
# -----------------------------------------------------------------------------
st.subheader(
    f"Yearly Aspirational Key Results — FY{selected_year} "
    f"({len(yearly_krs)})"
)
st.caption(
    "Updated quarterly during reviews, not weekly. These are the long-arc "
    "aspirational outcomes — quarterly bets ladder up to them."
)

if yearly_krs.empty:
    st.info(
        f"No yearly KRs for **{selected_ou_name}** in FY{selected_year}. "
        "Aspirational KRs are added on the **Annual Strategy & Objectives** page."
    )
else:
    yearly_krs_sorted = yearly_krs.copy()
    yearly_krs_sorted["__obj_title"] = yearly_krs_sorted["objective_id"].map(
        obj_title_by_id
    )
    yearly_krs_sorted = yearly_krs_sorted.sort_values(["__obj_title", "title"])
    for _, kr in yearly_krs_sorted.iterrows():
        obj_title = obj_title_by_id.get(kr["objective_id"], "?")
        _render_kr_row(kr, obj_title)


# -----------------------------------------------------------------------------
# Save / Discard bar at the bottom
# -----------------------------------------------------------------------------
pending_count = len(pending)

if pending_count == 0:
    st.caption(
        "No pending changes. Edit a current value or add a note above to "
        "begin a check-in."
    )
else:
    bc1, bc2, bc3 = st.columns([2, 1, 1])
    with bc1:
        st.markdown(
            f"**{pending_count} pending change"
            f"{'s' if pending_count != 1 else ''}** — not yet saved."
        )
    with bc2:
        if st.button("💾 Save all changes", type="primary", use_container_width=True):
            success_count = 0
            history_count = 0
            errors = []
            for kr_id, edit in pending.items():
                try:
                    # Update KR current_value if it changed
                    if edit.get("value_changed"):
                        sb.table("key_result").update(
                            {"current_value": edit["value"]}
                        ).eq("id", kr_id).execute()
                    # Insert a check_in history row whenever there's a value
                    # change OR a non-empty note. (Pure note-only entries
                    # capture context even if the value didn't move.)
                    if edit.get("value_changed") or edit.get("note_changed"):
                        try:
                            sb.table("check_in").insert(
                                {
                                    "key_result_id": kr_id,
                                    "value": edit["value"],
                                    "note": edit["note"] or None,
                                }
                            ).execute()
                            history_count += 1
                        except Exception as ce:
                            # If the check_in table doesn't exist yet, the value
                            # update still succeeded — note this but don't fail.
                            errors.append(
                                f"History for KR {kr_id} not saved "
                                f"(table missing?): {ce}"
                            )
                    success_count += 1
                except Exception as e:
                    errors.append(f"KR {kr_id}: {e}")
            st.session_state[pending_state_key] = {}
            clear_cache()
            if errors:
                st.warning(
                    f"Saved {success_count} of {pending_count} updates "
                    f"({history_count} with history). "
                    f"Some issues: {' · '.join(errors[:3])}"
                )
            else:
                st.success(
                    f"Saved {success_count} update"
                    f"{'s' if success_count != 1 else ''}"
                    f" ({history_count} with history)."
                )
            st.rerun()
    with bc3:
        if st.button("↩️ Discard", use_container_width=True):
            st.session_state[pending_state_key] = {}
            st.rerun()


# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.divider()
st.caption(
    "Check-ins are about *current state* and context. To restructure KRs — "
    "rename, retarget, re-parent, change owner — head over to **Plan a "
    "Quarter** or **Annual Strategy & Objectives**."
)

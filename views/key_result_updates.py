"""
Key Result Updates — execution reporting surface for KRs (weekly cadence).

Owns the weekly "where are we now?" check-in:
  * Current value (the metric being tracked)
  * Optional note explaining context for execs and history
  * Implicit time series: a check_in row is inserted whenever value moves
    OR when a non-empty note is provided

Scope:
  Pick an org unit + a period. The page shows both the QUARTERLY KRs (tracked
  weekly) AND the YEARLY aspirational KRs for the same fiscal year (typically
  updated quarterly during reviews). Both horizons in one surface.

Layout:
  Each KR is its own bordered box, always visible (no expand-to-edit). Quarterly
  KRs group under their parent Quarterly Objective so the team scans by goal,
  not by abstract list. Yearly aspirational KRs get their own bottom section.

Save behavior:
  All edits batch into session state. One 'Save all changes' button at the
  bottom commits everything; Discard reverts.
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client

# AI helpers — silently no-op when ANTHROPIC_API_KEY isn't configured
from views._ai_helpers import is_ai_enabled, review_kr_checkin, render_review
from views._analytics import track_page
from views._ui_helpers import format_number



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
        # Initiatives + links loaded for the "linked initiatives" reference
        # panel on each KR box (read-only — visible context for the
        # team while writing check-in notes).
        "initiatives": pd.DataFrame(sb.table("initiative").select("*").execute().data),
        "links": pd.DataFrame(sb.table("initiative_key_result").select("*").execute().data),
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
    return v if isinstance(v, str) else ""


def fmt_date(ts) -> str:
    try:
        return pd.to_datetime(ts).strftime("%b %d")
    except Exception:
        return "?"


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
track_page("Key Result Check-ins")
st.title("📈 Key Result Check-ins")
st.caption(
    "Update current values and add context notes for KRs. Quarterly KRs are "
    "tracked weekly; yearly aspirational KRs typically quarterly. Only "
    "current values and notes are editable here — structural fields "
    "(title, target, owner) live on **Plan a Quarter** or **Annual Strategy**."
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
initiatives_df = data["initiatives"]
links_df = data["links"]

# Lookup for initiative title/owner/status by id
init_by_id = (
    initiatives_df.set_index("id").to_dict("index")
    if not initiatives_df.empty else {}
)


# Exec health emoji (mirrors Initiative Updates page convention)
EXEC_RAG_ICONS = {
    "on_track":  "🟢",
    "at_risk":   "🟡",
    "off_track": "🔴",
    "blocked":   "🚧",
}

if org_units.empty:
    st.warning("No org units yet.")
    st.stop()

if key_results.empty:
    st.warning(
        "No KRs defined yet. Use **Plan a Quarter** or **Annual Strategy & "
        "Objectives** to add some first."
    )
    st.stop()


# -----------------------------------------------------------------------------
# Pickers: org unit (tree) + period (quarterly) + owner
# -----------------------------------------------------------------------------
ou_name_by_id = org_units.set_index("id")["name"].to_dict()

ou_sorted = org_units.copy()
level_order = {"company": 0, "segment": 1, "team": 2}
ou_sorted["__order"] = ou_sorted["level"].map(level_order).fillna(99)
ou_sorted = ou_sorted.sort_values(["__order", "name"])

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

# Owner picker — pulled from key_results.owner field
owner_values = sorted(
    {
        o for o in key_results["owner"].dropna().tolist()
        if isinstance(o, str) and o.strip()
    }
)
ALL_OWNERS_LABEL = "All owners"
NO_OWNER_LABEL = "— No owner set"
owner_options = [ALL_OWNERS_LABEL] + owner_values + [NO_OWNER_LABEL]

pc1, pc2, pc3 = st.columns([2, 1, 1])
with pc1:
    # Sticky-scope default
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
with pc3:
    selected_owner = st.selectbox(
        "**Owner**",
        options=owner_options,
        index=0,
        help=(
            "Filter to KRs owned by a specific person, or pick "
            f"'{NO_OWNER_LABEL}' to surface KRs missing an owner."
        ),
    )

selected_ou_id = tree_label_to_id[selected_ou_label]
selected_ou_name = ou_name_by_id[selected_ou_id]
selected_year = year_from_period(selected_period)

st.session_state["scope_org_id"] = selected_ou_id
st.session_state["scope_org_name"] = selected_ou_name
st.session_state["scope_period"] = selected_period


# -----------------------------------------------------------------------------
# Find KRs in scope, then apply owner filter
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


def apply_owner_filter(df):
    if df.empty:
        return df
    if selected_owner == ALL_OWNERS_LABEL:
        return df
    if selected_owner == NO_OWNER_LABEL:
        return df[df["owner"].isna() | (df["owner"].fillna("").str.strip() == "")]
    return df[df["owner"] == selected_owner]


quarterly_krs = apply_owner_filter(quarterly_krs)
yearly_krs = apply_owner_filter(yearly_krs)


# -----------------------------------------------------------------------------
# Session state for pending edits — keyed per (org_unit, period)
# -----------------------------------------------------------------------------
scope_key = f"{selected_ou_id}::{selected_period}"
pending_state_key = f"checkin_pending::{scope_key}"
if pending_state_key not in st.session_state:
    st.session_state[pending_state_key] = {}

pending: dict = st.session_state[pending_state_key]


def _kr_check_in_history(kr_id, limit: int = 5):
    if check_ins.empty:
        return pd.DataFrame()
    rows = check_ins[check_ins["key_result_id"] == kr_id]
    if rows.empty:
        return rows
    return rows.sort_values("created_at", ascending=False).head(limit)


def render_kr_box(kr):
    """Render one KR as a bordered box with editable current value + note +
    history disclosure. Same fields as before, just in a always-visible box
    instead of needing to expand."""
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

    with st.container(border=True):
        # Indicator emoji (🎯 lagging / 📡 leading) shown right after the
        # progress dot — same convention as Plan a Quarter / Annual.
        _ind_type = kr.get("indicator_type")
        indicator_prefix = ""
        if _ind_type == "lagging":
            indicator_prefix = "🎯 "
        elif _ind_type == "leading":
            indicator_prefix = "📡 "
        # Title row
        st.markdown(
            f"{grade_color(grade)} {indicator_prefix}&nbsp; **{kr['title']}**{edited_marker}",
            unsafe_allow_html=True,
        )

        # 4-column row: Owner · Start · Current (editable) · Target
        h_owner, h_start, h_cur, h_tgt = st.columns([1.2, 1, 1.3, 1.3])
        with h_owner:
            st.markdown(
                f"<div style='color:#6B7280;font-size:0.85em'>Owner</div>"
                f"<div style='font-size:0.95em'>{owner_str}</div>",
                unsafe_allow_html=True,
            )
        with h_start:
            st.markdown(
                f"<div style='color:#6B7280;font-size:0.85em'>Start</div>"
                f"<div style='font-size:0.95em'><b>{format_number(start)} {unit}</b></div>",
                unsafe_allow_html=True,
            )
        with h_cur:
            new_value = st.number_input(
                f"Current ({unit})" if unit else "Current",
                value=float(display_current or 0),
                step=1.0,
                format="%.2f",
                key=f"current_{kr_id}_{scope_key}",
                label_visibility="visible",
            )
        with h_tgt:
            st.markdown(
                f"<div style='color:#6B7280;font-size:0.85em'>Target</div>"
                f"<div style='font-size:0.95em'><b>{format_number(target)} {unit}</b><br>"
                f"<span style='color:#9CA3AF'>{grade:.0%} to goal</span></div>",
                unsafe_allow_html=True,
            )

        # Note row
        note_value = st.text_input(
            "Note for this check-in (optional)",
            value=display_note,
            key=f"note_{kr_id}_{scope_key}",
            placeholder=(
                "Why is this where it is? Any context for exec review? "
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
                "value_changed": value_changed,
                "note_changed": note_changed,
            }
        elif kr_id in pending:
            del pending[kr_id]

        # --- AI review of this KR check-in ------------------------------
        # Reads the CURRENT typed values (new_value, note_value) rather than
        # what's saved — this way a team lead can iterate on the wording
        # before committing to Save all.
        #
        # DELIBERATELY session-only (not persisted to DB) because a KR
        # check-in note is ephemeral: type it, save it into the check_in
        # history, note field returns to empty. Persisting the review to
        # the KR row would make it look stale on every page load (there's
        # no "current" note to compare against). So the review lives in
        # session state, matching the transience of the underlying note.
        # (Initiative reviews are different — they evaluate persistent
        # state on the initiative row, so they persist to the DB.)
        if is_ai_enabled():
            _kr_review_key = f"kr_review_{kr_id}"

            with st.expander("✨ Ask AI to review this check-in", expanded=False):
                st.caption(
                    "Claude Sonnet will look at the new value, the note, and "
                    "recent history — and tell you whether the note reads "
                    "the trend or just reports a number. Review is temporary "
                    "and disappears when you leave the page."
                )
                _krc1, _krc2 = st.columns([1, 3])
                with _krc1:
                    _existing = st.session_state.get(_kr_review_key)
                    _kr_btn_label = "🔄 Regenerate" if _existing else "✨ Review"
                    if st.button(
                        _kr_btn_label,
                        key=f"kr_review_btn_{kr_id}_{scope_key}",
                        use_container_width=True,
                    ):
                        # Build recent history package
                        _hist_df = _kr_check_in_history(kr_id, limit=5)
                        _recent_history = []
                        for _, _r in _hist_df.iterrows():
                            _recent_history.append({
                                "value": _r.get("value"),
                                "note": _r.get("note"),
                                "when": fmt_date(_r.get("created_at")),
                            })
                        _checkin_pkg = {
                            "kr_title": kr.get("title", "?"),
                            "unit": unit,
                            "start": start,
                            "target": target,
                            "previous_value": stored_current,
                            "new_value": new_value,
                            "recent_history": _recent_history,
                            "note": note_value.strip(),
                        }
                        with st.spinner("Reviewing..."):
                            _review = review_kr_checkin(_checkin_pkg)
                        if _review:
                            st.session_state[_kr_review_key] = _review
                            st.rerun()
                        else:
                            st.warning(
                                "Couldn't generate a review right now. Try again in a moment."
                            )

                _cached_kr_review = st.session_state.get(_kr_review_key)
                if _cached_kr_review:
                    st.markdown("---")
                    render_review(_cached_kr_review)

        # History disclosure (collapsed by default)
        history_df = _kr_check_in_history(kr_id, limit=5)
        if len(history_df) > 0:
            with st.expander(f"▸ history ({len(history_df)})", expanded=False):
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

        # Linked initiatives reference panel — read-only context for the
        # team while writing check-in notes. KR Updates is for *direct
        # measurement* of where the KR is now (the world moves it regardless
        # of any one initiative). But seeing which initiatives are aimed
        # at this KR helps the team write a more informed note when the
        # value moves — "did our onboarding redesign land? is the marketing
        # tailwind real?" Actual_kr_impact attribution lives elsewhere
        # (Initiative Updates) where each link's measurement is captured.
        kr_init_links = (
            links_df[links_df["key_result_id"] == kr_id]
            if not links_df.empty else pd.DataFrame()
        )
        link_count = len(kr_init_links)
        if link_count > 0:
            with st.expander(f"▸ linked initiatives ({link_count})", expanded=False):
                # Table format mirrors the Objectives & KRs page so the
                # two surfaces speak the same vocabulary. Same columns,
                # same column order — only difference is this one's
                # nested inside a disclosure and read-only.
                rows = []
                for _, lk in kr_init_links.iterrows():
                    init = init_by_id.get(lk["initiative_id"], {})
                    owner_val = init.get("owner")
                    exec_rag = init.get("exec_rag")
                    exec_icon = (
                        EXEC_RAG_ICONS.get(exec_rag, "—")
                        if isinstance(exec_rag, str) else "—"
                    )
                    rows.append({
                        "initiative": init.get("title", "?"),
                        "owner": (
                            owner_val
                            if isinstance(owner_val, str) and owner_val.strip()
                            else "—"
                        ),
                        "status": init.get("status", ""),
                        "exec health": exec_icon,
                        "delivery %": init.get("progress_pct", 0),
                        "predicted impact": lk.get("predicted_kr_impact"),
                        "actual impact": lk.get("actual_kr_impact"),
                    })
                st.dataframe(
                    pd.DataFrame(rows),
                    use_container_width=True,
                    hide_index=True,
                )
                st.caption(
                    "_Attribution of actual impact happens on **Initiative "
                    "Updates** — not here._"
                )


# -----------------------------------------------------------------------------
# Render: Quarterly KRs section — grouped by parent Quarterly Objective
# -----------------------------------------------------------------------------
obj_title_by_id = (
    objectives.set_index("id")["title"].to_dict() if not objectives.empty else {}
)

st.divider()
st.subheader(
    f"Quarterly Key Results — {selected_period} "
    f"({len(quarterly_krs)})"
)
st.caption("Updated weekly. Grouped by parent quarterly objective.")

if quarterly_krs.empty:
    st.info(
        f"No quarterly KRs match in **{selected_ou_name}** for {selected_period} "
        f"(owner filter: {selected_owner})."
    )
else:
    # Group quarterly KRs by their parent objective
    quarterly_krs_by_obj: dict = {}
    for _, kr in quarterly_krs.iterrows():
        obj_id = kr.get("objective_id")
        quarterly_krs_by_obj.setdefault(obj_id, []).append(kr)

    # Order objectives by title for predictability
    ordered_obj_ids = sorted(
        quarterly_krs_by_obj.keys(),
        key=lambda oid: safe_str(obj_title_by_id.get(oid)).lower(),
    )

    for obj_id in ordered_obj_ids:
        obj_title = obj_title_by_id.get(obj_id, "?")
        krs_for_obj = sorted(
            quarterly_krs_by_obj[obj_id],
            key=lambda k: safe_str(k.get("title")).lower(),
        )
        st.markdown(f"##### 🎯 {obj_title}")
        for kr in krs_for_obj:
            render_kr_box(kr)
        st.write("")  # small gap between objectives


# -----------------------------------------------------------------------------
# Render: Yearly Aspirational KRs section (flat — usually fewer)
# -----------------------------------------------------------------------------
st.divider()
st.subheader(
    f"Yearly Aspirational Key Results — FY{selected_year} "
    f"({len(yearly_krs)})"
)
st.caption(
    "Updated quarterly during reviews, not weekly. The long-arc outcomes "
    "that quarterly bets ladder up to."
)

if yearly_krs.empty:
    st.info(
        f"No yearly KRs match in **{selected_ou_name}** for FY{selected_year} "
        f"(owner filter: {selected_owner})."
    )
else:
    for _, kr in yearly_krs.sort_values("title").iterrows():
        render_kr_box(kr)


# -----------------------------------------------------------------------------
# Save / Discard bar
# -----------------------------------------------------------------------------
st.divider()
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
                    if edit.get("value_changed"):
                        sb.table("key_result").update(
                            {"current_value": edit["value"]}
                        ).eq("id", kr_id).execute()
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
                            errors.append(
                                f"History for KR {kr_id} not saved: {ce}"
                            )
                    success_count += 1
                except Exception as e:
                    errors.append(f"KR {kr_id}: {e}")
            # Clear the pending dict AND explicitly clear each note widget's
            # session state. This matters for notes specifically: the note
            # widget uses a `key=`, so once typed, its value persists in
            # session_state until we delete the key. Without this, on rerun
            # the widget re-reads the old note, `note_changed` is True again,
            # and pending re-populates — leaving the "pending change" banner
            # showing even though the save succeeded.
            for _kr_id in list(pending.keys()):
                _note_widget_key = f"note_{_kr_id}_{scope_key}"
                if _note_widget_key in st.session_state:
                    del st.session_state[_note_widget_key]
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
            # Same pattern as Save: clear the note widget keys as well as
            # the pending dict, otherwise discarding leaves the typed notes
            # visible in their widgets even though pending is cleared.
            for _kr_id in list(st.session_state.get(pending_state_key, {}).keys()):
                _note_widget_key = f"note_{_kr_id}_{scope_key}"
                if _note_widget_key in st.session_state:
                    del st.session_state[_note_widget_key]
            st.session_state[pending_state_key] = {}
            st.rerun()


# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.divider()
st.caption(
    "Key Result Updates is about *current state* and context. To restructure "
    "KRs — rename, retarget, re-parent, change owner — head over to "
    "**Plan a Quarter** or **Annual Strategy & Objectives**."
)

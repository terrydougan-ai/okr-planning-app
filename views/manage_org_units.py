"""
Manage Org Units — CRUD for the structural hierarchy.

The simplest CRUD page in the app; establishes the patterns reused by every
later Manage page:
  * Create form at the top
  * List of existing items below, each editable via expander
  * Soft-delete only (no hard delete from the UI — drop into Supabase if needed)
  * Cache cleared after every write so changes show up immediately

Org units don't have a `status` column today, so "soft delete" here is a
deferred concern — we'll add an archive column when we need it. For now, no
delete from the UI at all.
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client


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
def load_org_units() -> pd.DataFrame:
    return pd.DataFrame(sb.table("org_unit").select("*").execute().data)


def clear_cache():
    """Call after any write so the next read pulls fresh data."""
    load_org_units.clear()


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
LEVELS = ["company", "segment", "team"]


def build_tree_options(org_units: pd.DataFrame, exclude_id: str | None = None):
    """
    Return [(id, indented_label), ...] for use in parent-pickers.
    `exclude_id` lets us hide a unit from its own descendants list when editing
    (you can't be your own parent, or your child's parent).
    """
    if org_units.empty:
        return []

    by_parent: dict = {}
    for _, row in org_units.iterrows():
        by_parent.setdefault(row["parent_unit_id"], []).append(row)

    excluded_ids: set = set()
    if exclude_id:
        # Walk descendants of exclude_id and add them to the excluded set.
        stack = [exclude_id]
        while stack:
            cur = stack.pop()
            excluded_ids.add(cur)
            for child in by_parent.get(cur, []):
                stack.append(child["id"])

    out: list[tuple[str, str]] = []

    def walk(parent_id, depth: int):
        children = by_parent.get(parent_id, [])
        level_order = {"company": 0, "segment": 1, "team": 2}
        children.sort(key=lambda r: (level_order.get(r["level"], 99), r["name"]))
        for row in children:
            if row["id"] in excluded_ids:
                continue
            prefix = "↳ " * depth
            out.append((row["id"], f"{prefix}{row['name']} ({row['level']})"))
            walk(row["id"], depth + 1)

    walk(None, 0)
    return out


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("🏛️ Manage Org Units")
st.caption(
    "Create and edit the structural hierarchy: company → segment(s) → team(s). "
    "Deeper nesting works too — there's no level cap."
)

try:
    org_units = load_org_units()
except Exception as e:
    st.error(f"Couldn't reach Supabase: {e}")
    st.stop()


# --- Create form ---------------------------------------------------------------
st.subheader("Add a new org unit")

# Parent options for the create form (no exclusion needed — nothing exists yet)
parent_options = [("__NONE__", "— No parent (top level) —")] + build_tree_options(
    org_units
)
parent_labels = [label for _, label in parent_options]

with st.form("create_org_unit", clear_on_submit=True):
    col1, col2, col3 = st.columns([3, 2, 4])
    with col1:
        new_name = st.text_input("Name", placeholder="e.g. EMEA Growth Squad")
    with col2:
        new_level = st.selectbox("Level", options=LEVELS, index=0)
    with col3:
        new_parent_label = st.selectbox("Parent", options=parent_labels, index=0)

    submitted = st.form_submit_button("➕ Add org unit", type="primary")

    if submitted:
        if not new_name.strip():
            st.error("Name is required.")
        else:
            parent_id = next(
                (oid for oid, label in parent_options if label == new_parent_label),
                None,
            )
            if parent_id == "__NONE__":
                parent_id = None

            try:
                sb.table("org_unit").insert(
                    {
                        "name": new_name.strip(),
                        "level": new_level,
                        "parent_unit_id": parent_id,
                    }
                ).execute()
                clear_cache()
                st.success(f"Added **{new_name}** as {new_level}.")
                st.rerun()
            except Exception as e:
                st.error(f"Insert failed: {e}")


st.divider()


# --- Edit existing -----------------------------------------------------------
st.subheader("Existing org units")

if org_units.empty:
    st.info("No org units yet — add one above.")
    st.stop()

# Render in tree order so it's easy to scan
tree = build_tree_options(org_units)
id_to_row = org_units.set_index("id").to_dict("index")

for unit_id, label in tree:
    row = id_to_row[unit_id]

    with st.expander(label, expanded=False):
        with st.form(f"edit_{unit_id}"):
            ec1, ec2, ec3 = st.columns([3, 2, 4])
            with ec1:
                edit_name = st.text_input("Name", value=row["name"])
            with ec2:
                edit_level = st.selectbox(
                    "Level",
                    options=LEVELS,
                    index=LEVELS.index(row["level"]) if row["level"] in LEVELS else 0,
                )
            with ec3:
                # Parent picker — exclude self and descendants
                edit_parent_options = [
                    ("__NONE__", "— No parent (top level) —")
                ] + build_tree_options(org_units, exclude_id=unit_id)
                edit_parent_labels = [lbl for _, lbl in edit_parent_options]

                current_parent_id = row.get("parent_unit_id")
                # Find current label, default to "no parent"
                default_idx = 0
                for i, (oid, _) in enumerate(edit_parent_options):
                    if oid == current_parent_id:
                        default_idx = i
                        break

                edit_parent_label = st.selectbox(
                    "Parent",
                    options=edit_parent_labels,
                    index=default_idx,
                )

            save = st.form_submit_button("💾 Save changes", type="primary")

            if save:
                if not edit_name.strip():
                    st.error("Name is required.")
                else:
                    new_parent_id = next(
                        (
                            oid
                            for oid, lbl in edit_parent_options
                            if lbl == edit_parent_label
                        ),
                        None,
                    )
                    if new_parent_id == "__NONE__":
                        new_parent_id = None

                    try:
                        sb.table("org_unit").update(
                            {
                                "name": edit_name.strip(),
                                "level": edit_level,
                                "parent_unit_id": new_parent_id,
                            }
                        ).eq("id", unit_id).execute()
                        clear_cache()
                        st.success("Saved.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Update failed: {e}")

        st.caption(f"ID: `{unit_id}`")


# --- Footnote ---------------------------------------------------------------
st.divider()
st.caption(
    "🗑️ **No delete button by design.** Org units anchor everything else — "
    "strategies, objectives, KRs all reference them. If you really need to "
    "delete, do it in the Supabase SQL editor where you can see what cascades."
)

"""
_ui_helpers — small shared UI utilities used across pages.

Kept intentionally light. This module is for display-side formatting only —
things that make numbers readable, dates friendly, etc. Anything with
domain logic (grade colors, health rollups, RAG mapping) stays in the page
where it belongs.
"""

import pandas as pd


def format_number(value) -> str:
    """Format a numeric value for READ display in KR views.

    Rules:
      * None / NaN → empty string
      * Absolute value >= 1,000 → comma-separated ("18,000,000")
      * Otherwise → readable float or int, no commas

    Preserves decimal precision when the value is a non-integer float
    (0.9 stays "0.9", not "1"). Integer values >= 1000 render with commas
    but no trailing ".0".

    Used across Objectives & KRs, Hotspots, Annual Strategy, Plan a Quarter,
    and Plan Narrative — anywhere KR values are shown to a reader. Do NOT
    use in input fields; those need raw numeric values.
    """
    # None / NaN handling — pandas gives NaN for missing numerics
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        # pd.isna raises on some non-numeric types; let those fall through
        pass

    # Try to coerce to a number
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)

    # Integer-valued numbers render without decimals
    if num == int(num):
        int_val = int(num)
        if abs(int_val) >= 1000:
            return f"{int_val:,}"
        return str(int_val)

    # Non-integer floats: preserve reasonable precision
    if abs(num) >= 1000:
        return f"{num:,.2f}"
    # Small floats: strip trailing zeros for readability (0.9, not 0.90)
    formatted = f"{num:.4f}".rstrip("0").rstrip(".")
    return formatted if formatted else "0"

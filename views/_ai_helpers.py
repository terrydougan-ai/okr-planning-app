"""
_ai_helpers — small module for Anthropic API calls used across the app.

Design principles:
  * Graceful degradation: if ANTHROPIC_API_KEY is absent, is_ai_enabled() returns
    False and the caller silently skips AI features. No crashes, no error
    messages to hiring managers.
  * Structured output: JSON-only prompts with strict parsing. If the model
    returns malformed JSON, the caller shows a friendly retry message.
  * Model per feature: Haiku for quick structured writing (KR suggestions),
    Sonnet for reasoning over data (Hotspots summary, future feature).
  * No dependencies on other view files: this module is standalone so it
    can be imported anywhere.

Leading underscore in filename signals "internal helper, not a page."
Streamlit's navigation only loads pages that are registered in Overview.py,
so this file won't show up as a nav entry.
"""

import json
from typing import Optional

import streamlit as st


# Model IDs — verified current as of build time
MODEL_HAIKU = "claude-haiku-4-5-20251001"
MODEL_SONNET = "claude-sonnet-4-6"


# -----------------------------------------------------------------------------
# Client setup
# -----------------------------------------------------------------------------
@st.cache_resource
def _get_client():
    """Return the Anthropic client, or None if no API key is configured."""
    try:
        from anthropic import Anthropic
        api_key = st.secrets.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        return Anthropic(api_key=api_key)
    except Exception:
        # If anthropic isn't installed (during local dev without the package)
        # or any other setup issue, return None. The caller checks
        # is_ai_enabled() before using this.
        return None


def is_ai_enabled() -> bool:
    """True iff we can make Anthropic API calls. Callers use this to decide
    whether to show AI-powered UI elements at all."""
    return _get_client() is not None


# -----------------------------------------------------------------------------
# KR suggestion
# -----------------------------------------------------------------------------
def suggest_krs(
    objective_title: str,
    objective_description: Optional[str],
    team_name: Optional[str],
    existing_krs: list[dict],
) -> Optional[list[dict]]:
    """Ask Claude Haiku to suggest 2-3 KRs for the given objective.

    Returns a list of dicts with keys:
      title           — KR title (specific, measurable)
      metric_unit     — one of the app's common units
      start_value     — plausible starting value
      target_value    — plausible ambitious target
      indicator_type  — 'lagging' | 'leading' | ''
      rationale       — one-sentence why this KR matters

    Returns None on API failure so the caller can show a friendly error.
    """
    client = _get_client()
    if client is None:
        return None

    # Compact context for the prompt. Existing KRs are important — the model
    # should suggest KRs that complement rather than duplicate what's already
    # defined on this objective.
    existing_summary = (
        "\n".join(
            f"  - {kr.get('title', '?')} "
            f"({kr.get('metric_unit', '')}, "
            f"{kr.get('indicator_type') or 'no tag'})"
            for kr in existing_krs
        )
        if existing_krs
        else "  (none yet)"
    )

    prompt = f"""You are helping a leader draft Key Results (KRs) for a quarterly OKR planning session.

CONTEXT
Team: {team_name or 'unspecified'}
Objective: {objective_title}
Objective description: {objective_description or '(none provided)'}

Existing KRs on this objective:
{existing_summary}

TASK
Suggest 2 or 3 additional KRs that would help measure progress toward this objective. Aim for a mix — usually one lagging outcome KR and one or two leading indicators.

GUIDELINES
- Each KR must be measurable — a specific metric that can be tracked with numbers.
- Prefer specific, concrete metrics over vague ones. "Weekly active users" beats "user engagement."
- Set an ambitious but plausible target (typically 20-50% improvement from start).
- Choose one metric_unit from: %, count, USD, min, hours, days, score, NPS, ms.
- Tag indicator_type as 'lagging' if it measures the outcome you ultimately care about, 'leading' if it's an early signal that predicts the lagging outcome, or leave empty string if standalone.
- Avoid duplicating any existing KR.

OUTPUT
Return ONLY a JSON array. No prose, no markdown, no code fences. Just JSON.

Each element must have exactly these keys:
  "title": string (the KR title)
  "metric_unit": string (one of the units above)
  "start_value": number (plausible current baseline)
  "target_value": number (ambitious target)
  "indicator_type": string ("lagging" | "leading" | "")
  "rationale": string (one sentence, under 20 words)

Example format:
[
  {{"title": "Activation rate", "metric_unit": "%", "start_value": 30, "target_value": 55, "indicator_type": "lagging", "rationale": "The core outcome — activated users predict retention."}}
]

Now generate 2-3 KRs for the objective above."""

    try:
        response = client.messages.create(
            model=MODEL_HAIKU,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        # response.content is a list of content blocks; grab the text
        raw_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw_text += block.text

        # Some models occasionally wrap JSON in ```json fences even when told
        # not to. Strip defensively.
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            # Drop the first line (```json or similar) and last line (```)
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned

        parsed = json.loads(cleaned)
        if not isinstance(parsed, list):
            return None

        # Basic shape validation — drop any suggestion that's missing fields
        valid_suggestions = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            if "title" not in item or "metric_unit" not in item:
                continue
            valid_suggestions.append({
                "title": str(item.get("title", "")).strip(),
                "metric_unit": str(item.get("metric_unit", "")).strip(),
                "start_value": float(item.get("start_value", 0) or 0),
                "target_value": float(item.get("target_value", 100) or 100),
                "indicator_type": str(item.get("indicator_type", "") or "").strip().lower(),
                "rationale": str(item.get("rationale", "")).strip(),
            })
        return valid_suggestions if valid_suggestions else None

    except Exception as e:
        # Log to Streamlit console for debugging but don't crash the page.
        # The caller will show a friendly message to the user.
        print(f"[AI] suggest_krs failed: {e}")
        return None

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


# -----------------------------------------------------------------------------
# Hotspots summary
# -----------------------------------------------------------------------------
def summarize_hotspots(brief: dict) -> Optional[str]:
    """Generate an executive summary of the Hotspots view using Sonnet.

    Takes a pre-computed structured brief (built by the caller from the
    Hotspots roll-up math and problem buckets) and returns a 3-5 sentence
    prose summary suitable for the top of the Hotspots page.

    The brief should be a dict shaped like:
      {
        "scope_label": "Acme Analytics · Q3-2026",
        "totals": {"kr_red": 2, "kr_yellow": 3, "kr_green": 6,
                   "init_blocked_or_off": 1, "init_at_risk": 2,
                   "init_on_track": 5},
        "teams": [
          {
            "name": "Go-to-Market",
            "rollup_color": "🔴",
            "red_krs": [{"title": "...", "grade": 0.25, "unit": "%"}],
            "blocked_or_offtrack": [{"title": "ProductA Launch",
                                      "milestone_status": "off_track",
                                      "exec_rag": "blocked"}],
            "at_risk": [...],
            "past_milestone": [...],
          },
          ...
        ]
      }

    Returns a string (the summary) or None on API failure.
    """
    client = _get_client()
    if client is None:
        return None

    # Format the brief as compact structured text. Claude reasons well over
    # structured text; feeding raw JSON often produces stiffer prose.
    lines = []
    lines.append(f"SCOPE: {brief.get('scope_label', 'unspecified')}")
    totals = brief.get("totals", {})
    lines.append(
        f"TOTALS: {totals.get('kr_red', 0)} red KRs, "
        f"{totals.get('kr_yellow', 0)} yellow, "
        f"{totals.get('kr_green', 0)} green. "
        f"{totals.get('init_blocked_or_off', 0)} blocked/off-track initiatives, "
        f"{totals.get('init_at_risk', 0)} at-risk, "
        f"{totals.get('init_on_track', 0)} on track."
    )
    lines.append("")
    lines.append("PER-TEAM DETAIL:")
    for team in brief.get("teams", []):
        lines.append(f"\n{team['rollup_color']} {team['name']}")
        for r in team.get("red_krs", [])[:3]:
            lines.append(
                f"  Red KR — {r['title']}: "
                f"{int(r.get('grade', 0) * 100)}% to target"
            )
        for i in team.get("blocked_or_offtrack", [])[:3]:
            _team_view = i.get("milestone_status") or "no team signal"
            _exec_view = i.get("exec_rag") or "no exec signal"
            _divergence = ""
            if (
                i.get("milestone_status")
                and i.get("exec_rag")
                and i["milestone_status"] != i["exec_rag"]
            ):
                _divergence = f" (team: {_team_view}, exec: {_exec_view})"
            lines.append(
                f"  Blocked/off-track initiative — {i['title']}{_divergence}"
            )
        for i in team.get("at_risk", [])[:2]:
            lines.append(f"  At-risk initiative — {i['title']}")
        for m in team.get("past_milestone", [])[:2]:
            lines.append(
                f"  Past-milestone initiative — {m['title']} "
                f"(milestone due {m.get('due_date', '?')})"
            )

    brief_text = "\n".join(lines)

    prompt = f"""You are a chief of staff writing a brief exec update on OKR execution.

Below is a compact brief of the current state. Read it and write a 3-5 sentence executive summary that a busy VP could scan in 20 seconds. Prioritize: what needs attention, what's escalating, what's healthy.

BRIEF:
{brief_text}

WRITING GUIDELINES:
- Open with the most important thing — a specific concern by name, or if all healthy, say so directly.
- Reference initiatives and KRs by their actual names. Don't say "one team" when you can say "Go-to-Market."
- If team-view and exec-view RAG diverge on an initiative, that divergence is itself worth flagging.
- Do not restate the brief; interpret it.
- Do not use bullet points or headers. Prose only.
- Do not begin with "This summary" or "In summary" or any other meta-opener.
- Keep it under 120 words.
- If nothing needs attention, say so plainly — "No urgent issues in this scope; healthy execution overall" style. Do NOT invent problems.

Write the summary now."""

    try:
        response = client.messages.create(
            model=MODEL_SONNET,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text
        return text.strip() or None
    except Exception as e:
        print(f"[AI] summarize_hotspots failed: {e}")
        return None


# -----------------------------------------------------------------------------
# Initiative check-in review
# -----------------------------------------------------------------------------
def review_initiative_update(update: dict) -> Optional[dict]:
    """Review a PM's initiative check-in for quality.

    Reads the whole update as a package — the AI's job is to spot
    inconsistencies BETWEEN fields (e.g. exec_rag says "on track" but the
    narrative flags customer risk) as much as issues WITHIN any single
    field. Returns structured feedback under four categories:
      * Clarity — is the narrative specific and readable?
      * Consistency — do the status, RAG, %, and narrative agree with each other?
      * Completeness — did the PM address the things a leader would ask about?
      * Realism — do the numbers and dates hold up?

    `update` should be a dict with at least these keys (missing keys OK):
      title, description, status, milestone_status, exec_rag,
      progress_pct, next_milestone_text, next_milestone_date,
      exec_narrative, linked_krs (list of {title, unit, current, target}),
      effort_estimate.

    Returns a dict:
      {
        "categories": [
          {"name": "Consistency", "observations": ["...", "..."]},
          ...
        ],
        "overall": "one-line summary of the update's health"
      }
    Or None on API failure.
    """
    client = _get_client()
    if client is None:
        return None

    # Format the update as compact structured text
    linked_krs_txt = ""
    for kr in update.get("linked_krs", []) or []:
        _cur = kr.get("current")
        _tgt = kr.get("target")
        linked_krs_txt += (
            f"\n  - {kr.get('title', '?')}: current {_cur}, target {_tgt} "
            f"{kr.get('unit', '')}"
        )
    if not linked_krs_txt:
        linked_krs_txt = "\n  (none linked)"

    prompt = f"""You are an experienced chief of staff reviewing a project manager's initiative check-in. Your job: give the PM concrete, constructive feedback on the quality of their update. Not a rewrite — feedback they can act on.

Read the update below as a package. Check for:
- CLARITY: Is the narrative specific enough that a busy VP would understand the situation? Or is it vague ("making progress", "some blockers")?
- CONSISTENCY: Do the fields agree? For example: if delivery is at 40% and status is "on track", does the narrative explain that pace? If exec_rag is worse than milestone_status, does the narrative explain the divergence? If the milestone date has passed, was the status updated?
- COMPLETENESS: For a struggling initiative (not on-track), did the PM explain why AND describe a mitigation plan? For a healthy initiative, did they still note what could put it at risk? Are the questions a VP would ask actually addressed?
- REALISM: Do the numbers hold up? Is 100% delivery plausible given the status? Is a 5-day-away milestone realistic given progress? Is the KR impact claim (via progress) even remotely on the trajectory needed to hit target?

INITIATIVE CONTEXT:
Title: {update.get('title', '?')}
Description: {update.get('description', '(none)')}
Effort estimate: {update.get('effort_estimate', 'unspecified')}
Linked KRs:{linked_krs_txt}

CURRENT CHECK-IN VALUES:
Status: {update.get('status', 'unspecified')}
Milestone status (team view): {update.get('milestone_status', 'not set')}
Exec RAG (exec-facing view): {update.get('exec_rag', 'not set')}
Delivery progress: {update.get('progress_pct', 0)}%
Next milestone text: {update.get('next_milestone_text', '(not set)')}
Next milestone date: {update.get('next_milestone_date', '(not set)')}
Exec narrative: {update.get('exec_narrative', '(empty)')}

Return ONLY a JSON object. No prose, no markdown, no code fences.

Structure:
{{
  "categories": [
    {{"name": "Clarity", "observations": ["..."]}},
    {{"name": "Consistency", "observations": ["..."]}},
    {{"name": "Completeness", "observations": ["..."]}},
    {{"name": "Realism", "observations": ["..."]}}
  ],
  "overall": "one sentence, under 20 words"
}}

RULES:
- Each observation must be actionable — the PM should know what to do next.
- If a category has no issues, use an empty observations array — do NOT invent problems.
- Do NOT congratulate. Do NOT open with "Great job" or "This is well-written."
- Reference the actual field values by name where relevant.
- Keep each observation under 30 words.
- Overall should be neutral if no major issues, direct if there are.

Now write the review."""

    try:
        response = client.messages.create(
            model=MODEL_SONNET,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw_text += block.text

        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned

        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            return None

        # Validate shape
        categories = parsed.get("categories", [])
        if not isinstance(categories, list):
            categories = []
        valid_categories = []
        for cat in categories:
            if not isinstance(cat, dict):
                continue
            name = str(cat.get("name", "")).strip()
            obs = cat.get("observations", [])
            if not isinstance(obs, list):
                obs = []
            obs = [str(o).strip() for o in obs if str(o).strip()]
            if name:
                valid_categories.append({"name": name, "observations": obs})

        overall = str(parsed.get("overall", "")).strip()
        return {
            "categories": valid_categories,
            "overall": overall,
        }

    except Exception as e:
        print(f"[AI] review_initiative_update failed: {e}")
        return None


# -----------------------------------------------------------------------------
# KR check-in review
# -----------------------------------------------------------------------------
def review_kr_checkin(checkin: dict) -> Optional[dict]:
    """Review a KR check-in (value + optional note) for quality.

    Simpler than the initiative review — a KR check-in only has two fields
    of substance: the new value, and the note. So the evaluation focuses on:
      * Clarity — does the note actually say what happened?
      * Signal — does the note read the trend, or just report a number?

    `checkin` should be a dict:
      kr_title, unit, previous_value, new_value, target, start,
      recent_history (list of prior check-in values with optional notes),
      note (the new note being written)

    Returns:
      {
        "categories": [{"name": ..., "observations": [...]}, ...],
        "overall": "one sentence"
      }
    Or None on API failure.
    """
    client = _get_client()
    if client is None:
        return None

    history_txt = ""
    for h in checkin.get("recent_history", []) or []:
        _v = h.get("value")
        _n = h.get("note") or "(no note)"
        _t = h.get("when", "")
        history_txt += f"\n  {_t}: {_v} — {_n}"
    if not history_txt:
        history_txt = "\n  (no prior check-ins)"

    prev_v = checkin.get("previous_value")
    new_v = checkin.get("new_value")
    delta_str = ""
    try:
        if prev_v is not None and new_v is not None:
            delta = float(new_v) - float(prev_v)
            delta_str = f"Change from previous: {delta:+g}"
    except (TypeError, ValueError):
        pass

    prompt = f"""You are an experienced chief of staff reviewing a Key Result check-in written by a team lead. Give concrete, constructive feedback on the quality of the check-in note.

Check for:
- CLARITY: Does the note actually say what happened? Or is it filler like "Good week" / "Making progress"? A useful KR note names what moved the number (or didn't).
- SIGNAL: Does the note read the trend, or just report a number? If the KR jumped or dipped materially, does the note explain the driver? If the KR is flat, does the note acknowledge it?

KR CONTEXT:
Title: {checkin.get('kr_title', '?')}
Unit: {checkin.get('unit', '')}
Start value: {checkin.get('start')}
Target value: {checkin.get('target')}
Previous value: {prev_v}
NEW value being logged: {new_v}
{delta_str}

Recent check-in history (oldest first):{history_txt}

NEW NOTE BEING WRITTEN:
"{checkin.get('note', '') or '(empty note)'}"

Return ONLY a JSON object.

Structure:
{{
  "categories": [
    {{"name": "Clarity", "observations": ["..."]}},
    {{"name": "Signal", "observations": ["..."]}}
  ],
  "overall": "one sentence, under 20 words"
}}

RULES:
- Each observation actionable — the team lead should know what to add or change.
- Empty observations arrays for categories with no issues — do NOT invent problems.
- If the note is empty, say so directly under Clarity.
- Do NOT open with praise.
- Reference the actual values where useful (e.g. "the +12 jump from last week isn't explained").
- Keep each observation under 30 words.

Now write the review."""

    try:
        response = client.messages.create(
            model=MODEL_SONNET,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw_text += block.text

        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned

        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            return None

        categories = parsed.get("categories", [])
        if not isinstance(categories, list):
            categories = []
        valid_categories = []
        for cat in categories:
            if not isinstance(cat, dict):
                continue
            name = str(cat.get("name", "")).strip()
            obs = cat.get("observations", [])
            if not isinstance(obs, list):
                obs = []
            obs = [str(o).strip() for o in obs if str(o).strip()]
            if name:
                valid_categories.append({"name": name, "observations": obs})

        overall = str(parsed.get("overall", "")).strip()
        return {
            "categories": valid_categories,
            "overall": overall,
        }

    except Exception as e:
        print(f"[AI] review_kr_checkin failed: {e}")
        return None


# -----------------------------------------------------------------------------
# Shared rendering — used by both initiative check-in review and KR check-in
# review so the visual treatment is consistent across pages.
# -----------------------------------------------------------------------------
def render_review(review: dict) -> None:
    """Render a review result inline. Small, understated — the review is
    supplementary to the PM's own work, not a takeover of the page.
    Call within a Streamlit container/expander for best framing."""
    if not review:
        return

    # Overall line (one-liner) up top
    overall = review.get("overall", "").strip()
    if overall:
        st.markdown(
            f"<div style='color:#1F2937;font-size:0.95em;margin-bottom:12px'>"
            f"<b>Overall:</b> {overall}</div>",
            unsafe_allow_html=True,
        )

    # Categories with observations. Categories with EMPTY observations still
    # render — they signal "this dimension looked fine" without inventing filler.
    for cat in review.get("categories", []):
        name = cat.get("name", "").strip()
        obs = cat.get("observations", [])
        if not name:
            continue
        if not obs:
            st.markdown(
                f"<div style='color:#374151;font-size:0.9em;margin-top:8px'>"
                f"<b>{name}:</b> "
                f"<span style='color:#6B7280'>looks fine</span></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div style='color:#374151;font-size:0.9em;margin-top:8px'>"
                f"<b>{name}</b></div>",
                unsafe_allow_html=True,
            )
            for o in obs:
                st.markdown(
                    f"<div style='color:#4B5563;font-size:0.9em;"
                    f"margin-left:12px'>• {o}</div>",
                    unsafe_allow_html=True,
                )

    st.caption(
        "_Feedback from Claude Sonnet. Not a substitute for peer review or "
        "manager feedback — for real judgment on strategy, still talk to your leader._"
    )

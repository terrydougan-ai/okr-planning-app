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

    # Cross-functional patterns — added as a separate section. If present in
    # the brief, they surface how work flows across team boundaries. This is
    # the "connective tissue" a TPM cares about.
    cross_section = ""
    _cross_patterns = brief.get("cross_functional_patterns", [])
    if _cross_patterns:
        cross_lines = ["", "CROSS-FUNCTIONAL PATTERNS:"]
        cross_lines.append(
            f"({len(_cross_patterns)} initiatives are owned by one team but "
            f"moving another team's KRs.)"
        )
        for _cp in _cross_patterns[:8]:  # cap for prompt length
            _health = ""
            if _cp.get("initiative_ms") and _cp.get("initiative_rag"):
                if _cp["initiative_ms"] != _cp["initiative_rag"]:
                    _health = (
                        f" (team: {_cp['initiative_ms']}, exec: {_cp['initiative_rag']})"
                    )
                else:
                    _health = f" ({_cp['initiative_ms']})"
            cross_lines.append(
                f"  - {_cp['contributing_team']}'s {_cp['initiative_title']}"
                f" → {_cp['receiving_team']}'s {_cp['kr_title']}{_health}"
            )
        cross_section = "\n" + "\n".join(cross_lines)

    prompt = f"""You are a chief of staff writing a brief exec update on OKR execution.

Below is a compact brief of the current state. Read it and write a 3-5 sentence executive summary that a busy VP could scan in 20 seconds. Prioritize: what needs attention, what's escalating, what's healthy.

BRIEF:
{brief_text}{cross_section}

WRITING GUIDELINES:
- Open with the most important thing — a specific concern by name, or if all healthy, say so directly.
- Reference initiatives and KRs by their actual names. Don't say "one team" when you can say "Go-to-Market."
- If team-view and exec-view RAG diverge on an initiative, that divergence is itself worth flagging.
- If a cross-functional pattern is present AND the contributing initiative is at-risk or blocked, mention it. Example: "Platform's caching work is off-track — worth flagging because it's moving Product's activation KR." This kind of dependency is the connective-tissue TPM work.
- If cross-functional patterns are healthy (or absent), don't force mention.
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
  "verdict": "ready_to_send" | "needs_sharpening" | "rework_recommended",
  "categories": [
    {{"name": "Clarity", "observations": ["..."]}},
    {{"name": "Consistency", "observations": ["..."]}},
    {{"name": "Completeness", "observations": ["..."]}},
    {{"name": "Realism", "observations": ["..."]}}
  ],
  "overall": "one sentence, under 20 words"
}}

VERDICT RUBRIC (apply strictly):
- "ready_to_send" — no observations across categories, OR only one minor wording nudge. The update reads cleanly to a busy VP.
- "needs_sharpening" — 2–3 observations, none of them fundamental. Update is usable but would be stronger with a pass.
- "rework_recommended" — 4+ observations, OR a fundamental inconsistency (status conflicts with narrative), OR the exec narrative is empty on a struggling initiative, OR the update misses information a VP will immediately ask about.

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
        verdict = str(parsed.get("verdict", "")).strip().lower()
        # Normalize to one of the three known values; empty string means
        # AI omitted it (renderer handles that gracefully).
        if verdict not in ("ready_to_send", "needs_sharpening", "rework_recommended"):
            verdict = ""
        return {
            "verdict": verdict,
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
  "verdict": "ready_to_send" | "needs_sharpening" | "rework_recommended",
  "categories": [
    {{"name": "Clarity", "observations": ["..."]}},
    {{"name": "Signal", "observations": ["..."]}}
  ],
  "overall": "one sentence, under 20 words"
}}

VERDICT RUBRIC (apply strictly):
- "ready_to_send" — the note names what happened and reads the trend; no observations, or only one minor wording nudge.
- "needs_sharpening" — 1–2 observations. The note is usable but a small clarification would help a reader.
- "rework_recommended" — the note is empty or generic ("Good week"), OR a material value change is unexplained, OR the update misses signal a leader would want.

RULES:
- Each observation actionable — the team lead should know what to add or change.
- Empty observations arrays for categories with no issues — do NOT invent problems.
- If the note is empty, say so directly under Clarity and set verdict to "rework_recommended".
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
        verdict = str(parsed.get("verdict", "")).strip().lower()
        if verdict not in ("ready_to_send", "needs_sharpening", "rework_recommended"):
            verdict = ""
        return {
            "verdict": verdict,
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

    # Verdict badge at the very top — a single actionable label so the PM
    # knows at a glance whether to ship, sharpen, or rework the update.
    # Colors and icons stay OFF the traditional RAG palette (green/yellow/red)
    # so the verdict doesn't get confused with the app's initiative/KR RAG.
    verdict = review.get("verdict", "")
    verdict_labels = {
        "ready_to_send":       ("✅", "Ready to send", "#065F46", "#D1FAE5"),
        "needs_sharpening":    ("✏️", "Needs sharpening", "#92400E", "#FEF3C7"),
        "rework_recommended":  ("🔁", "Rework recommended", "#7C2D12", "#FED7AA"),
    }
    if verdict in verdict_labels:
        icon, label, fg, bg = verdict_labels[verdict]
        st.markdown(
            f"<div style='display:inline-block;padding:6px 12px;"
            f"background:{bg};color:{fg};border-radius:6px;"
            f"font-weight:600;font-size:0.95em;margin-bottom:10px'>"
            f"{icon} {label}</div>",
            unsafe_allow_html=True,
        )

    # Overall line (one-liner) below the verdict
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


# -----------------------------------------------------------------------------
# Signature — used for staleness detection
# -----------------------------------------------------------------------------
import hashlib


def _signature_for(payload: dict) -> str:
    """Deterministic hash of the review's input payload. When the payload
    changes (e.g. PM edits the narrative), the signature changes — the UI
    compares this to the stored signature to detect stale reviews."""
    # json.dumps with sort_keys guarantees the same payload → same hash
    # regardless of insertion order. default=str safely handles dates.
    normalized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def compute_initiative_signature(update: dict) -> str:
    """Signature for an initiative update. Only fields the review reasons over
    are included — so unrelated changes (e.g. created_at) don't invalidate."""
    return _signature_for({
        "status": update.get("status"),
        "milestone_status": update.get("milestone_status"),
        "exec_rag": update.get("exec_rag"),
        "progress_pct": update.get("progress_pct"),
        "next_milestone_text": update.get("next_milestone_text"),
        "next_milestone_date": str(update.get("next_milestone_date") or ""),
        "exec_narrative": update.get("exec_narrative"),
    })


def compute_kr_checkin_signature(checkin: dict) -> str:
    """Signature for a KR check-in — the value + note are the material inputs.

    NOTE: currently unused. KR check-in reviews are session-only (not
    persisted to the DB) because a KR check-in note is ephemeral. This
    helper is kept for symmetry with the initiative signature and in case
    a future design (e.g. attaching reviews to check_in rows) needs it.
    """
    return _signature_for({
        "new_value": checkin.get("new_value"),
        "note": checkin.get("note"),
    })


# -----------------------------------------------------------------------------
# AI-native drafting: initiative check-in
# -----------------------------------------------------------------------------
# This function inverts the default authorship: instead of the PM writing
# and the AI reviewing, the AI drafts from available context and the PM
# confirms or edits. This is the "authorship-native" pattern.
#
# When ambient signals (engineering activity, team messages, calendar events)
# are present in the context, the function also moves toward "signal-native":
# the AI reasons over Jira-ish, Slack-ish, and coordination signals rather
# than just what the PM typed into the app. This is the pattern a
# production-integrated version would use with real Jira/Slack/calendar APIs.
#
# Scope note: only drafts exec_narrative and next_milestone_text.
# Milestone status, exec RAG, delivery %, and dates stay human-owned —
# those are situational judgment calls the AI shouldn't anchor.
def draft_initiative_checkin(context: dict) -> Optional[dict]:
    """Ask Claude Sonnet to draft an exec narrative and next-milestone text
    from the initiative's current state, prior check-in context, and
    (when present) ambient signals.

    `context` may include the following keys:
      title, description, effort_estimate,
      status, milestone_status, exec_rag, progress_pct,
      previous_narrative (last saved), previous_milestone_text (last saved),
      next_milestone_date,
      linked_krs (list of {title, unit, current, target}),
      days_since_last_update (approximate, may be None),
      engineering_activity (list of records, most-recent-first),
      team_messages (list of records, most-recent-first),
      calendar_events (list of records, most-recent-first).

    Returns:
      { "exec_narrative": "...", "next_milestone_text": "..." }
    Or None on API failure.
    """
    client = _get_client()
    if client is None:
        return None

    # Format linked KRs for the prompt
    linked_krs_txt = ""
    for kr in context.get("linked_krs", []) or []:
        _cur = kr.get("current")
        _tgt = kr.get("target")
        linked_krs_txt += (
            f"\n  - {kr.get('title', '?')}: current {_cur}, target {_tgt} "
            f"{kr.get('unit', '')}"
        )
    if not linked_krs_txt:
        linked_krs_txt = "\n  (none linked)"

    days_text = ""
    _days = context.get("days_since_last_update")
    if _days is not None:
        days_text = f"\nDays since last check-in: {_days}"

    # Format ambient signals — these enable signal-native drafting.
    # If no signals are present, we say so explicitly and the model relies
    # only on the human-typed fields (assisted mode).
    def _fmt_signal_time(iso_str: str) -> str:
        """Convert ISO datetime to relative days-ago string."""
        try:
            import datetime as _dt
            _when = _dt.datetime.fromisoformat(iso_str.replace("Z", "+00:00")) if isinstance(iso_str, str) else iso_str
            _now = _dt.datetime.now(_when.tzinfo) if _when.tzinfo else _dt.datetime.now()
            _delta = (_now - _when).days
            return f"{max(0, _delta)}d ago"
        except Exception:
            return "recently"

    eng_activity = context.get("engineering_activity", []) or []
    team_msgs = context.get("team_messages", []) or []
    cal_events = context.get("calendar_events", []) or []
    total_signals = len(eng_activity) + len(team_msgs) + len(cal_events)

    signals_txt = ""
    if total_signals == 0:
        signals_txt = (
            "\n(No ambient signals available for this initiative — "
            "reason only from the PM-facing fields above.)"
        )
    else:
        signals_txt = f"\n\nAMBIENT SIGNALS ({total_signals} total)"
        signals_txt += (
            "\nThe following are Jira-ish, Slack-ish, and calendar signals "
            "scoped to this initiative. Reason over them — look for patterns, "
            "silences where you'd expect activity, and mismatches between "
            "what the PM's previous narrative claimed and what the signals "
            "actually show."
        )

        if eng_activity:
            signals_txt += "\n\nEngineering activity (most recent first):"
            for _e in eng_activity[:15]:  # cap to avoid runaway prompts
                _when_str = _fmt_signal_time(_e.get("occurred_at", ""))
                _ref = f"[{_e.get('reference', '?')}] " if _e.get("reference") else ""
                _actor = f" ({_e.get('actor')})" if _e.get("actor") else ""
                signals_txt += f"\n  - {_when_str}: {_ref}{_e.get('description', '')}{_actor}"

        if team_msgs:
            signals_txt += "\n\nTeam messages (most recent first):"
            for _m in team_msgs[:15]:
                _when_str = _fmt_signal_time(_m.get("posted_at", ""))
                _channel = _m.get("channel", "?")
                _author = _m.get("author", "?")
                _sent = f" [sentiment: {_m.get('sentiment')}]" if _m.get("sentiment") else ""
                signals_txt += f"\n  - {_when_str}: {_channel} · {_author}{_sent}: \"{_m.get('body', '')}\""

        if cal_events:
            signals_txt += "\n\nCoordination events (most recent first):"
            for _c in cal_events[:10]:
                _when_str = _fmt_signal_time(_c.get("occurred_at", ""))
                _outcome = f" → {_c.get('outcome')}" if _c.get("outcome") else ""
                signals_txt += f"\n  - {_when_str}: {_c.get('title', '?')}{_outcome}"

    prompt = f"""You are drafting a status check-in for an initiative on behalf of the PM. Your job is to produce a first-draft exec narrative and next-milestone description that the PM will review and edit. This is a working draft, not the final artifact — the PM has situational context you don't.

INITIATIVE CONTEXT
Title: {context.get('title', '?')}
Description: {context.get('description', '(none)')}
Effort estimate: {context.get('effort_estimate', 'unspecified')}
Current status: {context.get('status', 'unspecified')}
Milestone status (team view): {context.get('milestone_status', 'not set')}
Exec RAG (exec-facing view): {context.get('exec_rag', 'not set')}
Delivery progress: {context.get('progress_pct', 0)}%
Next milestone date (planned): {context.get('next_milestone_date', '(not set)')}
Linked KRs:{linked_krs_txt}{days_text}

PREVIOUS EXEC NARRATIVE (last saved):
{context.get('previous_narrative') or '(none — this may be the first check-in)'}

PREVIOUS NEXT-MILESTONE TEXT (last saved):
{context.get('previous_milestone_text') or '(none)'}
{signals_txt}

CRITICAL DIRECTIVE — READ CAREFULLY
The previous exec narrative is HISTORICAL CONTEXT ONLY. It represents what someone wrote at a past point in time. It may be accurate or it may have been aspirational, incomplete, or wrong. Do NOT treat it as a source of truth or a template to preserve continuity with.

The signals below (engineering activity, team messages, coordination events) are what has actually happened since. They are the ground truth for this check-in. Your job is NOT to update the tone of the previous narrative — your job is to write a fresh narrative grounded in what the signals show.

Before writing the draft, silently perform this analysis:
1. What are the 3-4 most important events in the signals? (Look for: unresolved blockers, incidents, rescheduled meetings, PR merges stopping, escalations in team channels, sentiment tags like "escalation" or "concerned".)
2. Does the previous exec narrative acknowledge these events? If not, that gap IS the story — the draft should surface what the previous narrative missed.
3. Does the previous narrative say something the signals contradict? (E.g., "on track" while signals show a blocker, or "team is managing appropriately" while team messages show escalation.) Name the contradiction directly.

Then write the draft.

TASK
Draft ONE text field: the exec_narrative.

exec_narrative — a 3-5 sentence narrative for a VP reader.

WHAT AN EXEC NARRATIVE SHOULD DO
An exec narrative isn't a chronology of what happened. It's a framing for a busy leader who needs to know: how is this initiative doing overall, what's the state, what (if anything) needs their attention or a decision. The reader is a VP, not a project manager. They want the assessment first, the evidence second.

STRUCTURE
- **Opening sentence (the lead)**: a single assessment sentence naming the overall state. Not a status word ("at risk") — a stance sentence. Examples of good opens:
  - "This initiative is at material risk of missing its Q3 target due to unresolved concurrency issues in the caching layer."
  - "Rollout is meaningfully progressing on the lower-risk query paths, but the harder tier of work has stalled and needs a decision."
  - "Bug reduction is on track but one high-severity issue represents the primary tail risk for the September release."
  - "Execution is healthy — the team has hit each milestone on schedule and impact on the KR is materializing."
  Do NOT open with facts like "Nine of twelve bugs are fixed" or "The team has migrated four query types." Facts support the stance; they don't lead it.

- **Middle 2-3 sentences (the evidence)**: the specific evidence supporting the opening assessment. This IS where you cite ticket numbers, incidents, meeting names, KR gaps, specific quotes from team messages when they matter. Be direct about what the signals show, especially if they contradict the previous narrative or the exec_rag field. Do not smooth over problems with soft language like "some minor issues." Name the actual issue.

- **Closing sentence (the ask, if there is one)**: if there's a decision needed, a risk worth flagging, or a specific commitment that would clarify things, name it in one sentence. If the situation is healthy and self-managing, close with what the next confirming event is. Do not close with vague forward-looking language like "the team will continue to monitor."

STYLE
- Direct, specific, honest about risk. The voice of a competent PM writing under time pressure.
- Match a VP's attention: what would they need to know to nod, or to ask a follow-up?
- Do not repeat claims from the previous narrative if the signals don't support them.
- Do not open with "This update covers..." or other meta-language.
- Keep it under 130 words.

Return ONLY a JSON object. No prose, no markdown, no code fences.

Structure:
{{
  "exec_narrative": "..."
}}

Draft now."""

    try:
        response = client.messages.create(
            model=MODEL_SONNET,
            max_tokens=1000,
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

        return {
            "exec_narrative": str(parsed.get("exec_narrative", "")).strip(),
            # Intentionally empty: the AI no longer drafts next_milestone_text.
            # That field holds release-level milestones the human owns.
            "next_milestone_text": "",
        }

    except Exception as e:
        print(f"[AI] draft_initiative_checkin failed: {e}")
        return None

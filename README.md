# AI OKR Execution System

A Streamlit + Supabase app for planning and tracking OKRs across a multi-team org. Built to be honest about the parts of OKR practice that most tools fudge: separating delivery from impact, leading from lagging indicators, exec-facing signal from team-internal status.

> ⚠️ This is a personal portfolio project — it works, but it isn't a hardened product. The repo is public so the modeling decisions are visible to anyone interested in how I think about cross-functional planning systems.

---

## Screenshots

### Strategy through execution in one view
Strategies tie to Yearly Objectives, which flow into Quarterly Objectives and Key Results — and Initiatives are the bets driving the KRs.

<img src="docs/images/cascade.png" alt="The full strategy-to-execution cascade rendered as a flow diagram" width="900">

### Hotspots — what needs attention
A focused triage view for leaders. Each org gets a color-coded health card; expand a card to see that team's specific problems inline.

<img src="docs/images/hotspots.png" alt="Hotspots page with org health cards, one expanded to show problems" width="900">

### Initiatives — portfolio health
Not just delivery status, but how each initiative is actually moving its associated KRs.

<img src="docs/images/initiatives.png" alt="Initiatives page grouped by team showing milestone status and exec RAG" width="900">

### Objectives & KRs — the causal cascade
See how each KR is tracking and which initiatives are contributing to it.

<img src="docs/images/objectives-and-krs.png" alt="Objectives and KRs page with linked initiative tables" width="900">

---

## Why this exists

Most portfolio-management tools emphasize delivery health without a clear view of how the work contributes to the bottom line. And most OKR tools track outcomes without traceability back to the specific bets driving them. The two halves of the picture rarely connect cleanly.

In the OKR-tool category specifically, products tend to optimize for one of two things: a polished UI on top of a thin data model (Lattice, Workboard), or a deep configurable system aimed at large enterprises (Quantive, Ally). What I wanted was different — a sketch in code of *what an OKR system that didn't lie to me would look like*.

Concretely, the design decisions below are the things I'd push back on in most off-the-shelf tools:

### Delivery, impact, and ROI are three different measurements

Most tools have a single "progress" number on an initiative. This app keeps three:

- **Delivery %** — how much of the work has been done
- **Actual KR impact** — how much the linked KR moved as a result (measured retrospectively, on Initiative Updates)
- **Business case ROI** — predicted value vs predicted cost, recorded at planning time

An initiative can ship 100% (delivery done) and move 0% of its target KR (impact missed). That's information worth keeping visible, not collapsing into a single bar.

### Milestone status (team view) and Exec RAG (exec view) are separate fields

Owners set two RAG-style statuses on each initiative:

- **Milestone Delivery Status** — the team's internal view of execution health
- **Exec RAG** — the curated outward signal the owner wants execs to see

When these diverge, that's itself a signal. The Hotspots page surfaces the divergence inline ("exec: 🚧 blocked / team: 🟡 at risk") so you can see when an owner is escalating externally faster than the team's running status reflects.

### KRs get updated directly; initiatives don't update KRs

A KR is a measurement of reality. The world moves it whether or not your initiative shipped. The app models this honestly:

- **KR `current_value`** is edited directly on Key Result Updates (weekly)
- **`actual_kr_impact`** on each initiative→KR link is a retrospective attribution claim (edited on Initiative Updates, lower cadence)

Different question, different cadence, different owner. The "Linked initiatives" reference panel on each KR shows you which bets are aimed at it, but doesn't force the math.

### Leading vs lagging indicators are a tag, not a rollup tree

It's tempting to model leading indicators as parent-child KRs with contribution weights. In practice, the weights become noise — nobody knows whether qualified pipeline drives ARR at 0.4 or 0.6. So this app uses a *declarative tag* on each KR: 🎯 Lagging, 📡 Leading, or standalone. The causal hypothesis is visible without forcing structure that doesn't match reality.

The schema retains `parent_key_result_id` and `contribution_weight` columns as latent infrastructure — if rollup math ever becomes useful, the data layer is ready.

### Initiatives belong to a team, not just to the KRs they move

An initiative's owning team and the KR(s) it moves are independent. A platform team can run an initiative that moves a revenue team's KR — that's the right model for cross-functional work. The `initiative.org_unit_id` field captures ownership separately from the KR linkage.

---

## Pages

The app is organized into four sections in the sidebar:

### Plan
- **📜 Annual Strategy & Objectives** — strategies, yearly objectives, aspirational KRs
- **✏️ Plan a Quarter** — the primary working surface; quarterly objectives, KRs, initiatives, predicted impact, business cases
- **🌊 Plan Flow** — Sankey visualization of the cascade (strategy → yearly → quarterly → KR → initiative) with barycentric ordering to minimize ribbon crossings

### Track
- **📈 Key Result Updates** — weekly check-ins, current values + notes, history per KR
- **📊 Initiative Updates** — execution updates, milestone status, exec RAG, exec narrative, actual impact

### Views
- **🔥 Hotspots** — operational "what needs my attention?" view. Each org gets a color-coded card with rolled-up health; click *Show specifics* to expand the card inline and see that team's specific problems (red KRs, blocked initiatives, planning gaps, overdue milestones)
- **📄 Plan Narrative** — read-the-plan-as-prose top to bottom; structured cascade with indented hierarchy
- **🧭 Objectives & KRs** — KR-centric view with linked initiatives as supporting tables (the causal cascade, KR by KR)
- **🚀 Initiatives** — read-only portfolio view of initiatives, grouped by owning team, sorted with problems at top

### Manage
- **🏛️ Org Units** — team / segment / company hierarchy
- **🚀 Create Initiative** — structural editing of initiatives (title, owner, status, effort, linked KRs, business case)

---

## Tech stack

- **Frontend:** Streamlit (Python). Multi-page navigation, custom HTML/CSS where I needed visual punch
- **Database:** Supabase (Postgres), accessed via the service-role key with app-enforced per-user scoping (no Row Level Security — kept the model simple for a single-user portfolio app)
- **Language:** Python 3.11+, with pandas for data manipulation
- **Visualization:** Plotly for the Plan Flow Sankey

I built this iteratively in multi-hour sessions using Claude Code (Anthropic's CLI agent) for implementation work. The architectural decisions, modeling choices, and feature scoping were mine; the implementation was Claude-assisted. Treat it as a sketch of judgment + delegation, not "wrote it all from scratch."

---

## Local setup

```bash
git clone https://github.com/terrydougan-ai/okr-planning-app
cd okr-planning-app
pip install -r requirements.txt
# Set up a Supabase project, then run schema/schema.sql against it
# (or run schema/migrations.sql in order if you want the historical view)
# Add a .streamlit/secrets.toml with:
#   SUPABASE_URL = "..."
#   SUPABASE_KEY = "..."
streamlit run Overview.py
```

---

## Data model

Eight tables:

| Table | What it holds |
|---|---|
| `org_unit` | Company / segment / team hierarchy |
| `strategy` | Top-level strategic bets |
| `objective` | Yearly and quarterly objectives, tied to a strategy + org unit |
| `key_result` | KRs under an objective. Tracks start / target / current values, indicator type (lagging/leading), owner |
| `initiative` | Discrete bets the team is making. Tracks owner, status, milestone delivery status, exec RAG, exec narrative, delivery %, owning org unit |
| `initiative_key_result` | M:N join. Tracks predicted impact and actual impact per (initiative, KR) pair |
| `business_case` | Predicted value, predicted cost, decision, summary — recorded at planning time for each initiative |
| `check_in` | Time series of KR value updates with optional notes |

The schema lives in `/schema/`:
- **`schema.sql`** — current state, the file to run for a fresh-install database
- **`migrations.sql`** — chronological history of every schema change, with notes on why each was added (useful as commentary on the design evolution)

---

## What this is deliberately NOT

- **Not a multi-tenant production tool.** Single-user app with no auth layer; the service-role Supabase key is used directly. Fine for a portfolio app, not fine for real use.
- **Not "feature-complete."** Some pages have backlog items I haven't gotten to (e.g., time-series visualizations on Key Result Updates — needs ~6+ weeks of check-in data accumulated first to be worth building).
- **Not a polished product UI.** Streamlit's design vocabulary is what it is. I cared about getting the *model* right, not making it look like Notion.
- **Not opinionated about OKR cadence.** The app supports quarterly and yearly horizons but doesn't enforce a particular framework (CFRs, OKR-Vital-Signs, etc.) — it's deliberately a substrate, not a methodology.

---

## What I'd build next

In rough order of value:

1. **Trends / Time Series page.** The `check_in` table is accumulating data; a per-KR line chart over the last 8 weeks would close the "is this getting better or worse?" gap a single color dot can't answer.
2. **Quarterly review export.** PDF or Markdown of the closing state of a quarter — KRs with final values, initiatives with actual impact recorded — useful as an exec deliverable.
3. **Predicted vs actual retrospective view.** For each KR with linked initiatives, side-by-side comparison of predicted impact (planning) vs measured impact (execution). Calibrates the team's planning over time.

These aren't done because each needs real production data to be meaningful — building them now would just give me flat lines and empty comparisons.

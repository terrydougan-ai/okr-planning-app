-- ============================================================================
-- Migration: simulated ambient signals for AI-native drafting
-- ============================================================================
-- Three tables capturing the "ambient signals" a modern PMO team would
-- integrate into their AI workflows: engineering activity (Jira-ish),
-- team communication (Slack-ish), and coordination (calendar).
--
-- The tables are *simulated* — this is a portfolio app, not integrated with
-- real Jira/Slack/Calendar. But the shape and the AI's reasoning over them
-- is what a production version would do. The distinction between "simulated"
-- and "integrated" is data source only; the prompt pattern is identical.
--
-- Design choice: signals link directly to initiative via initiative_id
-- foreign key. In production, this would need to be a fuzzy match (Slack
-- messages don't tag initiative IDs), but the demo simplification is
-- accepted for clarity.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- engineering_activity — Jira-ish signals
-- ----------------------------------------------------------------------------
-- Represents: ticket state changes, PR merges, deployments, incidents.
-- A snapshot of engineering execution as an ambient signal.
create table if not exists engineering_activity (
    id uuid primary key default gen_random_uuid(),
    initiative_id uuid not null references initiative(id) on delete cascade,

    -- What kind of activity: "ticket_transition", "pr_merged", "deploy",
    -- "incident_raised", "blocker_flagged" (freeform string for demo
    -- flexibility; production would enum)
    activity_type text not null,

    -- Short label like "BUG-8127", "EPIC-CACHE-12", "PR #4523"
    reference text,

    -- The human-readable description of what happened
    -- e.g. "moved from In Progress → Blocked", "merged 47-line change",
    -- "deployment to production halted"
    description text not null,

    -- Optional actor
    actor text,  -- e.g. "@sarena", "eng-platform-bot"

    -- When it happened (relative to now via seed)
    occurred_at timestamptz not null default now()
);

create index if not exists idx_engineering_activity_initiative
    on engineering_activity(initiative_id);
create index if not exists idx_engineering_activity_occurred
    on engineering_activity(occurred_at desc);


-- ----------------------------------------------------------------------------
-- team_message — Slack-ish signals
-- ----------------------------------------------------------------------------
-- Represents: chat mentions of the initiative in team channels, DMs.
-- Not every message needs to be about a specific initiative — but in this
-- demo simplification, they all have initiative_id set. See migration notes.
create table if not exists team_message (
    id uuid primary key default gen_random_uuid(),
    initiative_id uuid not null references initiative(id) on delete cascade,

    -- Where it was posted (channel name or "DM")
    channel text not null,       -- e.g. "#eng-platform", "#launches-emea"

    -- Speaker's handle
    author text,                 -- e.g. "@sarena", "@jordan"

    -- The actual message content (short, casual, sometimes ambiguous —
    -- match real Slack tone, not corporate documentation)
    body text not null,

    -- Optional sentiment tag: "concerned", "positive", "neutral", "escalation"
    -- Not machine-derived — a curator (or the AI, in production) has decided.
    sentiment text,

    -- When it was posted
    posted_at timestamptz not null default now()
);

create index if not exists idx_team_message_initiative
    on team_message(initiative_id);
create index if not exists idx_team_message_posted
    on team_message(posted_at desc);


-- ----------------------------------------------------------------------------
-- calendar_event — Coordination signals
-- ----------------------------------------------------------------------------
-- Represents: meetings that happened or are upcoming and are relevant to
-- the initiative. QBRs, incident postmortems, decision meetings, offsites.
create table if not exists calendar_event (
    id uuid primary key default gen_random_uuid(),
    initiative_id uuid not null references initiative(id) on delete cascade,

    -- What kind of meeting: "qbr", "incident_review", "decision_meeting",
    -- "sync", "offsite", "escalation"
    event_type text not null,

    -- Short title
    title text not null,

    -- Optional outcome / summary — one line
    -- e.g. "Decision to defer finance dataset to Q4"
    -- e.g. "Root cause identified as query planner regression"
    outcome text,

    -- Who attended (freeform for demo)
    attendees text,

    -- When it happened
    occurred_at timestamptz not null default now()
);

create index if not exists idx_calendar_event_initiative
    on calendar_event(initiative_id);
create index if not exists idx_calendar_event_occurred
    on calendar_event(occurred_at desc);


-- ----------------------------------------------------------------------------
-- End of migration
-- ----------------------------------------------------------------------------
-- After running this migration, populate with realistic seed data via
-- schema/seed_signals.sql (added in the next step).

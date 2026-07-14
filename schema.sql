-- ============================================================================
-- OKR Planning App — fresh-install schema
-- ============================================================================
-- Run this against an empty Supabase / Postgres database to set up all the
-- tables the app expects. For the incremental history (what was added when
-- and why), see migrations.sql in this same directory.
--
-- Conventions:
--   * UUID primary keys with gen_random_uuid() defaults
--   * Foreign keys cascade on delete where the dependent row has no meaning
--     without its parent (e.g. check_in → key_result, key_result → objective)
--   * Foreign keys use ON DELETE SET NULL where the dependent row can survive
--     losing its parent (e.g. initiative.org_unit_id)
--   * Timestamps default to now() at insert time
-- ============================================================================


-- ----------------------------------------------------------------------------
-- org_unit — the team / segment / company hierarchy
-- ----------------------------------------------------------------------------
-- Self-referencing via parent_unit_id. level is a soft categorization
-- (company / segment / team) used for visual ordering in the app's org
-- tree pickers.
create table org_unit (
    id              uuid primary key default gen_random_uuid(),
    name            text not null,
    level           text,                                       -- 'company' / 'segment' / 'team'
    parent_unit_id  uuid references org_unit(id) on delete set null,
    created_at      timestamptz default now()
);


-- ----------------------------------------------------------------------------
-- strategy — top-level strategic bets
-- ----------------------------------------------------------------------------
-- Attached to an org unit and a fiscal year. Status is a soft tag ('active',
-- 'closed', 'archived'); the app uses it to grey out non-active strategies
-- in views. Multiple strategies can coexist for the same org under different
-- fiscal years.
create table strategy (
    id              uuid primary key default gen_random_uuid(),
    org_unit_id     uuid not null references org_unit(id) on delete cascade,
    title           text not null,
    description     text,
    fiscal_year     integer,                                    -- e.g. 2026
    status          text default 'active',                      -- 'active' / 'closed' / 'archived'
    created_at      timestamptz default now()
);


-- ----------------------------------------------------------------------------
-- objective — yearly and quarterly objectives
-- ----------------------------------------------------------------------------
-- period encodes both horizon and time: 'FY2026' for yearly, 'Q3-2026' for
-- quarterly. Quarterly objectives often roll up to yearly objectives via
-- parent_objective_id (no cascade — a quarterly objective can survive losing
-- its yearly parent; the data is preserved with the link nulled).
create table objective (
    id                      uuid primary key default gen_random_uuid(),
    org_unit_id             uuid not null references org_unit(id) on delete cascade,
    strategy_id             uuid references strategy(id) on delete set null,
    parent_objective_id     uuid references objective(id) on delete set null,
    period                  text not null,                      -- 'FY2026' or 'Q3-2026'
    title                   text not null,
    owner                   text,
    status                  text default 'active',              -- 'active' / 'closed' / 'archived'
    created_at              timestamptz default now()
);


-- ----------------------------------------------------------------------------
-- key_result — KRs under an objective
-- ----------------------------------------------------------------------------
-- start_value / target_value / current_value drive progress math
-- (current - start) / (target - start), clamped 0..1.
--
-- indicator_type is a declarative tag for the leading-vs-lagging-vs-standalone
-- distinction. It does NOT drive rollup math — see README.md for rationale.
--
-- parent_key_result_id and contribution_weight are LATENT INFRASTRUCTURE.
-- The schema retains them so a future rollup feature is possible without a
-- migration, but no UI currently exposes them. See the README for why.
create table key_result (
    id                          uuid primary key default gen_random_uuid(),
    objective_id                uuid not null references objective(id) on delete cascade,
    title                       text not null,
    metric_unit                 text,                           -- '%', 'USD', 'count', etc.
    start_value                 numeric,
    target_value                numeric,
    current_value               numeric,
    owner                       text,
    indicator_type              text,                           -- 'lagging' / 'leading' / NULL
    parent_key_result_id        uuid references key_result(id) on delete set null,
    contribution_weight         numeric,
    -- AI review persistence (Phase 9). LATENT — not populated by current
    -- app code. KR check-in notes are ephemeral, so persisting a review
    -- to the parent row would look stale on every page load. KR reviews
    -- live in session state instead. Columns kept in place as harmless
    -- latent capacity; see migrations.sql for the full rationale.
    latest_ai_review            jsonb,
    latest_ai_review_at         timestamptz,
    latest_ai_review_signature  text,
    created_at                  timestamptz default now()
);


-- ----------------------------------------------------------------------------
-- initiative — discrete bets the team is making
-- ----------------------------------------------------------------------------
-- An initiative belongs to a TEAM (via org_unit_id) and is independently
-- linked to one or more KRs via initiative_key_result. The two relationships
-- are separable: a platform team can run an initiative that moves a revenue
-- team's KR.
--
-- Two RAG-style status fields are deliberately kept distinct:
--   milestone_status — team's internal view of execution health
--   exec_rag         — owner's curated exec-facing signal
-- The Hotspots page surfaces divergence between these as its own signal.
--
-- progress_pct (delivery %) is separate from actual_kr_impact (recorded on
-- the join row below) because delivery and impact are different measurements.
create table initiative (
    id                      uuid primary key default gen_random_uuid(),
    org_unit_id             uuid references org_unit(id) on delete set null,
    title                   text not null,
    description             text,
    owner                   text,
    status                  text default 'proposed',            -- 'proposed' / 'active' / 'done' / 'killed'
    effort_estimate         text,                               -- '' / 'XS' / 'S' / 'M' / 'L' / 'XL'
    progress_pct            integer default 0,
    milestone_status        text,                               -- 'on_track' / 'at_risk' / 'off_track' / 'blocked'
    next_milestone_text     text,
    next_milestone_date     date,
    exec_rag                text,                               -- same value set as milestone_status
    exec_narrative          text,
    -- AI review persistence (Phase 9). Only the LATEST review is stored;
    -- see migrations.sql for rationale. Signature is a hash of the reviewed
    -- content used for staleness detection.
    latest_ai_review            jsonb,
    latest_ai_review_at         timestamptz,
    latest_ai_review_signature  text,
    created_at              timestamptz default now()
);


-- ----------------------------------------------------------------------------
-- initiative_key_result — M:N join with per-link impact measurements
-- ----------------------------------------------------------------------------
-- An initiative can move multiple KRs; a KR can be moved by multiple
-- initiatives. predicted_kr_impact is the planning-time estimate;
-- actual_kr_impact is the retrospective measurement (recorded on Initiative
-- Updates, NOT inferred from KR movement). The two are deliberately separable.
create table initiative_key_result (
    initiative_id           uuid not null references initiative(id) on delete cascade,
    key_result_id           uuid not null references key_result(id) on delete cascade,
    predicted_kr_impact     numeric,
    actual_kr_impact        numeric,
    created_at              timestamptz default now(),
    primary key (initiative_id, key_result_id)
);


-- ----------------------------------------------------------------------------
-- business_case — predicted value / cost / decision for each initiative
-- ----------------------------------------------------------------------------
-- One row per initiative. Captures the planning-time financial bet
-- (predicted_value / predicted_cost) and the go/no-go decision. The summary
-- field is free text for the rationale.
create table business_case (
    initiative_id           uuid primary key references initiative(id) on delete cascade,
    predicted_value         numeric,
    predicted_cost          numeric,
    target_metric           text,                               -- free text e.g. 'ARR', 'cost saved'
    target_metric_unit      text,                               -- '$', '%', 'count', etc.
    decision                text default 'pending',             -- 'pending' / 'approved' / 'rejected'
    summary                 text,
    created_at              timestamptz default now()
);


-- ----------------------------------------------------------------------------
-- check_in — time series of KR value updates with optional notes
-- ----------------------------------------------------------------------------
-- A row is inserted when a KR's current_value moves OR when a user attaches
-- a note to an unchanged KR. Powers the "▸ history" disclosure on Key Result
-- Updates and the last-note quote on the Hotspots triage list.
create table check_in (
    id              uuid primary key default gen_random_uuid(),
    key_result_id   uuid not null references key_result(id) on delete cascade,
    value           numeric not null,
    note            text,
    created_at      timestamptz default now()
);

create index idx_check_in_kr_time on check_in(key_result_id, created_at desc);

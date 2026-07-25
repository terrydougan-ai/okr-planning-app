-- ============================================================================
-- AI OKR Execution System — incremental migration history
-- ============================================================================
-- This file is the CHRONOLOGICAL HISTORY of schema changes during
-- development. It's here so the evolution of the data model is visible:
-- what was added when, and (in the comments) why.
--
-- If you're spinning up a fresh database, USE schema.sql INSTEAD —
-- it represents the same end state in one pass. This file is for context
-- and for anyone upgrading an existing instance.
--
-- The migrations are ordered roughly by the design conversation that
-- prompted them.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Phase 1: Initial tables
-- ----------------------------------------------------------------------------
-- The starting model: org units, strategies, objectives, KRs, initiatives
-- with the M:N join, and business cases. See schema.sql for the actual
-- CREATE TABLE statements.


-- ----------------------------------------------------------------------------
-- Phase 2: KR check-in history
-- ----------------------------------------------------------------------------
-- Added when Key Result Updates was built. Each KR check-in (whether a
-- value change or just a note) now inserts a check_in row so the team can
-- see the trajectory over time, not just the current point.

create table check_in (
    id              uuid primary key default gen_random_uuid(),
    key_result_id   uuid not null references key_result(id) on delete cascade,
    value           numeric not null,
    note            text,
    created_at      timestamptz default now()
);

create index idx_check_in_kr_time on check_in(key_result_id, created_at desc);


-- ----------------------------------------------------------------------------
-- Phase 3: KR ownership
-- ----------------------------------------------------------------------------
-- Added when filtering by KR owner became useful on Key Result Updates and
-- elsewhere. Free text — not a foreign key to a users table because there
-- is no users table; the app is single-user.

alter table key_result add column owner text;


-- ----------------------------------------------------------------------------
-- Phase 4: Strategy status
-- ----------------------------------------------------------------------------
-- Lets strategies be archived without being deleted. The app uses this to
-- grey out non-active strategies in views.

alter table strategy add column status text default 'active';


-- ----------------------------------------------------------------------------
-- Phase 5: Initiative milestone + exec fields
-- ----------------------------------------------------------------------------
-- When the Track section was split into Key Result Updates and Initiative
-- Updates, four new fields landed on initiative:
--   next_milestone_text/date — what milestone the team is heading toward
--   exec_narrative — the curated exec-facing prose update
--   exec_rag — the exec-facing RAG signal (separate from milestone_status,
--              which captures the team's internal view)
-- The two RAG fields are deliberately kept distinct because their
-- divergence is itself a signal worth surfacing.

alter table initiative add column next_milestone_text text;
alter table initiative add column next_milestone_date date;
alter table initiative add column exec_narrative text;
alter table initiative add column exec_rag text;


-- ----------------------------------------------------------------------------
-- Phase 6: KR indicator type (leading vs lagging tag)
-- ----------------------------------------------------------------------------
-- A lightweight tag — Leading (early signal), Lagging (final outcome), or
-- standalone (NULL). No rollup math; just a label that surfaces causal
-- intent without forcing a parent-child structure. The schema retains
-- parent_key_result_id and contribution_weight columns from earlier as
-- latent infrastructure, in case rollup math ever becomes useful.

alter table key_result add column indicator_type text;


-- ----------------------------------------------------------------------------
-- Phase 7: Initiative owning org unit
-- ----------------------------------------------------------------------------
-- An initiative belongs to a TEAM (org unit) independently from the KR(s)
-- it moves. This enables cross-functional work — a platform team can run
-- an initiative that moves a revenue team's KR — and also fixes the
-- problem of orphan initiatives (no KR link) being invisible to the
-- Hotspots roll-up. With org_unit_id set, the initiative surfaces under
-- its owning team's card regardless of KR linkage.

alter table initiative add column org_unit_id uuid references org_unit(id) on delete set null;


-- ----------------------------------------------------------------------------
-- Phase 8: Strategy fiscal year
-- ----------------------------------------------------------------------------
-- A single strategy can persist across multiple fiscal years, or multiple
-- strategies can coexist for one org in the same year. The app filters
-- strategies by fiscal year on Plan a Quarter, Annual Strategy, and Plan
-- Narrative — so this column is required for correct scoping. Backfill
-- existing rows to the current planning year.

alter table strategy add column fiscal_year integer;
update strategy set fiscal_year = 2026 where fiscal_year is null;

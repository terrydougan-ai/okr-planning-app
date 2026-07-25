-- ============================================================================
-- Seed: simulated ambient signals for AI-native drafting demo
-- ============================================================================
-- Realistic-feeling engineering activity, team messages, and calendar events
-- for a subset of initiatives. Written by hand to feel like actual Jira /
-- Slack / calendar entries, not AI-generated marketing copy.
--
-- Coverage philosophy:
--   * 5-6 signal-rich initiatives — the ones that will be demoed
--   * Remaining initiatives get sparse or no signal — matches reality;
--     not everything is instrumented
--   * Signal richness correlates with the Verdict tier of the initiative:
--     Rework-tier initiatives should show signals that *contradict* the
--     human narrative. That's the killer AI moment.
--
-- Timing:
--   Recent activity uses `now() - interval` so the demo always shows
--   "recent" data regardless of when the seed is run.
-- ============================================================================

-- Clear existing signal data (safe re-run)
truncate table engineering_activity, team_message, calendar_event cascade;


-- ----------------------------------------------------------------------------
-- Initiative #6: Query engine caching layer (Rework tier — the demo star)
-- ----------------------------------------------------------------------------
-- Story the signals tell:
--   Weeks 1-2: healthy migration activity, PRs merging
--   Week 3: a customer incident (near-miss data loss on Redwood Financial)
--   Week 4+: activity slows, one senior engineer flags concurrency issue,
--            team lead posts concerns in #eng-platform
--   Recent: PR merge rate dropped to near-zero, incident review meeting held
--
-- The exec narrative for this initiative claims "on track, minor issues" —
-- the signals should let AI see through that.

insert into engineering_activity (initiative_id, activity_type, reference, description, actor, occurred_at) values
    ('10000000-0000-0000-0000-000000000006', 'pr_merged', 'PR #4521', 'Migrated top query type (aggregations) to caching layer. p95 latency down 42% on migrated paths.', '@marcus', now() - interval '32 days'),
    ('10000000-0000-0000-0000-000000000006', 'pr_merged', 'PR #4534', 'Migrated GROUP BY queries. Cache hit rate 78% first week.', '@marcus', now() - interval '28 days'),
    ('10000000-0000-0000-0000-000000000006', 'pr_merged', 'PR #4551', 'Migrated ORDER BY queries. Deployment successful.', '@jinny', now() - interval '24 days'),
    ('10000000-0000-0000-0000-000000000006', 'incident_raised', 'INC-2847', 'Customer (Redwood Financial) reported stale query results on their nightly reporting job. Suspected cache invalidation lag on join-heavy queries.', '@oncall', now() - interval '20 days'),
    ('10000000-0000-0000-0000-000000000006', 'blocker_flagged', 'BUG-8891', 'Race condition identified in cache invalidation on join queries under concurrent write load. Reproduction confirmed. Priority: P1.', '@marcus', now() - interval '18 days'),
    ('10000000-0000-0000-0000-000000000006', 'pr_merged', 'PR #4573', 'Partial fix for INC-2847 — added invalidation delay for join queries. Marcus flagged this as a workaround, not a solution.', '@marcus', now() - interval '16 days'),
    ('10000000-0000-0000-0000-000000000006', 'ticket_transition', 'EPIC-CACHE-12', 'Moved from In Progress → At Risk. Owner: @marcus. Note: "Concurrency issues on join queries need deeper redesign. Estimating 3-4 additional weeks."', '@marcus', now() - interval '12 days'),
    ('10000000-0000-0000-0000-000000000006', 'ticket_transition', 'BUG-8891', 'Moved from Ready → Blocked. Note: "Waiting on architectural review with @sarena before proceeding."', '@marcus', now() - interval '9 days'),
    ('10000000-0000-0000-0000-000000000006', 'deploy', 'REL-4577', 'Deployment paused for read paths that use joins. Only aggregation and GROUP BY caching remain enabled.', '@ops-bot', now() - interval '7 days'),
    ('10000000-0000-0000-0000-000000000006', 'ticket_transition', 'EPIC-CACHE-12', 'No status update in 7 days. Last activity: architectural review scheduled but not held.', null, now() - interval '2 days');

insert into team_message (initiative_id, channel, author, body, sentiment, posted_at) values
    ('10000000-0000-0000-0000-000000000006', '#eng-platform', '@marcus', 'Migration going well. p95 latency dropping as we expected. Aggregation queries were the easy win.', 'positive', now() - interval '30 days'),
    ('10000000-0000-0000-0000-000000000006', '#eng-platform', '@sarena', 'Redwood incident this morning — cache invalidation is more complex than we modeled. Escalating to architectural review.', 'concerned', now() - interval '20 days'),
    ('10000000-0000-0000-0000-000000000006', '#eng-oncall', '@marcus', 'INC-2847 recovered but I want to be direct: this was a near-miss on data loss. Customer''s Monday report would have shown wrong numbers if @jinny hadn''t caught it.', 'escalation', now() - interval '19 days'),
    ('10000000-0000-0000-0000-000000000006', '#eng-platform', '@jinny', 'The workaround shipped in PR #4573 is a bandaid. We need to redesign the invalidation logic for join queries. I can''t recommend continuing rollout to join paths until we do.', 'concerned', now() - interval '15 days'),
    ('10000000-0000-0000-0000-000000000006', '#eng-platform', '@marcus', 'Hearing you. Architectural review meeting scheduled with sarena next week. Progress on join paths paused until then.', 'neutral', now() - interval '14 days'),
    ('10000000-0000-0000-0000-000000000006', '#exec-updates', '@marcus', 'Weekly update: caching layer 65% deployed. Some concurrency issues under review. On track for Q3 target.', 'positive', now() - interval '8 days'),
    ('10000000-0000-0000-0000-000000000006', '#eng-platform', '@jinny', 'Marcus — architectural review meeting was rescheduled again. This is now blocking three PRs. Can we escalate?', 'escalation', now() - interval '3 days');

insert into calendar_event (initiative_id, event_type, title, outcome, attendees, occurred_at) values
    ('10000000-0000-0000-0000-000000000006', 'incident_review', 'INC-2847 Postmortem: Redwood Financial cache invalidation', 'Root cause: cache invalidation TTL insufficient for concurrent writes on join queries. Workaround shipped (invalidation delay). Long-term fix requires invalidation redesign. Action: architectural review meeting.', 'Marcus, Sarena, Jinny, VP Platform', now() - interval '18 days'),
    ('10000000-0000-0000-0000-000000000006', 'decision_meeting', 'Architectural review: cache invalidation for join queries', 'RESCHEDULED — did not occur. New date: TBD.', 'Marcus, Sarena', now() - interval '10 days'),
    ('10000000-0000-0000-0000-000000000006', 'decision_meeting', 'Architectural review: cache invalidation for join queries (rescheduled)', 'RESCHEDULED AGAIN — Marcus and Sarena travel conflict. Next attempt: next week.', 'Marcus, Sarena', now() - interval '4 days');


-- ----------------------------------------------------------------------------
-- Initiative #5: Q3 Production Bug Push (Ready tier)
-- ----------------------------------------------------------------------------
-- Story: steady, healthy execution. Rich signal but positive throughout.
-- Confirms the AI reads good signals as good.

insert into engineering_activity (initiative_id, activity_type, reference, description, actor, occurred_at) values
    ('10000000-0000-0000-0000-000000000005', 'ticket_transition', 'BUG-7891', 'Moved from Open → Fixed. Sev-2 incident from Q2 resolved. Customer verification in progress.', '@priya', now() - interval '28 days'),
    ('10000000-0000-0000-0000-000000000005', 'ticket_transition', 'BUG-8012', 'Moved from Open → Fixed. Verified with customer.', '@priya', now() - interval '25 days'),
    ('10000000-0000-0000-0000-000000000005', 'ticket_transition', 'BUG-8091', 'Race condition confirmed. Reproduction case built by @dev-team. Priority: P1.', '@priya', now() - interval '19 days'),
    ('10000000-0000-0000-0000-000000000005', 'ticket_transition', 'BUG-8127', 'Moved from Open → Ready for Deploy. Staged for 9/15 release.', '@dev-team', now() - interval '12 days'),
    ('10000000-0000-0000-0000-000000000005', 'ticket_transition', 'BUG-8134', 'Moved from Open → Ready for Deploy. Staged for 9/15 release.', '@dev-team', now() - interval '11 days'),
    ('10000000-0000-0000-0000-000000000005', 'ticket_transition', 'BUG-8091', 'Still Open. Concurrency pattern isolated but fix requires scheduler changes. Estimated: 5 more days.', '@priya', now() - interval '5 days');

insert into team_message (initiative_id, channel, author, body, sentiment, posted_at) values
    ('10000000-0000-0000-0000-000000000005', '#sre-team', '@priya', 'Bug push going well. 9 of 12 fixed, tracking clean. BUG-8091 is the only concerning one — race condition harder to reproduce than expected.', 'neutral', now() - interval '10 days'),
    ('10000000-0000-0000-0000-000000000005', '#sre-team', '@priya', 'BUG-8091 update: pattern isolated. Fix scoped. Should ship by 9/18.', 'positive', now() - interval '5 days');

insert into calendar_event (initiative_id, event_type, title, outcome, attendees, occurred_at) values
    ('10000000-0000-0000-0000-000000000005', 'sync', 'Weekly bug push standup', 'Progress reviewed. On track. BUG-8091 flagged as remaining risk.', 'SRE team, VP Platform', now() - interval '3 days');


-- ----------------------------------------------------------------------------
-- Initiative #3: ProductA Launch (Needs sharpening tier)
-- ----------------------------------------------------------------------------
-- Story: mixed signals. Strong Berlin event momentum but pipeline conversion
-- is slower than modeled. AI draft should catch what human narrative smoothed over.

insert into engineering_activity (initiative_id, activity_type, reference, description, actor, occurred_at) values
    ('10000000-0000-0000-0000-000000000003', 'deploy', 'REL-4560', 'ProductA feature flag enabled for Berlin event demo accounts.', '@ops-bot', now() - interval '14 days');

insert into team_message (initiative_id, channel, author, body, sentiment, posted_at) values
    ('10000000-0000-0000-0000-000000000003', '#launches-emea', '@sales-manager', 'Berlin registrations tracking well — 62 confirmed as of this morning. Interest is real.', 'positive', now() - interval '17 days'),
    ('10000000-0000-0000-0000-000000000003', '#launches-emea', '@sales-manager', 'Post-event update: 74 attendees, ~40 solid conversations. Pipeline forming.', 'positive', now() - interval '10 days'),
    ('10000000-0000-0000-0000-000000000003', '#gtm-strategy', '@emea-sales-lead', 'Concerning pattern: discovery calls booked but conversion to qualified opportunities is running ~40% below model. Not sure yet if this is speed of trust in the region or a real fit issue.', 'concerned', now() - interval '8 days'),
    ('10000000-0000-0000-0000-000000000003', '#gtm-strategy', '@vp-sales', 'Agree with @emea-sales-lead. Need to dig into why. Scheduled a review for next week.', 'concerned', now() - interval '7 days'),
    ('10000000-0000-0000-0000-000000000003', '#launches-emea', '@sales-manager', 'Two more discovery calls booked this week. Still positive momentum on the top of the funnel.', 'positive', now() - interval '3 days');

insert into calendar_event (initiative_id, event_type, title, outcome, attendees, occurred_at) values
    ('10000000-0000-0000-0000-000000000003', 'sync', 'ProductA Berlin launch event', 'Successful — 74 enterprise attendees, positive reception.', 'Sales team, exec sponsors', now() - interval '10 days'),
    ('10000000-0000-0000-0000-000000000003', 'decision_meeting', 'EMEA pipeline conversion review', 'Meeting scheduled but not yet held. Agenda: why conversion is running below model.', 'VP Sales, EMEA Sales Lead, VP Product', now() - interval '1 day');


-- ----------------------------------------------------------------------------
-- Initiative #14: Claude/Cursor rollout to Engineering (Ready tier)
-- ----------------------------------------------------------------------------
-- Story: healthy adoption signals. Two teams leaning in. Some senior
-- engineers slow to adopt — matches narrative honestly.

insert into engineering_activity (initiative_id, activity_type, reference, description, actor, occurred_at) values
    ('10000000-0000-0000-0000-000000000014', 'ticket_transition', 'ADOPT-01', 'Weekly usage report: 47% of engineers used Claude Code for code review this week. Up from 39% last week.', '@usage-bot', now() - interval '14 days'),
    ('10000000-0000-0000-0000-000000000014', 'ticket_transition', 'ADOPT-02', 'Platform Foundations team: 100% weekly usage. Full team rituals in place.', '@usage-bot', now() - interval '10 days'),
    ('10000000-0000-0000-0000-000000000014', 'ticket_transition', 'ADOPT-01', 'Weekly usage report: 52% weekly active. Data Ingest team at 90%. Senior engineers cohort at 22%.', '@usage-bot', now() - interval '3 days');

insert into team_message (initiative_id, channel, author, body, sentiment, posted_at) values
    ('10000000-0000-0000-0000-000000000014', '#eng-tools', '@platform-lead', 'Team rituals for Claude code review are landing well. Weekly review meeting includes an AI-review section now.', 'positive', now() - interval '12 days'),
    ('10000000-0000-0000-0000-000000000014', '#eng-tools', '@data-ingest-lead', 'Data Ingest team all in. Best PR feedback quality since I''ve been here.', 'positive', now() - interval '9 days'),
    ('10000000-0000-0000-0000-000000000014', '#eng-tools', '@senior-eng-1', 'Been slow to adopt. Not opposed — just want to understand the failure modes before I trust it on my reviews. Setting up a 1:1 with the VP Eng next week to work through it.', 'neutral', now() - interval '5 days');


-- ----------------------------------------------------------------------------
-- Initiative #15: AI Maturity Scale rollout (Rework tier)
-- ----------------------------------------------------------------------------
-- Story: sparse and vague signal. Matches how the human narrative reads —
-- "great engagement" but nothing measurable happening. AI should note that
-- signals corroborate lack of traction.

insert into engineering_activity (initiative_id, activity_type, reference, description, actor, occurred_at) values
    ('10000000-0000-0000-0000-000000000015', 'ticket_transition', 'MATURITY-01', 'Framework v1 published to internal wiki.', '@cos-team', now() - interval '25 days');

insert into team_message (initiative_id, channel, author, body, sentiment, posted_at) values
    ('10000000-0000-0000-0000-000000000015', '#dh-forum', '@head-of-product', 'Completed my self-assessment. Feedback: the levels are aspirational but Level 3+ definitions need concrete anchor examples.', 'neutral', now() - interval '20 days'),
    ('10000000-0000-0000-0000-000000000015', '#dh-forum', '@head-of-sales', 'Similar concern. I''m not sure what "workflows fundamentally redesigned" looks like in practice for my team. Would help to see an example.', 'concerned', now() - interval '15 days');

-- No calendar events for this initiative — no meetings actually happened.
-- That absence is itself a signal.


-- ----------------------------------------------------------------------------
-- Initiative #8: AI query assistant beta (Needs sharpening tier)
-- ----------------------------------------------------------------------------
-- Story: design-partner activity is real but engagement metrics unclear.
-- Matches narrative that "engagement trending well" without numbers.

insert into engineering_activity (initiative_id, activity_type, reference, description, actor, occurred_at) values
    ('10000000-0000-0000-0000-000000000008', 'ticket_transition', 'BETA-01', 'Kestrel Labs onboarded. First queries logged.', '@pm-ai', now() - interval '25 days'),
    ('10000000-0000-0000-0000-000000000008', 'ticket_transition', 'BETA-02', 'Redwood Financial onboarded. Focus area: regulatory reporting queries.', '@pm-ai', now() - interval '20 days'),
    ('10000000-0000-0000-0000-000000000008', 'ticket_transition', 'BETA-03', 'Meridian Retail onboarded. Early feedback: needs query explanation feature.', '@pm-ai', now() - interval '12 days'),
    ('10000000-0000-0000-0000-000000000008', 'ticket_transition', 'BETA-04', 'Beacon Insurance onboarded. 4 active partners.', '@pm-ai', now() - interval '6 days');

insert into team_message (initiative_id, channel, author, body, sentiment, posted_at) values
    ('10000000-0000-0000-0000-000000000008', '#product-beta', '@pm-ai', 'Kestrel Labs feedback: love the interface, want more control over which tables it can query.', 'neutral', now() - interval '22 days'),
    ('10000000-0000-0000-0000-000000000008', '#product-beta', '@pm-ai', 'Redwood is asking for query explanation before we ship the query. That''s a UX pattern I''d push back on — makes the feature slower to use.', 'concerned', now() - interval '15 days'),
    ('10000000-0000-0000-0000-000000000008', '#product-beta', '@pm-ai', 'Meridian usage frequency: 2 uses/week per partner. Need to get this to 3+ for our target.', 'neutral', now() - interval '8 days');


-- ----------------------------------------------------------------------------
-- End of seed
-- ----------------------------------------------------------------------------

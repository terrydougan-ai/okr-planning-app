-- ============================================================================
-- AI OKR Execution System — demo seed data ("Acme Analytics" story)
-- ============================================================================
-- Run this against a DEMO Supabase project (NOT your production one) to
-- populate it with a coherent multi-team story for portfolio demonstrations.
--
-- The story:
--   "Acme Analytics" — a mid-sized analytics SaaS company in mid-Q3 2026
--   with three teams (Product, Go-to-Market, Platform).
--
-- The data is deliberately staged so each design decision the app makes is
-- VISIBLE in the demo:
--   * Leading vs lagging indicator tags (🎯 / 📡) — visible on Product team
--   * Exec-vs-team RAG divergence — ProductA Launch initiative
--   * Cross-team initiative ownership — Q3 Production Bug Push (Platform-owned,
--     moves a Product team KR)
--   * Orphaned initiatives — Documentation Overhaul (no KR linked, no org_unit_id)
--   * Planning gaps (predicted impact < gap) — Go-to-Market Closed deals KR
--   * Past-milestone-date warnings — EMEA Expansion initiative
--
-- This script is IDEMPOTENT — re-running wipes the seed data and rebuilds it.
-- Safe to run on a demo database; DESTRUCTIVE on a real one. Read carefully.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Wipe existing data (cascading from the roots)
-- ----------------------------------------------------------------------------
-- check_in cascades from key_result; key_result cascades from objective.
-- initiative_key_result and business_case cascade from initiative.
-- So truncating org_unit (which cascades to strategy → objective → key_result
-- → check_in) plus initiative (which cascades to its join tables) covers
-- everything.
truncate table org_unit, strategy, initiative cascade;


-- ----------------------------------------------------------------------------
-- Org units — Acme Analytics with three teams
-- ----------------------------------------------------------------------------
insert into org_unit (id, name, level, parent_unit_id) values
  ('a0000000-0000-0000-0000-000000000001', 'Acme Analytics', 'company', null),
  ('a0000000-0000-0000-0000-000000000002', 'Product',         'team',    'a0000000-0000-0000-0000-000000000001'),
  ('a0000000-0000-0000-0000-000000000003', 'Go-to-Market',    'team',    'a0000000-0000-0000-0000-000000000001'),
  ('a0000000-0000-0000-0000-000000000004', 'Platform',        'team',    'a0000000-0000-0000-0000-000000000001');


-- ----------------------------------------------------------------------------
-- Strategy — one top-level strategic bet
-- ----------------------------------------------------------------------------
insert into strategy (id, org_unit_id, title, description, fiscal_year, status) values
  (
    'b0000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'Make Acme indispensable to data analysts',
    'Become the default analytics platform for mid-market data teams by combining best-in-class onboarding, technical reliability, and a high-value pipeline of design partners.',
    2026,
    'active'
  ),
  -- Strategy 2 — the AI-native bet (added alongside the platform strategy)
  (
    'b0000000-0000-0000-0000-000000000002',
    'a0000000-0000-0000-0000-000000000001',
    'Become the AI-native analytics platform for mid-market',
    'Two parallel bets: (a) ship AI-augmented workflows customers pay for — starting with the AI query assistant, then expanding across core workflows; (b) operate as an AI-native team ourselves, measured in hours saved per FTE and cycle-time reduction. Aggressive on both angles — competitors who wait a year will be a year behind on both product and operating leverage.',
    2026,
    'active'
  );


-- ----------------------------------------------------------------------------
-- Yearly objectives (FY2026) with aspirational KRs
-- ----------------------------------------------------------------------------
insert into objective (id, org_unit_id, strategy_id, parent_objective_id, period, title, owner, status) values
  -- Company yearly — Product growth
  (
    'c0000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'b0000000-0000-0000-0000-000000000001',
    null,
    'FY2026',
    'Win the analytics platform of choice for mid-market data teams',
    'CEO',
    'active'
  ),
  -- Company yearly — Operational excellence
  (
    'c0000000-0000-0000-0000-000000000002',
    'a0000000-0000-0000-0000-000000000001',
    'b0000000-0000-0000-0000-000000000001',
    null,
    'FY2026',
    'Operate with the reliability and pace expected of a platform we want analysts to depend on',
    'COO',
    'active'
  ),
  -- Company yearly under Strategy 2 (AI-native, product angle)
  (
    'c0000000-0000-0000-0000-000000000003',
    'a0000000-0000-0000-0000-000000000001',
    'b0000000-0000-0000-0000-000000000002',
    null,
    'FY2026',
    'AI capabilities are core to how customers use Acme — not features on the side',
    'CEO',
    'active'
  ),
  -- Company yearly under Strategy 2 (AI-native, operating angle)
  (
    'c0000000-0000-0000-0000-000000000004',
    'a0000000-0000-0000-0000-000000000001',
    'b0000000-0000-0000-0000-000000000002',
    null,
    'FY2026',
    'Acme teams operate AI-native — measurable, not aspirational',
    'Chief of Staff',
    'active'
  );


-- Aspirational KRs (yearly)
insert into key_result (id, objective_id, title, metric_unit, start_value, target_value, current_value, owner, indicator_type) values
  -- Yearly KRs under Win-the-platform
  (
    'd0000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'Annual recurring revenue (ARR)',
    'USD',
    18000000, 30000000, 22500000,
    'CFO',
    'lagging'
  ),
  (
    'd0000000-0000-0000-0000-000000000002',
    'c0000000-0000-0000-0000-000000000001',
    'Logos in our target customer segment',
    'count',
    120, 200, 148,
    'VP Sales',
    'lagging'
  ),
  -- Yearly KRs under Operate-reliably
  (
    'd0000000-0000-0000-0000-000000000003',
    'c0000000-0000-0000-0000-000000000002',
    'Platform uptime (rolling 90-day)',
    '%',
    99.7, 99.95, 99.84,
    'VP Platform',
    'lagging'
  ),
  (
    'd0000000-0000-0000-0000-000000000004',
    'c0000000-0000-0000-0000-000000000002',
    'Production incidents (severity 1 or 2)',
    'count',
    24, 12, 16,
    'VP Platform',
    'lagging'
  ),

  -- Yearly KRs under Strategy 2 · Objective 2A (product-angle)
  (
    'd0000000-0000-0000-0000-000000000005',
    'c0000000-0000-0000-0000-000000000003',
    'Paid accounts with an AI-feature monthly active user',
    '%',
    12, 60, 22,
    'VP Product',
    'lagging'
  ),
  (
    'd0000000-0000-0000-0000-000000000006',
    'c0000000-0000-0000-0000-000000000003',
    'Median time-to-first-insight for new signups',
    'min',
    42, 18, 34,
    'VP Product',
    'lagging'
  ),
  (
    'd0000000-0000-0000-0000-000000000007',
    'c0000000-0000-0000-0000-000000000003',
    'AI-augmented workflow adoption (weekly sessions per paid account)',
    'count',
    0.4, 3.0, 0.9,
    'VP Product',
    'leading'
  ),

  -- Yearly KRs under Strategy 2 · Objective 2B (operating-angle)
  (
    'd0000000-0000-0000-0000-000000000008',
    'c0000000-0000-0000-0000-000000000004',
    'Median hours saved per FTE per week via AI-augmented workflows',
    'hours',
    1.0, 5.0, 2.2,
    'Chief of Staff',
    'lagging'
  ),
  (
    'd0000000-0000-0000-0000-000000000009',
    'c0000000-0000-0000-0000-000000000004',
    'Teams reaching AI Maturity Level 3+ on internal scale',
    '%',
    0, 70, 15,
    'Chief of Staff',
    'lagging'
  ),
  (
    'd0000000-0000-0000-0000-000000000010',
    'c0000000-0000-0000-0000-000000000004',
    'Engineering PR cycle time (median, end-to-end)',
    'hours',
    42, 18, 34,
    'VP Engineering',
    'leading'
  );


-- ----------------------------------------------------------------------------
-- Quarterly objectives (Q3-2026) per team, each laddering to a yearly objective
-- ----------------------------------------------------------------------------
insert into objective (id, org_unit_id, strategy_id, parent_objective_id, period, title, owner, status) values
  -- Product team quarterly objective — ladders to Win-the-platform
  (
    'e0000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000002',
    'b0000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'Q3-2026',
    'New signups become activated, engaged users within two weeks',
    'VP Product',
    'active'
  ),
  -- Go-to-Market quarterly objective — ladders to Win-the-platform
  (
    'e0000000-0000-0000-0000-000000000002',
    'a0000000-0000-0000-0000-000000000003',
    'b0000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'Q3-2026',
    'Land flagship logos in EMEA mid-market',
    'VP Sales',
    'active'
  ),
  -- Platform team quarterly objective — ladders to Operate-reliably
  (
    'e0000000-0000-0000-0000-000000000003',
    'a0000000-0000-0000-0000-000000000004',
    'b0000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000002',
    'Q3-2026',
    'Reduce production noise so customer-facing teams can sell with confidence',
    'VP Platform',
    'active'
  ),
  -- Go-to-Market quarterly objective — Customer Success on the top 50 accounts.
  -- Ladders to the same growth yearly as the EMEA logos objective — this
  -- deliberately shows that one yearly objective can be moved by multiple
  -- quarterly objectives across different segments (new logos AND retention).
  (
    'e0000000-0000-0000-0000-000000000004',
    'a0000000-0000-0000-0000-000000000003',
    'b0000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'Q3-2026',
    'Retain and expand our top 50 accounts',
    'VP Customer Success',
    'active'
  ),
  -- Product team quarterly objective — Retention / usage depth on existing
  -- customers (complements the activation-focused objective above).
  (
    'e0000000-0000-0000-0000-000000000005',
    'a0000000-0000-0000-0000-000000000002',
    'b0000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'Q3-2026',
    'Existing customers expand their usage of the platform',
    'VP Product',
    'active'
  ),
  -- Quarterly objective under Strategy 2 · Y2A — Product AI (Q3-2A)
  (
    'e0000000-0000-0000-0000-000000000006',
    'a0000000-0000-0000-0000-000000000002',
    'b0000000-0000-0000-0000-000000000002',
    'c0000000-0000-0000-0000-000000000003',
    'Q3-2026',
    'Ship the first AI-augmented workflow a real customer would pay for',
    'VP Product',
    'active'
  ),
  -- Quarterly objective under Strategy 2 · Y2B — Engineering AI-native (Q3-2B)
  (
    'e0000000-0000-0000-0000-000000000007',
    'a0000000-0000-0000-0000-000000000004',
    'b0000000-0000-0000-0000-000000000002',
    'c0000000-0000-0000-0000-000000000004',
    'Q3-2026',
    'Get Engineering to AI-native baseline; instrument the rest of the org',
    'VP Engineering',
    'active'
  ),
  -- Quarterly objective under Strategy 2 · Y2B — Company-level measurement (Q3-2C).
  -- Owned at the company level because CoS orchestrates cross-team work.
  -- Also exercises the app's ability to hold company-level quarterly objectives.
  (
    'e0000000-0000-0000-0000-000000000008',
    'a0000000-0000-0000-0000-000000000001',
    'b0000000-0000-0000-0000-000000000002',
    'c0000000-0000-0000-0000-000000000004',
    'Q3-2026',
    'Establish the measurement infrastructure for AI ROI',
    'Chief of Staff',
    'active'
  );


-- ----------------------------------------------------------------------------
-- Quarterly KRs — the workhorses
-- ----------------------------------------------------------------------------
insert into key_result (id, objective_id, title, metric_unit, start_value, target_value, current_value, owner, indicator_type) values
  -- Product team KRs under Activation objective
  (
    'f0000000-0000-0000-0000-000000000001',
    'e0000000-0000-0000-0000-000000000001',
    'Activation rate (signups reaching first insight within 14 days)',
    '%',
    32, 55, 42,
    'Head of Onboarding',
    'lagging'           -- the outcome we care about
  ),
  (
    'f0000000-0000-0000-0000-000000000002',
    'e0000000-0000-0000-0000-000000000001',
    'Onboarding tutorial completion rate',
    '%',
    48, 75, 64,
    'Head of Onboarding',
    'leading'           -- early signal that predicts activation
  ),
  (
    'f0000000-0000-0000-0000-000000000003',
    'e0000000-0000-0000-0000-000000000001',
    'Sample dataset usage in first 7 days',
    '%',
    22, 60, 35,
    'Head of Onboarding',
    'leading'           -- another early signal
  ),
  -- Go-to-Market KRs under EMEA logos objective
  (
    'f0000000-0000-0000-0000-000000000004',
    'e0000000-0000-0000-0000-000000000002',
    'EMEA mid-market closed-won deals',
    'count',
    0, 12, 3,
    'EMEA Sales Lead',
    null
  ),
  (
    'f0000000-0000-0000-0000-000000000005',
    'e0000000-0000-0000-0000-000000000002',
    'EMEA qualified pipeline created',
    'USD',
    2400000, 12000000, 5800000,
    'EMEA Sales Lead',
    'leading'
  ),
  -- Platform team KRs under Reduce-production-noise objective
  (
    'f0000000-0000-0000-0000-000000000006',
    'e0000000-0000-0000-0000-000000000003',
    'P1/P2 production incidents (this quarter)',
    'count',
    7, 2, 5,                 -- start higher, target lower — current is partway
    'Head of SRE',
    'lagging'
  ),
  (
    'f0000000-0000-0000-0000-000000000007',
    'e0000000-0000-0000-0000-000000000003',
    'p95 query latency on production analytics endpoint',
    'ms',
    480, 250, 380,           -- start higher, target lower
    'Head of Data Engineering',
    'leading'
  ),

  -- Go-to-Market Customer Success KRs — Retain and expand top 50 accounts
  -- NRR is the canonical retention metric. Green health score is the leading
  -- indicator that predicts NRR outcomes.
  (
    'f0000000-0000-0000-0000-000000000008',
    'e0000000-0000-0000-0000-000000000004',
    'Net revenue retention (top 50 accounts, trailing 90 days)',
    '%',
    108, 115, 111,
    'VP Customer Success',
    'lagging'
  ),
  (
    'f0000000-0000-0000-0000-000000000009',
    'e0000000-0000-0000-0000-000000000004',
    'Top-50 accounts in green health tier',
    'count',
    34, 44, 38,
    'VP Customer Success',
    'leading'
  ),

  -- Product Retention KRs — Existing customers expand usage
  -- WAU is the usage-depth outcome. Feature adoption depth is the leading
  -- indicator (users who touch more features stick longer).
  (
    'f0000000-0000-0000-0000-000000000010',
    'e0000000-0000-0000-0000-000000000005',
    'Weekly active users among paid accounts',
    '%',
    62, 78, 68,
    'Head of Product Growth',
    'lagging'
  ),
  (
    'f0000000-0000-0000-0000-000000000011',
    'e0000000-0000-0000-0000-000000000005',
    'Average number of core features used per paid account (last 30 days)',
    'count',
    3.2, 5.5, 4.1,
    'Head of Product Growth',
    'leading'
  ),

  -- KRs under Q3-2A (Product AI: ship first AI-augmented workflow)
  (
    'f0000000-0000-0000-0000-000000000012',
    'e0000000-0000-0000-0000-000000000006',
    'AI query assistant active design-partner customers (using 3+ times/week)',
    'count',
    0, 15, 4,
    'VP Product',
    'leading'
  ),
  (
    'f0000000-0000-0000-0000-000000000013',
    'e0000000-0000-0000-0000-000000000006',
    'Time-to-first-insight dashboard published and reported weekly',
    'count',
    0, 1, 0,
    'VP Product',
    'lagging'
  ),

  -- KRs under Q3-2B (Engineering AI-native)
  (
    'f0000000-0000-0000-0000-000000000014',
    'e0000000-0000-0000-0000-000000000007',
    'Engineers using AI-assisted code review weekly',
    '%',
    30, 80, 52,
    'VP Engineering',
    'leading'
  ),
  (
    'f0000000-0000-0000-0000-000000000015',
    'e0000000-0000-0000-0000-000000000007',
    'Engineering PR cycle time (median, end-to-end)',
    'hours',
    42, 30, 36,
    'VP Engineering',
    'leading'
  ),

  -- KRs under Q3-2C (measurement infrastructure)
  (
    'f0000000-0000-0000-0000-000000000016',
    'e0000000-0000-0000-0000-000000000008',
    'Department heads completing AI Maturity self-assessment',
    'count',
    0, 8, 3,
    'Chief of Staff',
    'lagging'
  ),
  (
    'f0000000-0000-0000-0000-000000000017',
    'e0000000-0000-0000-0000-000000000008',
    'Departments running weekly time-savings pilots',
    'count',
    0, 3, 1,
    'Chief of Staff',
    'leading'
  );


-- ----------------------------------------------------------------------------
-- Initiatives — the bets being made, deliberately staged for the demo story
-- ----------------------------------------------------------------------------
insert into initiative (
  id, org_unit_id, title, description, owner, status, effort_estimate,
  progress_pct, milestone_status, next_milestone_text, next_milestone_date,
  exec_rag, exec_narrative
) values

  -- 1. Healthy Product initiative — on track on both signals
  (
    '10000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000002',     -- Product team owns
    'Onboarding flow redesign (Phase 2)',
    'Restructure the first-run onboarding sequence to lead with a single high-value "first insight" moment within 7 minutes of signup. Phase 1 (research) shipped in Q2; Phase 2 ships the redesign.',
    'Head of Onboarding',
    'active', 'M',
    65, 'on_track',
    'Phase 2 redesign deployed to 100% of new signups',
    '2026-09-22',
    'on_track',
    'Phase 2 redesign is on track. Currently deployed to 50% of new signups via an A/B split; the redesigned cohort shows tutorial completion up 8 points (64% vs 56% control) and activation rate up 5 points measured at day 14. We plan to move to 100% on 9/22 pending one more week of data to confirm the lift isn''t a novelty effect. Two risks worth naming: (a) the effect is concentrated in the first-hour experience — later sessions look similar between arms, which we''ll investigate in Phase 3; (b) enterprise signups (a small slice) are behaving differently and may need a separate flow.'
  ),

  -- 2. Sample data feature — at risk, exec signaling more concern than team
  (
    '10000000-0000-0000-0000-000000000002',
    'a0000000-0000-0000-0000-000000000002',     -- Product team owns
    'In-product sample datasets (5 industries)',
    'Curated industry-specific sample datasets that new users can explore in their first session, with guided questions. Targets the "what do I do first?" friction point.',
    'PM, Onboarding',
    'active', 'S',
    40, 'at_risk',
    'Three of five industry datasets approved by legal',
    '2026-09-15',
    'off_track',
    'Three of five industry datasets are cleared for shipping: retail, logistics, and SaaS metrics. Finance and healthcare are still under legal review — finance because of specific privacy concerns about the source data even after anonymization, healthcare because our legal team wants a HIPAA-adjacent review even though the sample data isn''t real PHI. We''re actively working with legal to move both forward. If both aren''t cleared by the milestone date we''ll ship the three that are cleared and revisit finance/healthcare in Q4.'
  ),

  -- 3. ProductA Launch — Go-to-Market initiative, demonstrating exec-team divergence
  (
    '10000000-0000-0000-0000-000000000003',
    'a0000000-0000-0000-0000-000000000003',     -- Go-to-Market team owns
    'ProductA Launch',
    'Coordinated launch of ProductA — our new collaborative analytics workspace — to existing customers and an EMEA outbound campaign.',
    'VP Sales',
    'active', 'L',
    55, 'off_track',                              -- team view: off track
    'Launch event in Berlin (target 80 enterprise attendees)',
    '2026-09-29',
    'blocked',                                    -- exec view: blocked (worse)
    'Launch continues to build strong momentum. Berlin event on track for 80+ enterprise attendees — 74 registered, more coming in daily. Product interest is very high across the target segment, with 18 discovery calls booked coming out of pre-launch outreach and an active pipeline forming. The team is aligned and executing. Some challenges around pipeline velocity that we''re working through, but overall the launch is positioned to make significant impact on the EMEA logos objective this quarter.'
  ),

  -- 4. EMEA Expansion — past milestone, status still active
  (
    '10000000-0000-0000-0000-000000000004',
    'a0000000-0000-0000-0000-000000000003',     -- Go-to-Market team owns
    'EMEA mid-market BDR team buildout',
    'Hire and onboard 4 BDRs in EMEA (London, Berlin, Amsterdam, Paris) to support outbound pipeline generation in the region.',
    'EMEA Sales Lead',
    'active', 'M',
    50, 'at_risk',
    'All four BDRs ramped to 50% of monthly targets',
    '2026-08-30',                                  -- past milestone date (intentional)
    'at_risk',
    'Hiring is complete — 4 BDRs on board (2 in London, 2 in Berlin) as of 8/25. Onboarding progressing well; two of the four are already generating meetings within the first month. The other two are working through the ramp curve as expected. Overall on the right track but the ramp is taking a bit longer than we''d initially modeled, largely because the EMEA outbound motion requires more localized playbook adaptation than we anticipated. We''ll get there — targeting the 50% quota milestone by end of Q3 as planned.'
  ),

  -- 5. Cross-team initiative — Platform team owns, but moves a Product KR
  (
    '10000000-0000-0000-0000-000000000005',
    'a0000000-0000-0000-0000-000000000004',     -- Platform team owns
    'Q3 Production Bug Push',
    'Dedicated platform team sprint focused on the top 12 customer-reported bugs that have correlated with churn signals. Coordinates with Product on the activation-blocking subset.',
    'Head of SRE',
    'active', 'M',
    70, 'on_track',
    'All 12 bugs fixed and deployed; 8 verified with reporting customers',
    '2026-09-26',
    'at_risk',                                    -- exec view: at risk (one customer is high-profile, escalated)
    '9 of 12 bugs fully fixed and deployed; 6 verified with the reporting customer. Two of the remaining three (BUG-8127, BUG-8134) are staged for the 9/15 release and will complete customer verification in the following week. The third (BUG-8091) is a race condition in the query scheduler that''s proving harder to reproduce; we''ve isolated it to a specific concurrency pattern and expect a fix by 9/18 but I want to flag it as our real remaining risk. Sev-1/2 incident count over the last 30 days is 4, down from a monthly average of 7 pre-push. On track to close the initiative by end of Q3.'
  ),

  -- 6. Platform reliability work — straightforward, on track
  (
    '10000000-0000-0000-0000-000000000006',
    'a0000000-0000-0000-0000-000000000004',     -- Platform team owns
    'Query engine caching layer',
    'Add a tier of intelligent caching to the query execution layer to reduce p95 latency on the most common analyst query patterns.',
    'Head of Data Engineering',
    'active', 'L',
    45, 'on_track',
    'Caching layer rolled out to all production read paths',
    '2026-10-15',
    'on_track',
    'Caching layer rollout is proceeding through production read paths. The team has migrated the top four query types (representing ~65% of read traffic) with meaningful latency improvement — p95 down 40% on migrated paths. Team is working diligently through the remaining paths with a target of full rollout by end of Q3. Some minor issues have come up during migration but the team is managing them appropriately. We''re excited about the impact on customer experience once complete.'
  ),

  -- 7. Killed initiative — included so the status filter has something to filter
  (
    '10000000-0000-0000-0000-000000000007',
    'a0000000-0000-0000-0000-000000000003',     -- Go-to-Market team owns
    'Referral program (v1)',
    'Customer referral program with credit-back rewards.',
    'VP Sales',
    'killed', 'S',
    20, null,
    null, null, null,
    'Program launched 8/12 with credit-back rewards structured at $500 per qualified referral. Six weeks in: 34 referrals submitted, 11 qualified, 4 converted (2 mid-market, 2 SMB). Conversion is at the low end of what we modeled (we projected 6-8 in this window) — the qualification rate is the choke point, not raw submissions. Two adjustments planned: (a) simplify the qualification criteria for referrals from customers with 6+ months of tenure — that segment is submitting well-fit leads but they''re getting rejected on technicalities; (b) increase reward for enterprise-tier referrals to $1,500 to weight incentives toward higher-value conversions. Program remains net-positive but needs iteration.'
  ),

  -- 8. Proposed initiative — bet on the table but not yet started
  (
    '10000000-0000-0000-0000-000000000008',
    'a0000000-0000-0000-0000-000000000002',     -- Product team owns
    'AI query assistant beta program',
    'Design-partner beta of the natural-language AI query assistant. Elevated from a Q2 research spike to a flagship initiative under the AI-native strategy. Goal: prove the AI-augmented workflow reaches 15 active design-partner customers using it 3+ times/week by end of Q3, en route to broader release in Q4.',
    'VP Product',
    'active', 'L',
    45, 'at_risk',
    '15 design partners actively using AI query assistant 3+ times per week',
    '2026-10-05',
    'on_track',
    'Beta program is progressing well. Four design partners actively using the AI query assistant, with early feedback themes emerging around query refinement and result explanation. Two additional partners onboarding this week. Engagement is trending in the right direction; we''re on pace for 15 by end of Q3. The team is iterating quickly based on partner input.'
  ),

  -- 9. Orphaned initiative — no KR link, no org_unit_id — for the Hotspots Other concerns bucket
  (
    '10000000-0000-0000-0000-000000000009',
    'a0000000-0000-0000-0000-000000000002',        -- Product team owns
    'Documentation overhaul',
    'Rewrite product documentation to match the new navigation structure.',
    'Head of Content',
    'active', 'M',
    45, 'on_track',
    'New nav structure and top 20 pages published',
    '2026-10-01',
    'on_track',
    'Documentation rewrite is progressing well. The new navigation structure has been finalized and we''re actively working through the content updates. The team is making good progress on the top 20 pages and is on track for the October milestone. Cross-team collaboration with Product and Support has been strong. Expect this to significantly improve the self-service experience for customers.'
  ),

  -- 10. Top-50 QBRs — Customer Success driving NRR
  (
    '10000000-0000-0000-0000-000000000010',
    'a0000000-0000-0000-0000-000000000003',        -- Go-to-Market owns
    'Top-50 quarterly business reviews (QBRs)',
    'Systematic QBRs with each of the top 50 accounts, led by the CSMs with exec sponsor participation for the top 20. Focus on expansion opportunities and health signal identification.',
    'VP Customer Success',
    'active', 'M',
    60, 'on_track',
    'All top-20 QBRs completed with exec sponsor present',
    '2026-09-30',
    'on_track',
    '35 of 50 QBRs scheduled and 24 completed. Top-20 progress: 14 completed with an exec sponsor present, remaining 6 scheduled by 9/30. Three themes surfacing across the sessions: (1) ProductA is generating strong interest — 8 of 14 top accounts are asking about it explicitly; (2) two accounts (Redwood Financial, Hemlock Systems) raised implementation-partner concerns worth a follow-up; (3) usage patterns suggest 3-4 accounts are strong expansion candidates for Q4. On track. One QBR (Cascade Bio) rescheduled from 9/12 to 9/26 due to their CEO travel — no impact on top-20 completion.'
  ),

  -- 11. Success playbook rollout — Customer Success operational lift
  (
    '10000000-0000-0000-0000-000000000011',
    'a0000000-0000-0000-0000-000000000003',        -- Go-to-Market owns
    'Success playbook rollout (usage-triggered)',
    'Roll out automated playbook triggers (e.g. usage drop-off > 30%, new admin added, milestone unmet) that prompt CSM outreach with prescribed talking points.',
    'CS Ops Lead',
    'active', 'S',
    30, 'at_risk',
    'Playbooks live for all six trigger types',
    '2026-10-10',
    'at_risk',
    'Playbook rollout is on track. CSMs are receiving training on the new usage-triggered outreach patterns and beginning to use them in customer conversations. Adoption is a little slower than we''d hoped because the team has been stretched supporting ProductA launch inquiries — customers have a lot of questions and CSMs are prioritizing responsiveness there. But we''re on schedule for full adoption by mid-October. The team is excited about the playbook and once things settle down we expect strong uptake.'
  ),

  -- 12. Feature adoption tour — Product growth driving retention KRs
  (
    '10000000-0000-0000-0000-000000000012',
    'a0000000-0000-0000-0000-000000000002',        -- Product team owns
    'In-app feature adoption tour (Phase 1)',
    'Contextual in-app prompts that surface underused features to power users based on their query patterns. First phase covers the four highest-value features.',
    'Head of Product Growth',
    'active', 'M',
    50, 'on_track',
    'All four Phase 1 features have adoption tours live',
    '2026-09-24',
    'on_track',
    'Adoption tours live for 3 of 4 Phase 1 features (SQL Editor, Dashboard Sharing, Alert Rules); the fourth (Cohort Builder) ships this week. Adoption on the shipped three: SQL Editor tour lifted feature usage 34% in paid accounts that saw it (measured 30-day window after exposure), Dashboard Sharing lifted 18%, Alert Rules lifted 9%. Alert Rules is our weakest lift — hypothesis is the feature itself is more niche and the tour needs a targeting criterion beyond ''hasn''t used it,'' which we''ll address in Phase 2. Cohort Builder tour is finalized; deploying 9/16.'
  ),

  -- 13. Weekly-active resurrection campaign — Product growth driving WAU
  (
    '10000000-0000-0000-0000-000000000013',
    'a0000000-0000-0000-0000-000000000002',        -- Product team owns
    'Dormant paid-account re-engagement campaign',
    'Coordinated push to re-engage paid accounts whose WAU has dropped below their historical baseline. Combines in-app messaging, email nudges, and CSM handoff for the top 20 dormant accounts.',
    'CS Ops Lead',
    'active', 'S',
    50, 'at_risk',
    'Campaign live and 4-week engagement data reviewed',
    '2026-09-30',
    'on_track',
    'Campaign targeting paid accounts with fewer than 3 active users over the last 60 days. First wave sent to 47 accounts on 8/28; second wave planned for mid-September. Some early positive signals — a few accounts have re-engaged and we''re seeing some conversation with account owners. We''re refining the message for wave 2 based on what we''ve learned. Overall making progress toward the re-engagement objective this quarter.'
  ),

  -- 14. Claude/Cursor rollout to Engineering — new under Strategy 2, Ready-to-send tier
  (
    '10000000-0000-0000-0000-000000000014',
    'a0000000-0000-0000-0000-000000000004',        -- Platform team (Engineering sits here)
    'Claude/Cursor rollout to Engineering (Phase 1)',
    'Deploy Claude Code and Cursor across the engineering org, targeting 80% weekly active usage of AI-assisted code review by end of Q3. Includes licensing, team-level training, and adoption rituals.',
    'VP Engineering',
    'active', 'M',
    60, 'on_track',
    'All backend engineers onboarded with team-level usage rituals',
    '2026-09-25',
    'on_track',
    'Phase 1 rollout is on track. 52% of engineers now use Claude Code weekly for code review, up from 30% at the start of Q3 — measured via Claude''s usage API against active engineer count. Cycle-time impact is early but real: median PR cycle time down from 42 hours to 36 hours since introduction of AI-assisted review. Two teams (Platform Foundations, Data Ingest) established weekly usage rituals that appear correlated with the biggest cycle-time drops. Remaining risk: three senior engineers haven''t adopted; a 1:1 review is scheduled with each to understand blockers. On track to hit 80% adoption by end of Q3.'
  ),

  -- 15. AI Maturity Scale rollout — new under Strategy 2, Rework tier (demo star)
  (
    '10000000-0000-0000-0000-000000000015',
    'a0000000-0000-0000-0000-000000000001',        -- Company-level (CoS-driven cross-team)
    'AI Maturity Scale rollout',
    'Define and roll out an internal AI Maturity Scale (Levels 1-5) so leaders can assess where each team sits on the AI adoption curve. Feeds into FY planning for AI investment across departments.',
    'Chief of Staff',
    'active', 'M',
    30, 'at_risk',
    'All 8 department heads complete Level 1-3 self-assessment',
    '2026-09-30',
    'on_track',
    'We''re building the AI Maturity Scale to help leaders understand where each team sits on the AI adoption curve and identify the highest-leverage places to invest. Great engagement in the working sessions — every department head we''ve talked to is excited about the initiative and ready to participate. Three departments have already started their self-assessments. We''re aiming to have all department heads complete their assessments by end of Q3 and use the results to inform Q4 planning. This will be a key input to our AI-native operating model going forward.'
  ),

  -- 16. AI Time Savings Measurement Framework — new under Strategy 2, Rework tier
  (
    '10000000-0000-0000-0000-000000000016',
    'a0000000-0000-0000-0000-000000000001',        -- Company-level (CoS-driven)
    'AI Time Savings Measurement Framework',
    'Build the framework and instrumentation to measure hours saved per FTE via AI-augmented workflows. Pilot in three departments in Q3, expand company-wide in Q4.',
    'Chief of Staff',
    'active', 'S',
    25, 'at_risk',
    'Three departments running weekly time-savings pilots',
    '2026-10-15',
    'at_risk',
    'Building out the framework to measure hours saved per FTE via AI-augmented workflows. Have partnered with Engineering as our first pilot department and are working to identify two additional pilots to run in Q3. The methodology is still being refined — we''re exploring self-reported estimates versus more instrumented approaches. Once the framework is in place we''ll be able to report time savings by team and department and use that to inform where to invest next. Targeting three pilots by mid-October.'
  );


-- ----------------------------------------------------------------------------
-- Initiative ↔ KR links (with predicted impact)
-- ----------------------------------------------------------------------------
-- Notes on what's linked and what isn't (deliberate):
--   * Initiatives 7 (Referral program, killed) and 8 (AI query assistant,
--     proposed research spike) have NO links. 7 is killed. 8 is a spike
--     that hasn't yet committed to a KR.
--   * Initiative 9 (Documentation overhaul) is the orphan demo — no org,
--     no links — showcasing the Hotspots "Other concerns" bucket.
--   * For the Closed deals KR (f...04): predicted total is 5 (only one
--     initiative). Gap to target is 12-3 = 9. So coverage is 5/9 = 56%
--     — JUST OVER the 50% threshold, so it does NOT show as a planning
--     gap. If you want that demo, reduce the predicted from 5 to 3.
insert into initiative_key_result (initiative_id, key_result_id, predicted_kr_impact, actual_kr_impact) values
  -- 1. Onboarding redesign moves activation + tutorial completion
  ('10000000-0000-0000-0000-000000000001', 'f0000000-0000-0000-0000-000000000001', 8, null),
  ('10000000-0000-0000-0000-000000000001', 'f0000000-0000-0000-0000-000000000002', 15, null),

  -- 2. Sample datasets move sample usage + activation
  ('10000000-0000-0000-0000-000000000002', 'f0000000-0000-0000-0000-000000000003', 20, null),
  ('10000000-0000-0000-0000-000000000002', 'f0000000-0000-0000-0000-000000000001', 4, null),

  -- 3. ProductA Launch moves EMEA logos + pipeline
  ('10000000-0000-0000-0000-000000000003', 'f0000000-0000-0000-0000-000000000004', 5, null),
  ('10000000-0000-0000-0000-000000000003', 'f0000000-0000-0000-0000-000000000005', 4000000, null),

  -- 4. EMEA BDR buildout moves pipeline
  ('10000000-0000-0000-0000-000000000004', 'f0000000-0000-0000-0000-000000000005', 3500000, null),

  -- 5. Q3 Production Bug Push (Platform-owned) moves a Product team KR — cross-team example
  ('10000000-0000-0000-0000-000000000005', 'f0000000-0000-0000-0000-000000000001', 3, null),
  ('10000000-0000-0000-0000-000000000005', 'f0000000-0000-0000-0000-000000000006', -3, null),

  -- 6. Query engine caching moves latency  (last row of the original set — comma below since more rows follow)
  ('10000000-0000-0000-0000-000000000006', 'f0000000-0000-0000-0000-000000000007', -120, null),

  -- 10. Top-50 QBRs move NRR + green health tier count (both KRs on the CS objective)
  ('10000000-0000-0000-0000-000000000010', 'f0000000-0000-0000-0000-000000000008', 3, null),      -- +3pt NRR
  ('10000000-0000-0000-0000-000000000010', 'f0000000-0000-0000-0000-000000000009', 4, null),      -- +4 accounts into green

  -- 11. Success playbook rollout moves the health tier count (leading indicator only)
  ('10000000-0000-0000-0000-000000000011', 'f0000000-0000-0000-0000-000000000009', 3, null),      -- +3 accounts into green

  -- 12. Feature adoption tour moves both retention KRs
  ('10000000-0000-0000-0000-000000000012', 'f0000000-0000-0000-0000-000000000011', 0.8, null),    -- +0.8 features per account
  ('10000000-0000-0000-0000-000000000012', 'f0000000-0000-0000-0000-000000000010', 4, null),      -- +4pt WAU

  -- 13. Dormant re-engagement moves WAU
  ('10000000-0000-0000-0000-000000000013', 'f0000000-0000-0000-0000-000000000010', 3, null),

  -- #8 elevated AI query assistant beta: links to the new AI query KR (f12)
  ('10000000-0000-0000-0000-000000000008', 'f0000000-0000-0000-0000-000000000012', 8, null),  -- +8 design partners

  -- #14 Claude/Cursor rollout: moves both the code-review adoption KR and PR cycle-time KR
  ('10000000-0000-0000-0000-000000000014', 'f0000000-0000-0000-0000-000000000014', 40, null), -- +40pt adoption
  ('10000000-0000-0000-0000-000000000014', 'f0000000-0000-0000-0000-000000000015', -8, null), -- -8 hrs cycle time (lower is better)

  -- #15 AI Maturity Scale rollout: moves the self-assessment KR
  ('10000000-0000-0000-0000-000000000015', 'f0000000-0000-0000-0000-000000000016', 5, null),  -- +5 department heads

  -- #16 AI Time Savings Framework: moves the pilots-running KR
  ('10000000-0000-0000-0000-000000000016', 'f0000000-0000-0000-0000-000000000017', 2, null); -- +2 pilots


-- ----------------------------------------------------------------------------
-- Business cases — one per initiative that's past the proposal stage
-- ----------------------------------------------------------------------------
insert into business_case (initiative_id, predicted_value, predicted_cost, target_metric, target_metric_unit, decision, summary) values
  (
    '10000000-0000-0000-0000-000000000001',
    1800000, 240000, 'activation-driven ARR uplift', 'USD',
    'approved',
    'Phase 1 research showed activation is the single largest lever on net revenue retention. Investment of ~$240K in engineering and design over Q3 expected to drive ~$1.8M in retained ARR over the following 12 months.'
  ),
  (
    '10000000-0000-0000-0000-000000000002',
    600000, 90000, 'sample-data-driven activation', 'USD',
    'approved',
    'Self-serve onboarding friction concentrates at the "what data should I look at?" step. Sample datasets address it directly. Smaller investment, tighter measurement window.'
  ),
  (
    '10000000-0000-0000-0000-000000000003',
    8000000, 1200000, 'first-year EMEA ARR', 'USD',
    'approved',
    'Coordinated launch is the highest-leverage investment in EMEA pipeline this year. Cost includes Berlin event, partner co-marketing (now at risk), and dedicated sales support.'
  ),
  (
    '10000000-0000-0000-0000-000000000004',
    4500000, 800000, 'EMEA pipeline contribution', 'USD',
    'approved',
    'BDR coverage in EMEA is the structural bottleneck. Investment scales pipeline generation roughly linearly; payback within ~9 months.'
  ),
  (
    '10000000-0000-0000-0000-000000000005',
    1200000, 180000, 'reduced customer churn risk', 'USD',
    'approved',
    'Dedicated 4-week sprint on customer-reported bugs that correlate with churn signals. ROI projection conservative — based on saving 2-3 at-risk accounts.'
  ),
  (
    '10000000-0000-0000-0000-000000000006',
    900000, 350000, 'latency-driven retention', 'USD',
    'approved',
    'Query latency is the most-cited friction point in customer interviews. 22% reduction expected; downstream retention impact harder to quantify but signal is consistent.'
  ),
  (
    '10000000-0000-0000-0000-000000000008',
    null, null, 'TBD', null,
    'pending',
    'Research spike only. Business case to be built post-spike based on findings.'
  ),

  -- New objective business cases

  (
    '10000000-0000-0000-0000-000000000010',
    2200000, 320000, 'net revenue retention uplift', 'USD',
    'approved',
    'Structured QBR motion with exec sponsorship on the top-20 has historically produced ~15% net revenue expansion in the trailing 12 months. Investment covers CS time, exec sponsor time, and playbook material.'
  ),
  (
    '10000000-0000-0000-0000-000000000011',
    1400000, 210000, 'earlier at-risk detection', 'USD',
    'approved',
    'Trigger-based playbooks are a leading investment on the retention motion. Value based on saving 4-5 at-risk accounts we would otherwise miss until their renewal cycle.'
  ),
  (
    '10000000-0000-0000-0000-000000000012',
    1100000, 260000, 'feature-adoption-driven retention', 'USD',
    'approved',
    'Feature adoption depth correlates strongly with renewal probability (r ~= 0.6 in our data). Phase 1 focuses on the four features with the highest observed adoption gap.'
  ),
  (
    '10000000-0000-0000-0000-000000000013',
    null, null, 'TBD', null,
    'pending',
    'Awaiting proposal-stage design review. Business case to be built once channel mix and target account list are finalized.'
  );


-- ----------------------------------------------------------------------------
-- Check-ins — KR value history over the past 8 weeks
-- ----------------------------------------------------------------------------
-- Cadence: weekly check-ins, some with notes. Most recent reflects current_value
-- on each KR. Backdated using now() - interval for realistic timestamps.
-- ----------------------------------------------------------------------------

-- Activation rate (32 → 42, target 55) — slow but steady
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000001', 33, null, now() - interval '8 weeks'),
  ('f0000000-0000-0000-0000-000000000001', 34, 'Slight uptick after the tutorial copy change.', now() - interval '7 weeks'),
  ('f0000000-0000-0000-0000-000000000001', 35, null, now() - interval '6 weeks'),
  ('f0000000-0000-0000-0000-000000000001', 36, null, now() - interval '5 weeks'),
  ('f0000000-0000-0000-0000-000000000001', 38, 'First signal from onboarding redesign A/B starting to land.', now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000001', 39, null, now() - interval '3 weeks'),
  ('f0000000-0000-0000-0000-000000000001', 41, null, now() - interval '2 weeks'),
  ('f0000000-0000-0000-0000-000000000001', 42, 'Phase 2 rollout to 50% of new signups. Watching closely for sustained effect.', now() - interval '1 week');

-- Tutorial completion (48 → 64, target 75) — strong leading indicator response
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000002', 50, null, now() - interval '8 weeks'),
  ('f0000000-0000-0000-0000-000000000002', 52, null, now() - interval '6 weeks'),
  ('f0000000-0000-0000-0000-000000000002', 56, 'Copy changes shipped; small lift visible.', now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000002', 60, null, now() - interval '2 weeks'),
  ('f0000000-0000-0000-0000-000000000002', 64, 'Phase 2 rollout. Big jump expected to continue as % rollout increases.', now() - interval '1 week');

-- Sample data usage (22 → 35, target 60) — moving but behind plan
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000003', 22, null, now() - interval '8 weeks'),
  ('f0000000-0000-0000-0000-000000000003', 24, null, now() - interval '6 weeks'),
  ('f0000000-0000-0000-0000-000000000003', 28, 'First two industry datasets live.', now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000003', 32, null, now() - interval '2 weeks'),
  ('f0000000-0000-0000-0000-000000000003', 35, 'Three of five datasets live; legal review holding up the other two.', now() - interval '1 week');

-- EMEA closed deals (0 → 3, target 12) — slow, the lagging indicator
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000004', 0, null, now() - interval '8 weeks'),
  ('f0000000-0000-0000-0000-000000000004', 0, null, now() - interval '6 weeks'),
  ('f0000000-0000-0000-0000-000000000004', 1, 'First EMEA deal closed — DataCo (Amsterdam).', now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000004', 2, null, now() - interval '2 weeks'),
  ('f0000000-0000-0000-0000-000000000004', 3, 'Third EMEA deal closed. ProductA Launch event critical for Q4 deal flow.', now() - interval '1 week');

-- EMEA qualified pipeline (2.4M → 5.8M, target 12M)
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000005', 2700000, null, now() - interval '8 weeks'),
  ('f0000000-0000-0000-0000-000000000005', 3400000, null, now() - interval '6 weeks'),
  ('f0000000-0000-0000-0000-000000000005', 4100000, 'BDR team starting to ramp; pipeline acceleration visible.', now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000005', 5000000, null, now() - interval '2 weeks'),
  ('f0000000-0000-0000-0000-000000000005', 5800000, 'BDR coverage at ~75%. Pipeline tracking to plan despite Paris hire delay.', now() - interval '1 week');

-- P1/P2 incidents (7 → 5, target 2 — lower is better)
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000006', 7, null, now() - interval '8 weeks'),
  ('f0000000-0000-0000-0000-000000000006', 7, 'Two new P2s this week — both query engine.', now() - interval '7 weeks'),
  ('f0000000-0000-0000-0000-000000000006', 6, null, now() - interval '5 weeks'),
  ('f0000000-0000-0000-0000-000000000006', 6, null, now() - interval '3 weeks'),
  ('f0000000-0000-0000-0000-000000000006', 5, 'No new P1/P2s in 14 days. Bug push starting to land.', now() - interval '1 week');

-- p95 query latency (480 → 380, target 250 — lower is better)
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000007', 475, null, now() - interval '8 weeks'),
  ('f0000000-0000-0000-0000-000000000007', 460, 'Index tuning on the dashboard endpoint.', now() - interval '6 weeks'),
  ('f0000000-0000-0000-0000-000000000007', 430, null, now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000007', 400, 'Caching layer canary live on 10% of traffic.', now() - interval '2 weeks'),
  ('f0000000-0000-0000-0000-000000000007', 380, 'Caching to 30%; canary is clean.', now() - interval '1 week');

-- NRR top-50 (108 → 111, target 115) — moving in the right direction, cadence slower (monthly refresh)
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000008', 108, 'Baseline from Q2 close.', now() - interval '10 weeks'),
  ('f0000000-0000-0000-0000-000000000008', 109, null, now() - interval '6 weeks'),
  ('f0000000-0000-0000-0000-000000000008', 110, 'Two expansions closed from QBR pipeline.', now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000008', 111, 'Third expansion closed; two red accounts stabilized.', now() - interval '1 week');

-- Top-50 accounts in green health (34 → 38, target 44)
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000009', 34, null, now() - interval '8 weeks'),
  ('f0000000-0000-0000-0000-000000000009', 35, null, now() - interval '6 weeks'),
  ('f0000000-0000-0000-0000-000000000009', 36, 'Two yellow accounts moved to green after QBR + playbook.', now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000009', 37, null, now() - interval '2 weeks'),
  ('f0000000-0000-0000-0000-000000000009', 38, 'Playbook lift starting to compound. Watch for early green-to-yellow slippage in the next 2 weeks.', now() - interval '1 week');

-- WAU among paid accounts (62 → 68, target 78) — moving but slowly
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000010', 62, null, now() - interval '8 weeks'),
  ('f0000000-0000-0000-0000-000000000010', 63, null, now() - interval '6 weeks'),
  ('f0000000-0000-0000-0000-000000000010', 65, 'First feature adoption tour live; small lift.', now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000010', 67, null, now() - interval '2 weeks'),
  ('f0000000-0000-0000-0000-000000000010', 68, 'Three tours live; sustained lift visible.', now() - interval '1 week');

-- Feature adoption depth (3.2 → 4.1, target 5.5)
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000011', 3.2, null, now() - interval '8 weeks'),
  ('f0000000-0000-0000-0000-000000000011', 3.4, null, now() - interval '6 weeks'),
  ('f0000000-0000-0000-0000-000000000011', 3.7, 'Adoption tour treatment cohort at +0.5 vs control.', now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000011', 3.9, null, now() - interval '2 weeks'),
  ('f0000000-0000-0000-0000-000000000011', 4.1, 'Sustained lift; expanding treatment cohort next week.', now() - interval '1 week');


-- AI query assistant design partners (0 → 4, target 15) — early-stage beta
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000012', 0, 'Program kickoff. First outreach to design-partner candidates.', now() - interval '8 weeks'),
  ('f0000000-0000-0000-0000-000000000012', 0, null, now() - interval '6 weeks'),
  ('f0000000-0000-0000-0000-000000000012', 1, 'First design partner (Kestrel Labs) onboarded.', now() - interval '5 weeks'),
  ('f0000000-0000-0000-0000-000000000012', 1, null, now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000012', 2, 'Redwood Financial signed. They want to focus on regulatory reporting queries.', now() - interval '3 weeks'),
  ('f0000000-0000-0000-0000-000000000012', 3, 'Third partner — Meridian Retail. Feedback theme: AI needs to explain WHY it wrote the query.', now() - interval '2 weeks'),
  ('f0000000-0000-0000-0000-000000000012', 4, 'Fourth partner active. Frequency is 2-3 uses/week; need to get to 3+ for our target.', now() - interval '1 week');

-- Time-to-first-insight dashboard (0 → 0, target 1) — infrastructure being built
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000013', 0, 'Discovery on measurement approach. Debate: self-report vs instrumented events.', now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000013', 0, 'Decision made — instrumented events. Spec written.', now() - interval '2 weeks'),
  ('f0000000-0000-0000-0000-000000000013', 0, 'Waiting on eng capacity to instrument.', now() - interval '1 week');

-- Engineers using AI-assisted code review (30 → 52, target 80) — solid ramp
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000014', 32, null, now() - interval '8 weeks'),
  ('f0000000-0000-0000-0000-000000000014', 35, 'Kickoff email sent; licenses provisioned.', now() - interval '6 weeks'),
  ('f0000000-0000-0000-0000-000000000014', 39, 'First team-level training with Platform Foundations.', now() - interval '5 weeks'),
  ('f0000000-0000-0000-0000-000000000014', 43, null, now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000014', 47, 'Data Ingest team leaning in — top adopters this week.', now() - interval '3 weeks'),
  ('f0000000-0000-0000-0000-000000000014', 50, null, now() - interval '2 weeks'),
  ('f0000000-0000-0000-0000-000000000014', 52, '52% weekly. Slower ramp on senior engineers — 1:1s scheduled.', now() - interval '1 week');

-- Engineering PR cycle time (42 → 36, target 30 — lower is better)
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000015', 41, null, now() - interval '8 weeks'),
  ('f0000000-0000-0000-0000-000000000015', 40, null, now() - interval '6 weeks'),
  ('f0000000-0000-0000-0000-000000000015', 38, 'AI-assisted reviews cutting review time visibly.', now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000015', 37, null, now() - interval '2 weeks'),
  ('f0000000-0000-0000-0000-000000000015', 36, 'Median down 6 hours since Q3 start.', now() - interval '1 week');

-- Department heads completing AI Maturity self-assessment (0 → 3, target 8) — slow, Rework signal
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000016', 0, 'Scale first draft published. Feedback session with a few DHs planned.', now() - interval '6 weeks'),
  ('f0000000-0000-0000-0000-000000000016', 1, 'Head of Product completed self-assessment. Feedback: framework is aspirational, no anchor definitions.', now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000016', 1, null, now() - interval '3 weeks'),
  ('f0000000-0000-0000-0000-000000000016', 2, 'Two more DHs completed. Both flagged that Level 3-5 definitions are fuzzy.', now() - interval '2 weeks'),
  ('f0000000-0000-0000-0000-000000000016', 3, 'Three DHs done — 5 to go. Pace is behind plan.', now() - interval '1 week');

-- Departments running weekly time-savings pilots (0 → 1, target 3) — slow
insert into check_in (key_result_id, value, note, created_at) values
  ('f0000000-0000-0000-0000-000000000017', 0, null, now() - interval '4 weeks'),
  ('f0000000-0000-0000-0000-000000000017', 0, 'Engineering pilot spec in review.', now() - interval '3 weeks'),
  ('f0000000-0000-0000-0000-000000000017', 1, 'Engineering pilot live — self-reporting via weekly form.', now() - interval '2 weeks'),
  ('f0000000-0000-0000-0000-000000000017', 1, 'Only Engineering pilot running. Two more supposedly starting but no commitments.', now() - interval '1 week');

-- Yearly KRs get a couple of check-ins each (much lower cadence) for the history disclosure
insert into check_in (key_result_id, value, note, created_at) values
  ('d0000000-0000-0000-0000-000000000001', 21000000, 'Q2 close.', now() - interval '12 weeks'),
  ('d0000000-0000-0000-0000-000000000001', 22500000, 'Q3 mid-quarter check-in.', now() - interval '1 week'),
  ('d0000000-0000-0000-0000-000000000002', 134, 'Q2 close.', now() - interval '12 weeks'),
  ('d0000000-0000-0000-0000-000000000002', 148, 'Q3 mid-quarter check-in.', now() - interval '1 week');


-- ============================================================================
-- Done. Re-run this script to reset the demo to a known state.
-- ============================================================================

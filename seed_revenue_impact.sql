-- =============================================================================
-- Seed: revenue impact backfill for all initiatives
-- =============================================================================
-- Populates revenue_impact_usd_annual, revenue_impact_category, and
-- time_horizon_years for all initiatives — including creating business_case
-- rows for the 5 initiatives that don't have one yet.
--
-- Numbers are calibrated to tell a coherent portfolio story:
--   - The Big Bets show larger annual impact, longer horizons
--   - Retention initiatives show impact as protected revenue
--   - Cost savings and risk mitigation show as such
--   - Ratios between initiatives are plausible for a mid-market analytics SaaS
--
-- Idempotent: uses UPSERT semantics via ON CONFLICT.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Update existing business cases with new fields
-- -----------------------------------------------------------------------------
-- Initiative #1: Onboarding flow redesign — retention (activation) play
update business_case
set revenue_impact_usd_annual = 2400000,
    revenue_impact_category = 'retention',
    time_horizon_years = 2,
    predicted_cost = 380000
where initiative_id = '10000000-0000-0000-0000-000000000001';

-- Initiative #2: In-product sample datasets — activation → retention play
update business_case
set revenue_impact_usd_annual = 1800000,
    revenue_impact_category = 'retention',
    time_horizon_years = 2,
    predicted_cost = 220000
where initiative_id = '10000000-0000-0000-0000-000000000002';

-- Initiative #3: ProductA Launch — new revenue play (EMEA expansion)
update business_case
set revenue_impact_usd_annual = 4200000,
    revenue_impact_category = 'new_revenue',
    time_horizon_years = 3,
    predicted_cost = 950000
where initiative_id = '10000000-0000-0000-0000-000000000003';

-- Initiative #4: EMEA mid-market BDR team buildout — new revenue play
update business_case
set revenue_impact_usd_annual = 3800000,
    revenue_impact_category = 'new_revenue',
    time_horizon_years = 3,
    predicted_cost = 1400000
where initiative_id = '10000000-0000-0000-0000-000000000004';

-- Initiative #5: Q3 Production Bug Push — retention (churn prevention)
update business_case
set revenue_impact_usd_annual = 900000,
    revenue_impact_category = 'retention',
    time_horizon_years = 1,
    predicted_cost = 180000
where initiative_id = '10000000-0000-0000-0000-000000000005';

-- Initiative #6: Query engine caching layer — cost savings + retention
-- (activation improvement via faster queries; infrastructure play)
update business_case
set revenue_impact_usd_annual = 2100000,
    revenue_impact_category = 'cost_savings',
    time_horizon_years = 3,
    predicted_cost = 640000
where initiative_id = '10000000-0000-0000-0000-000000000006';

-- Initiative #7: Top-50 quarterly business reviews — retention play
update business_case
set revenue_impact_usd_annual = 3600000,
    revenue_impact_category = 'retention',
    time_horizon_years = 2,
    predicted_cost = 240000
where initiative_id = '10000000-0000-0000-0000-000000000007';

-- Initiative #8: AI query assistant beta program — new revenue (product bet)
update business_case
set revenue_impact_usd_annual = 5400000,
    revenue_impact_category = 'new_revenue',
    time_horizon_years = 3,
    predicted_cost = 820000
where initiative_id = '10000000-0000-0000-0000-000000000008';

-- Initiative #9: Dormant paid-account re-engagement — retention play
update business_case
set revenue_impact_usd_annual = 1600000,
    revenue_impact_category = 'retention',
    time_horizon_years = 1,
    predicted_cost = 140000
where initiative_id = '10000000-0000-0000-0000-000000000009';

-- Initiative #10: Successbook rollout (usage-triggered playbooks) — retention
update business_case
set revenue_impact_usd_annual = 2200000,
    revenue_impact_category = 'retention',
    time_horizon_years = 2,
    predicted_cost = 310000
where initiative_id = '10000000-0000-0000-0000-000000000010';

-- Initiative #11: In-product feature adoption tour — activation → retention
update business_case
set revenue_impact_usd_annual = 1400000,
    revenue_impact_category = 'retention',
    time_horizon_years = 2,
    predicted_cost = 180000
where initiative_id = '10000000-0000-0000-0000-000000000011';

-- -----------------------------------------------------------------------------
-- Insert business cases for the 5 initiatives without one
-- -----------------------------------------------------------------------------
-- Initiative #12: Documentation overhaul — cost savings (deflect support tickets)
insert into business_case (initiative_id, predicted_value, predicted_cost, decision, summary,
                            revenue_impact_usd_annual, revenue_impact_category, time_horizon_years)
values (
    '10000000-0000-0000-0000-000000000012',
    450000, 120000, 'go',
    'Documentation overhaul deflects tier-1 support tickets and reduces new-hire ramp time. Modest but real cost savings.',
    450000, 'cost_savings', 2
)
on conflict (initiative_id) do update set
    revenue_impact_usd_annual = excluded.revenue_impact_usd_annual,
    revenue_impact_category = excluded.revenue_impact_category,
    time_horizon_years = excluded.time_horizon_years,
    predicted_value = excluded.predicted_value,
    predicted_cost = excluded.predicted_cost,
    decision = excluded.decision,
    summary = excluded.summary;

-- Initiative #13: AI Time Savings Framework — cost savings (internal productivity)
insert into business_case (initiative_id, predicted_value, predicted_cost, decision, summary,
                            revenue_impact_usd_annual, revenue_impact_category, time_horizon_years)
values (
    '10000000-0000-0000-0000-000000000013',
    1800000, 220000, 'go',
    'Establishes measurement framework and time-savings targets for AI adoption across the engineering and product organizations. Impact = reclaimed hours at loaded cost.',
    1800000, 'cost_savings', 2
)
on conflict (initiative_id) do update set
    revenue_impact_usd_annual = excluded.revenue_impact_usd_annual,
    revenue_impact_category = excluded.revenue_impact_category,
    time_horizon_years = excluded.time_horizon_years,
    predicted_value = excluded.predicted_value,
    predicted_cost = excluded.predicted_cost,
    decision = excluded.decision,
    summary = excluded.summary;

-- Initiative #14: Claude/Cursor rollout to Engineering — cost savings (developer productivity)
insert into business_case (initiative_id, predicted_value, predicted_cost, decision, summary,
                            revenue_impact_usd_annual, revenue_impact_category, time_horizon_years)
values (
    '10000000-0000-0000-0000-000000000014',
    3200000, 480000, 'go',
    'Full-team rollout of Claude Code and Cursor to engineering. Impact modeled as productivity gain on code review, boilerplate, and bug diagnosis at loaded engineering cost.',
    3200000, 'cost_savings', 3
)
on conflict (initiative_id) do update set
    revenue_impact_usd_annual = excluded.revenue_impact_usd_annual,
    revenue_impact_category = excluded.revenue_impact_category,
    time_horizon_years = excluded.time_horizon_years,
    predicted_value = excluded.predicted_value,
    predicted_cost = excluded.predicted_cost,
    decision = excluded.decision,
    summary = excluded.summary;

-- Initiative #15: AI Maturity Scale rollout — strategic optionality; low direct revenue
insert into business_case (initiative_id, predicted_value, predicted_cost, decision, summary,
                            revenue_impact_usd_annual, revenue_impact_category, time_horizon_years)
values (
    '10000000-0000-0000-0000-000000000015',
    600000, 190000, 'go',
    'Establishes AI adoption maturity framework across department heads. Impact is diffuse — better prioritization of AI investments — and modeled conservatively.',
    600000, 'cost_savings', 3
)
on conflict (initiative_id) do update set
    revenue_impact_usd_annual = excluded.revenue_impact_usd_annual,
    revenue_impact_category = excluded.revenue_impact_category,
    time_horizon_years = excluded.time_horizon_years,
    predicted_value = excluded.predicted_value,
    predicted_cost = excluded.predicted_cost,
    decision = excluded.decision,
    summary = excluded.summary;

-- Initiative #16: Referral program (or similar) — new revenue
-- (Confirm the actual title of initiative #16 in your data; adjusting the
--  values if the initiative shape is different.)
insert into business_case (initiative_id, predicted_value, predicted_cost, decision, summary,
                            revenue_impact_usd_annual, revenue_impact_category, time_horizon_years)
values (
    '10000000-0000-0000-0000-000000000016',
    2600000, 320000, 'go',
    'Program launch driving pipeline from existing customers as referrers.',
    2600000, 'new_revenue', 2
)
on conflict (initiative_id) do update set
    revenue_impact_usd_annual = excluded.revenue_impact_usd_annual,
    revenue_impact_category = excluded.revenue_impact_category,
    time_horizon_years = excluded.time_horizon_years,
    predicted_value = excluded.predicted_value,
    predicted_cost = excluded.predicted_cost,
    decision = excluded.decision,
    summary = excluded.summary;

-- -----------------------------------------------------------------------------
-- Also sync predicted_value with revenue_impact_usd_annual for the 11 that
-- already had business cases, so both fields reflect the same underlying number.
-- (New code reads revenue_impact_usd_annual; old code reads predicted_value.)
-- -----------------------------------------------------------------------------
update business_case
set predicted_value = revenue_impact_usd_annual
where revenue_impact_usd_annual is not null
  and (predicted_value is null or predicted_value <> revenue_impact_usd_annual);

-- End of seed

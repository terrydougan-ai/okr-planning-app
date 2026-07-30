-- =============================================================================
-- Migration: revenue impact fields on business_case
-- =============================================================================
-- Adds explicit fields to make revenue impact comparable across initiatives:
--   revenue_impact_usd_annual: the honest per-year dollar figure. This
--     replaces the ambiguous predicted_value going forward, but predicted_value
--     is left in place for backward compatibility with existing code.
--   revenue_impact_category: what kind of impact — new revenue, retention,
--     cost savings, or risk mitigation. Same dollar figure means different
--     things depending on category, and executives read them differently.
--   time_horizon_years: over what timeframe the impact accrues. A $500K/year
--     initiative that runs for 3 years is worth $1.5M lifetime; a one-time
--     $500K launch is not the same thing.
--
-- predicted_cost is retained as-is; the app now documents that it represents
-- dollars invested.
--
-- Safe to re-run — idempotent via IF NOT EXISTS on each column.
-- =============================================================================

alter table business_case
    add column if not exists revenue_impact_usd_annual numeric,
    add column if not exists revenue_impact_category text
        check (revenue_impact_category is null or revenue_impact_category in (
            'new_revenue',
            'retention',
            'cost_savings',
            'risk_mitigation'
        )),
    add column if not exists time_horizon_years integer;

comment on column business_case.revenue_impact_usd_annual is
    'Annual revenue impact in USD. New sales, protected revenue (retention), cost savings, or avoided-cost (risk) all normalize into this single figure.';

comment on column business_case.revenue_impact_category is
    'Type of impact: new_revenue | retention | cost_savings | risk_mitigation';

comment on column business_case.time_horizon_years is
    'Years over which the impact accrues. Default 1 for straight annual bets. Longer for infrastructure investments.';

comment on column business_case.predicted_cost is
    'Total dollars invested (implementation + ongoing operating cost). Compared against revenue_impact_usd_annual × time_horizon_years to compute lifetime ROI.';

-- Backward-compat note: existing code reading predicted_value continues to
-- work. New code should read revenue_impact_usd_annual.

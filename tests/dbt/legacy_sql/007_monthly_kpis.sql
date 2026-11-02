-- Build monthly analytical controls and a BI-facing view from migration 006.
-- Grain: one row per observed calendar month; absent months are not zero sales.
-- Initial snapshot only. No source updates and no automatic fact refresh.
BEGIN ISOLATION LEVEL REPEATABLE READ;
SET LOCAL lock_timeout = '30s';
SELECT pg_advisory_xact_lock(690007);

DO $$
BEGIN
    IF to_regclass('marts.sales_monthly') IS NOT NULL
       OR to_regclass('marts.v_sales_monthly_kpis') IS NOT NULL
       OR to_regclass('marts.monthly_kpi_build_audit') IS NOT NULL THEN
        RAISE EXCEPTION 'Monthly KPI objects already exist; initial build will not overwrite them.';
    END IF;
    IF (SELECT COUNT(*) FROM marts.sales_build_audit
        WHERE preservation_check = 'PASSED') <> 1 THEN
        RAISE EXCEPTION 'Expected one successful migration 006 audit record.';
    END IF;
END $$;

\echo Capturing fact totals and checking date availability...
CREATE TEMP TABLE kpi_source_control ON COMMIT DROP AS
SELECT COUNT(*) AS source_records,
    COUNT(*) FILTER (WHERE ordered_on IS NULL) AS undated_records,
    SUM(reported_sales_dollars::NUMERIC) AS reported_sales_dollars,
    COUNT(reported_sales_dollars) AS reported_sales_dollars_present,
    SUM(sales_bottles::NUMERIC) AS sales_bottles,
    COUNT(sales_bottles) AS sales_bottles_present,
    SUM(reported_sales_liters::NUMERIC) AS reported_sales_liters,
    COUNT(reported_sales_liters) AS reported_sales_liters_present,
    SUM(sales_gallons::NUMERIC) AS sales_gallons,
    COUNT(sales_gallons) AS sales_gallons_present
FROM marts.fact_sales;

-- This version requires a dated fact population. Fail explicitly rather than
-- silently dropping undated records from a monthly dashboard.
DO $$
BEGIN
    IF (SELECT source_records FROM kpi_source_control) = 0 THEN
        RAISE EXCEPTION 'Fact table is empty.';
    END IF;
    IF (SELECT undated_records FROM kpi_source_control) <> 0 THEN
        RAISE EXCEPTION 'Undated facts exist. Add an explicit undated bucket before building monthly KPIs.';
    END IF;
END $$;

\echo Aggregating all available years by calendar month...
CREATE TABLE marts.sales_monthly AS
SELECT DATE_TRUNC('month', ordered_on)::DATE AS month_start,
    COUNT(*) AS source_records,
    MIN(ordered_on) AS first_observed_date,
    MAX(ordered_on) AS last_observed_date,
    COUNT(DISTINCT ordered_on) AS observed_sales_days,
    COUNT(DISTINCT store_no) AS active_stores,
    COUNT(DISTINCT item_no) AS active_products,
    SUM(reported_sales_dollars::NUMERIC) AS reported_sales_dollars,
    COUNT(reported_sales_dollars) AS reported_sales_dollars_present,
    SUM(sales_bottles::NUMERIC) AS sales_bottles,
    COUNT(sales_bottles) AS sales_bottles_present,
    SUM(reported_sales_liters::NUMERIC) AS reported_sales_liters,
    COUNT(reported_sales_liters) AS reported_sales_liters_present,
    SUM(sales_gallons::NUMERIC) AS sales_gallons,
    COUNT(sales_gallons) AS sales_gallons_present,
    COUNT(*) FILTER (WHERE reported_sales_dollars < 0) AS negative_sales_records,
    SUM(reported_sales_dollars) FILTER (WHERE reported_sales_dollars < 0) AS negative_sales_dollars,
    COUNT(*) FILTER (WHERE store_no IS NULL) AS missing_store_records,
    COUNT(*) FILTER (WHERE item_no IS NULL) AS missing_product_records,
    COUNT(*) FILTER (WHERE money_check_evaluable) AS money_evaluable_records,
    COUNT(*) FILTER (WHERE money_mismatch) AS money_mismatch_records,
    SUM(reported_sales_dollars) FILTER (WHERE money_check_evaluable) AS reported_sales_dollars_evaluable,
    SUM(calculated_sales_dollars) FILTER (WHERE money_check_evaluable) AS calculated_sales_dollars_evaluable,
    SUM(ABS(reported_sales_dollars)) FILTER (WHERE money_check_evaluable) AS reported_sales_dollars_absolute_evaluable,
    SUM(sales_dollars_difference) FILTER (WHERE money_check_evaluable) AS money_signed_difference,
    SUM(ABS(sales_dollars_difference)) FILTER (WHERE money_check_evaluable) AS money_absolute_difference,
    COUNT(*) FILTER (WHERE volume_check_evaluable) AS volume_evaluable_records,
    COUNT(*) FILTER (WHERE volume_mismatch) AS volume_mismatch_records,
    SUM(reported_sales_liters) FILTER (WHERE volume_check_evaluable) AS reported_sales_liters_evaluable,
    SUM(calculated_sales_liters) FILTER (WHERE volume_check_evaluable) AS calculated_sales_liters_evaluable,
    SUM(ABS(reported_sales_liters)) FILTER (WHERE volume_check_evaluable) AS reported_sales_liters_absolute_evaluable,
    SUM(sales_liters_difference) FILTER (WHERE volume_check_evaluable) AS volume_signed_difference,
    SUM(ABS(sales_liters_difference)) FILTER (WHERE volume_check_evaluable) AS volume_absolute_difference,
    BOOL_OR('PRECISION_REVIEW_PERIOD' = ANY(quality_flags)) AS precision_review_period
FROM marts.fact_sales
GROUP BY DATE_TRUNC('month', ordered_on)::DATE;
ALTER TABLE marts.sales_monthly ADD PRIMARY KEY (month_start);
ALTER TABLE marts.sales_monthly
    ADD CHECK (source_records > 0),
    ADD CHECK (money_mismatch_records BETWEEN 0 AND money_evaluable_records),
    ADD CHECK (money_evaluable_records BETWEEN 0 AND source_records),
    ADD CHECK (volume_mismatch_records BETWEEN 0 AND volume_evaluable_records),
    ADD CHECK (volume_evaluable_records BETWEEN 0 AND source_records);

\echo Validating that monthly aggregation preserves fact totals...
CREATE TEMP TABLE kpi_monthly_control ON COMMIT DROP AS
SELECT SUM(source_records) AS source_records,
        SUM(reported_sales_dollars) AS reported_sales_dollars,
        SUM(reported_sales_dollars_present) AS reported_sales_dollars_present,
        SUM(sales_bottles) AS sales_bottles,
        SUM(sales_bottles_present) AS sales_bottles_present,
        SUM(reported_sales_liters) AS reported_sales_liters,
        SUM(reported_sales_liters_present) AS reported_sales_liters_present,
        SUM(sales_gallons) AS sales_gallons,
        SUM(sales_gallons_present) AS sales_gallons_present
FROM marts.sales_monthly;

DO $$
DECLARE source_values JSONB; monthly_values JSONB;
BEGIN
    SELECT to_jsonb(s) - 'undated_records' INTO source_values
    FROM kpi_source_control s;
    SELECT to_jsonb(m) INTO monthly_values FROM kpi_monthly_control m;
    IF source_values IS DISTINCT FROM monthly_values THEN
        RAISE EXCEPTION 'Monthly count, non-NULL counts or reported totals do not match fact totals.';
    END IF;
END $$;

-- Ratios remain unrounded in the database. Format them in the report.
-- Percentages use the 0-100 scale; do not apply a BI percentage format that
-- multiplies these values by 100 again.
CREATE VIEW marts.v_sales_monthly_kpis AS
SELECT m.*,
    100::NUMERIC * m.money_evaluable_records / NULLIF(m.source_records, 0) AS money_check_coverage_pct,
    100::NUMERIC * m.money_mismatch_records / NULLIF(m.money_evaluable_records, 0) AS money_mismatch_pct_of_evaluable,
    100::NUMERIC * m.money_absolute_difference / NULLIF(m.reported_sales_dollars_absolute_evaluable, 0) AS money_absolute_difference_pct,
    CASE
        WHEN m.money_evaluable_records = 0 THEN 'NOT_EVALUABLE'
        WHEN m.precision_review_period THEN 'REVIEW_REQUIRED'
        WHEN m.money_mismatch_records > 0 THEN 'DISCREPANCIES_PRESENT'
        ELSE 'NO_MISMATCH_DETECTED'
    END::TEXT AS money_reconciliation_status,
    100::NUMERIC * m.volume_evaluable_records / NULLIF(m.source_records, 0) AS volume_check_coverage_pct,
    100::NUMERIC * m.volume_mismatch_records / NULLIF(m.volume_evaluable_records, 0) AS volume_mismatch_pct_of_evaluable,
    100::NUMERIC * m.volume_absolute_difference / NULLIF(m.reported_sales_liters_absolute_evaluable, 0) AS volume_absolute_difference_pct,
    CASE
        WHEN m.volume_evaluable_records = 0 THEN 'NOT_EVALUABLE'
        WHEN m.precision_review_period THEN 'REVIEW_REQUIRED'
        WHEN m.volume_mismatch_records > 0 THEN 'DISCREPANCIES_PRESENT'
        ELSE 'NO_MISMATCH_DETECTED'
    END::TEXT AS volume_reconciliation_status,
    -- Observation bounds do not establish extract completeness.
    'UNVERIFIED'::TEXT AS period_completeness_status,
    p.month_start AS prior_year_month_start,
    p.reported_sales_dollars AS prior_year_reported_sales_dollars,
    m.reported_sales_dollars - p.reported_sales_dollars
        AS reported_sales_yoy_difference,
    CASE WHEN p.reported_sales_dollars > 0
         THEN 100::NUMERIC * (m.reported_sales_dollars - p.reported_sales_dollars)
              / p.reported_sales_dollars
    END AS reported_sales_yoy_pct,
    CASE WHEN p.month_start IS NULL THEN 'PRIOR_YEAR_MONTH_UNAVAILABLE'
         WHEN p.reported_sales_dollars IS NULL THEN 'PRIOR_YEAR_SALES_UNAVAILABLE'
         WHEN p.reported_sales_dollars <= 0 THEN 'NONPOSITIVE_BASE'
         WHEN m.reported_sales_dollars IS NULL THEN 'CURRENT_SALES_UNAVAILABLE'
         ELSE 'COMPUTED_FROM_REPORTED_VALUES'
    END::TEXT AS yoy_calculation_status,
    -- Multiple caveats can coexist; do not collapse them into a blanket PASS.
    ARRAY_REMOVE(ARRAY[
        'PERIOD_COMPLETENESS_UNVERIFIED'::TEXT,
        CASE WHEN p.month_start IS NULL THEN 'PRIOR_YEAR_MONTH_UNAVAILABLE' END,
        CASE WHEN m.precision_review_period OR COALESCE(p.precision_review_period, FALSE)
             THEN 'PRECISION_REVIEW_IN_COMPARISON' END,
        CASE WHEN m.money_evaluable_records < m.source_records
                   OR p.money_evaluable_records < p.source_records
             THEN 'MONEY_RECONCILIATION_COVERAGE_INCOMPLETE' END,
        CASE WHEN m.reported_sales_dollars_present < m.source_records
                   OR p.reported_sales_dollars_present < p.source_records
             THEN 'REPORTED_SALES_COVERAGE_INCOMPLETE' END
    ], NULL)::TEXT[] AS yoy_caveats,
    'monthly_kpis_v1'::TEXT AS kpi_policy
FROM marts.sales_monthly m
-- Match the exact calendar month a year earlier; LAG(12) is unsafe if an
-- entire month is absent from the data.
LEFT JOIN marts.sales_monthly p
    ON p.month_start = (m.month_start - INTERVAL '1 year')::DATE;

CREATE TABLE marts.monthly_kpi_build_audit AS
SELECT transaction_timestamp() AS build_started_at,
       clock_timestamp() AS validated_at,
       'monthly_kpis_v1'::TEXT AS kpi_policy,
       'PASSED'::TEXT AS preservation_check,
       (SELECT validated_at FROM marts.sales_build_audit
        WHERE preservation_check = 'PASSED') AS source_mart_validated_at,
       (SELECT COUNT(*) FROM marts.sales_monthly) AS month_count,
       (SELECT MIN(month_start) FROM marts.sales_monthly) AS first_month,
       (SELECT MAX(month_start) FROM marts.sales_monthly) AS last_month,
       to_jsonb(s) AS source_control,
       to_jsonb(m) AS monthly_control
FROM kpi_source_control s CROSS JOIN kpi_monthly_control m;

COMMENT ON TABLE marts.sales_monthly IS
'Observed-month snapshot of all available fact years. Distinct counts are not additive across months. Do not sum ratios; recalculate from counts and denominators.';
COMMENT ON VIEW marts.v_sales_monthly_kpis IS
'Reported monthly KPIs with reconciliation coverage and exact-month YoY. Calculated measures are diagnostics; completeness remains unverified. Percentages use a 0-100 scale.';
COMMENT ON TABLE marts.monthly_kpi_build_audit IS
'Preservation controls for the initial monthly snapshot. PASSED does not establish source correctness or extract completeness.';

ANALYZE marts.sales_monthly;
COMMIT;

\echo Monthly KPI snapshot committed successfully.
SELECT kpi_policy, preservation_check, month_count, first_month, last_month,
       monthly_control->>'source_records' AS source_records
FROM marts.monthly_kpi_build_audit;


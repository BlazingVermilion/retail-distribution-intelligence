-- Local Power BI access to the monthly snapshot built by migration 007.
-- Run as postgres. Set the login password interactively AFTER this commits.
-- This migration does not store, print or generate a password.
BEGIN;
SET LOCAL lock_timeout = '30s';
SELECT pg_advisory_xact_lock(690008);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'retail_bi') THEN
        RAISE EXCEPTION 'Role retail_bi already exists; refusing to change an existing account.';
    END IF;
    IF to_regclass('marts.bi_sales_monthly') IS NOT NULL THEN
        RAISE EXCEPTION 'BI view already exists; refusing to replace it.';
    END IF;
    IF (SELECT COUNT(*) FROM marts.monthly_kpi_build_audit
        WHERE preservation_check = 'PASSED') <> 1 THEN
        RAISE EXCEPTION 'Expected one successful monthly KPI build audit.';
    END IF;
END $$;

-- Expose only scalar fields. PostgreSQL arrays become readable text so the
-- Power BI connector does not need to interpret array-valued columns.
CREATE VIEW marts.bi_sales_monthly AS
SELECT
    k.month_start,
    EXTRACT(YEAR FROM k.month_start)::INTEGER AS calendar_year,
    EXTRACT(MONTH FROM k.month_start)::INTEGER AS calendar_month,
    k.source_records,
    k.active_stores,
    k.active_products,
    k.reported_sales_dollars,
    k.sales_bottles,
    k.reported_sales_liters,
    k.negative_sales_records,
    k.negative_sales_dollars,
    k.money_evaluable_records,
    k.money_mismatch_records,
    k.money_check_coverage_pct,
    k.money_mismatch_pct_of_evaluable,
    k.money_signed_difference,
    k.money_absolute_difference,
    k.reported_sales_dollars_absolute_evaluable,
    k.money_absolute_difference_pct,
    k.money_reconciliation_status,
    k.volume_evaluable_records,
    k.volume_mismatch_records,
    k.volume_check_coverage_pct,
    k.volume_mismatch_pct_of_evaluable,
    k.volume_absolute_difference,
    k.reported_sales_liters_absolute_evaluable,
    k.volume_absolute_difference_pct,
    k.volume_reconciliation_status,
    k.first_observed_date,
    k.last_observed_date,
    k.observed_sales_days,
    k.period_completeness_status,
    k.precision_review_period,
    k.prior_year_month_start,
    k.prior_year_reported_sales_dollars,
    k.reported_sales_yoy_difference,
    k.reported_sales_yoy_pct,
    k.yoy_calculation_status,
    ARRAY_TO_STRING(k.yoy_caveats, '; ') AS yoy_caveats,
    k.kpi_policy,
    a.validated_at AS kpi_snapshot_validated_at
FROM marts.v_sales_monthly_kpis k
CROSS JOIN marts.monthly_kpi_build_audit a
WHERE a.preservation_check = 'PASSED';

CREATE ROLE retail_bi LOGIN
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    CONNECTION LIMIT 10;
-- This default helps prevent accidental writes; object privileges are the
-- actual authorization boundary. No membership in ingestion/admin roles.
ALTER ROLE retail_bi SET default_transaction_read_only = on;
GRANT USAGE ON SCHEMA marts TO retail_bi;
GRANT SELECT ON marts.bi_sales_monthly TO retail_bi;
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO retail_bi', current_database());
END $$;

-- Detect unexpected PUBLIC grants instead of silently changing other roles.
DO $$
BEGIN
    IF NOT has_table_privilege('retail_bi', 'marts.bi_sales_monthly', 'SELECT') THEN
        RAISE EXCEPTION 'BI SELECT grant is missing.';
    END IF;
    IF has_table_privilege('retail_bi', 'marts.fact_sales', 'SELECT')
       OR has_table_privilege('retail_bi', 'marts.fact_sales', 'INSERT')
       OR has_table_privilege('retail_bi', 'marts.fact_sales', 'UPDATE')
       OR has_table_privilege('retail_bi', 'marts.fact_sales', 'DELETE')
       OR has_table_privilege('retail_bi', 'marts.fact_sales', 'TRUNCATE') THEN
        RAISE EXCEPTION 'Unexpected fact-table privileges inherited through PUBLIC; review grants.';
    END IF;
    IF (SELECT COUNT(*) FROM marts.bi_sales_monthly)
       <> (SELECT COUNT(*) FROM marts.sales_monthly) THEN
        RAISE EXCEPTION 'BI view row count differs from monthly snapshot.';
    END IF;
END $$;

COMMENT ON VIEW marts.bi_sales_monthly IS
'Read-only BI contract over the monthly snapshot. SQL percentages use 0-100; active counts and ratios are not additive. Array caveats exposed as text.';
COMMIT;

\echo BI view and login created. Set the password using psql backslash-password.
SELECT COUNT(*) AS available_months FROM marts.bi_sales_monthly;


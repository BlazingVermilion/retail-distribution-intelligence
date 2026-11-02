-- Initial analytical snapshot. Requires migrations 001 through 005.
-- Grain: one exact-deduplicated source record, identified within this export
-- by _audit_row_id. invoice_id is retained but is not a unique fact key.
-- Run as postgres using psql -v ON_ERROR_STOP=1.
-- This is deliberately an initial build, not an incremental refresh script.
BEGIN ISOLATION LEVEL REPEATABLE READ;
SET LOCAL lock_timeout = '30s';
SELECT pg_advisory_xact_lock(690006);

-- Refuse to replace an existing mart or an incomplete manually created model.
DO $$
BEGIN
    IF to_regclass('marts.fact_sales') IS NOT NULL
       OR to_regclass('marts.dim_store') IS NOT NULL
       OR to_regclass('marts.dim_product') IS NOT NULL
       OR to_regclass('marts.dim_date') IS NOT NULL
       OR to_regclass('marts.sales_build_audit') IS NOT NULL THEN
        RAISE EXCEPTION 'Mart objects already exist. Initial migration will not overwrite them.';
    END IF;
END $$;

\echo Capturing source reconciliation totals...
CREATE TEMP TABLE source_control ON COMMIT DROP AS
SELECT COUNT(*) AS row_count,
        COUNT(sales_bottles) AS sales_bottles_present,
        SUM(sales_bottles::NUMERIC) AS sales_bottles_sum,
        COUNT(reported_sales_dollars) AS reported_sales_dollars_present,
        SUM(reported_sales_dollars::NUMERIC) AS reported_sales_dollars_sum,
        COUNT(calculated_sales_dollars) AS calculated_sales_dollars_present,
        SUM(calculated_sales_dollars::NUMERIC) AS calculated_sales_dollars_sum,
        COUNT(sales_dollars_difference) AS sales_dollars_difference_present,
        SUM(sales_dollars_difference::NUMERIC) AS sales_dollars_difference_sum,
        COUNT(reported_sales_liters) AS reported_sales_liters_present,
        SUM(reported_sales_liters::NUMERIC) AS reported_sales_liters_sum,
        COUNT(calculated_sales_liters) AS calculated_sales_liters_present,
        SUM(calculated_sales_liters::NUMERIC) AS calculated_sales_liters_sum,
        COUNT(sales_liters_difference) AS sales_liters_difference_present,
        SUM(sales_liters_difference::NUMERIC) AS sales_liters_difference_sum,
        COUNT(sales_gallons) AS sales_gallons_present,
        SUM(sales_gallons::NUMERIC) AS sales_gallons_sum,
        COUNT(state_bottle_cost) AS state_bottle_cost_present,
        SUM(state_bottle_cost::NUMERIC) AS state_bottle_cost_sum,
        COUNT(state_bottle_retail) AS state_bottle_retail_present,
        SUM(state_bottle_retail::NUMERIC) AS state_bottle_retail_sum
FROM staging.iowa_sales_reconciled;

DO $$
BEGIN
    IF (SELECT row_count FROM source_control) = 0 THEN
        RAISE EXCEPTION 'Source is empty; refusing to build an empty mart.';
    END IF;
END $$;

\echo Materializing fact rows; this step can take time...
-- No joins or filters: source lineage, original typed fields, flags, category
-- and vendor are retained at transaction grain. Retained descriptive fields
-- provide observed historical context; dimensions expose latest observations.
CREATE TABLE marts.fact_sales AS
SELECT * FROM staging.iowa_sales_reconciled;
ALTER TABLE marts.fact_sales ADD PRIMARY KEY (_audit_row_id);

\echo Building latest-observed store and product dimensions...
-- Select one complete observed record, never independent MAX values from
-- different rows. Unknown dates rank last; audit ID breaks same-date ties
-- deterministically within this export, not by an assumed transaction time.
CREATE TABLE marts.dim_store AS
SELECT DISTINCT ON (store_no)
    store_no, store_name, store_address, store_city, store_zip_code,
    county_fips_code, county_name,
    ordered_on AS last_observed_on,
    _audit_row_id AS attribute_source_audit_row_id
FROM marts.fact_sales
WHERE store_no IS NOT NULL
ORDER BY store_no, ordered_on DESC NULLS LAST, _audit_row_id DESC;
ALTER TABLE marts.dim_store ADD PRIMARY KEY (store_no);

CREATE TABLE marts.dim_product AS
SELECT DISTINCT ON (item_no)
    item_no, im_desc, bottle_volume_ml, pack,
    ordered_on AS last_observed_on,
    _audit_row_id AS attribute_source_audit_row_id
FROM marts.fact_sales
WHERE item_no IS NOT NULL
ORDER BY item_no, ordered_on DESC NULLS LAST, _audit_row_id DESC;
ALTER TABLE marts.dim_product ADD PRIMARY KEY (item_no);

-- Generate a continuous calendar, including days without sales.
CREATE TABLE marts.dim_date AS
WITH bounds AS (
    SELECT MIN(ordered_on) AS first_day, MAX(ordered_on) AS last_day
    FROM marts.fact_sales
), calendar AS (
    SELECT first_day + g.day_offset AS calendar_date
    FROM bounds
    CROSS JOIN LATERAL generate_series(0, last_day - first_day) AS g(day_offset)
)
SELECT calendar_date,
       EXTRACT(YEAR FROM calendar_date)::INTEGER AS calendar_year,
       EXTRACT(QUARTER FROM calendar_date)::INTEGER AS calendar_quarter,
       EXTRACT(MONTH FROM calendar_date)::INTEGER AS calendar_month,
       DATE_TRUNC('month', calendar_date)::DATE AS month_start,
       EXTRACT(ISODOW FROM calendar_date)::INTEGER AS iso_day_of_week,
       (EXTRACT(ISODOW FROM calendar_date) IN (6, 7)) AS is_weekend
FROM calendar;
ALTER TABLE marts.dim_date ADD PRIMARY KEY (calendar_date);

\echo Validating dimension relationships and creating date index...
-- NULL natural keys remain NULL, preserving rows with unavailable identifiers.
-- Every non-NULL key must resolve to exactly one dimension record.
ALTER TABLE marts.fact_sales
    ADD CONSTRAINT fact_sales_date_fk FOREIGN KEY (ordered_on)
        REFERENCES marts.dim_date(calendar_date),
    ADD CONSTRAINT fact_sales_store_fk FOREIGN KEY (store_no)
        REFERENCES marts.dim_store(store_no),
    ADD CONSTRAINT fact_sales_product_fk FOREIGN KEY (item_no)
        REFERENCES marts.dim_product(item_no);
CREATE INDEX fact_sales_ordered_on_idx ON marts.fact_sales(ordered_on);

\echo Reconciling fact totals against the source snapshot...
CREATE TEMP TABLE fact_control ON COMMIT DROP AS
SELECT COUNT(*) AS row_count,
        COUNT(sales_bottles) AS sales_bottles_present,
        SUM(sales_bottles::NUMERIC) AS sales_bottles_sum,
        COUNT(reported_sales_dollars) AS reported_sales_dollars_present,
        SUM(reported_sales_dollars::NUMERIC) AS reported_sales_dollars_sum,
        COUNT(calculated_sales_dollars) AS calculated_sales_dollars_present,
        SUM(calculated_sales_dollars::NUMERIC) AS calculated_sales_dollars_sum,
        COUNT(sales_dollars_difference) AS sales_dollars_difference_present,
        SUM(sales_dollars_difference::NUMERIC) AS sales_dollars_difference_sum,
        COUNT(reported_sales_liters) AS reported_sales_liters_present,
        SUM(reported_sales_liters::NUMERIC) AS reported_sales_liters_sum,
        COUNT(calculated_sales_liters) AS calculated_sales_liters_present,
        SUM(calculated_sales_liters::NUMERIC) AS calculated_sales_liters_sum,
        COUNT(sales_liters_difference) AS sales_liters_difference_present,
        SUM(sales_liters_difference::NUMERIC) AS sales_liters_difference_sum,
        COUNT(sales_gallons) AS sales_gallons_present,
        SUM(sales_gallons::NUMERIC) AS sales_gallons_sum,
        COUNT(state_bottle_cost) AS state_bottle_cost_present,
        SUM(state_bottle_cost::NUMERIC) AS state_bottle_cost_sum,
        COUNT(state_bottle_retail) AS state_bottle_retail_present,
        SUM(state_bottle_retail::NUMERIC) AS state_bottle_retail_sum
FROM marts.fact_sales;

DO $$
DECLARE source_values JSONB; fact_values JSONB;
BEGIN
    SELECT to_jsonb(s) INTO source_values FROM source_control s;
    SELECT to_jsonb(f) INTO fact_values FROM fact_control f;
    IF source_values IS DISTINCT FROM fact_values THEN
        RAISE EXCEPTION 'Source/fact count, non-NULL count or numeric totals differ. Rolling back.';
    END IF;
END $$;

-- The audit survives commit; these controls verify preservation, not that
-- source values are economically correct. Unit-price sums are checksums only.
CREATE TABLE marts.sales_build_audit AS
SELECT transaction_timestamp() AS build_started_at,
       clock_timestamp() AS validated_at,
       'initial_snapshot_v1'::TEXT AS build_policy,
       'staging.iowa_sales_reconciled'::TEXT AS source_relation,
       'PASSED'::TEXT AS preservation_check,
       to_jsonb(s) AS source_control,
       to_jsonb(f) AS fact_control
FROM source_control s CROSS JOIN fact_control f;

COMMENT ON TABLE marts.fact_sales IS
'One exact-deduplicated source record per audit ID in this export. Reported measures are preserved; calculated measures are diagnostic estimates. Snapshot, not auto-refresh.';
COMMENT ON TABLE marts.dim_store IS
'Latest observed store attributes per store_no. Not a historical SCD2 dimension; use fact fields for transaction-observed attributes.';
COMMENT ON TABLE marts.dim_product IS
'Latest observed product attributes per item_no. Transaction calculations retain fact-level volume, pack and prices.';
COMMENT ON TABLE marts.sales_build_audit IS
'Row counts, non-NULL counts and numeric sums reconcile source to fact. PASSED concerns preservation only, not business data quality.';

ANALYZE marts.dim_date;
ANALYZE marts.dim_store;
ANALYZE marts.dim_product;
ANALYZE marts.fact_sales;
COMMIT;

\echo Mart committed successfully.
SELECT build_policy, preservation_check,
       fact_control->>'row_count' AS fact_rows,
       validated_at
FROM marts.sales_build_audit;


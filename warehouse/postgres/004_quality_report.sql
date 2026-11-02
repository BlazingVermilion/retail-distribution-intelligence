-- Purpose: profile typed data by month before approving any business KPI.
-- Run as the administrative user. This scans the full dataset but does not
-- change source rows or persist another full copy of 17 million records.
-- Re-running replaces only this compact derived report, atomically.
BEGIN ISOLATION LEVEL REPEATABLE READ;
SET LOCAL DateStyle = 'ISO, YMD';
SET LOCAL lock_timeout = '30s';

-- Fail early if there is no authoritative completed full load.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM ops.pg_loaded_exports
        WHERE target_table = 'staging.iowa_sales_exact' AND mode = 'full'
    ) THEN
        RAISE EXCEPTION 'A completed full load is required before quality profiling';
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS ops.iowa_quality_monthly (
    month_key TEXT PRIMARY KEY,
    row_count BIGINT NOT NULL,
    rows_with_invalid_fields BIGINT NOT NULL,
    invalid_or_missing_date_rows BIGINT NOT NULL,
    missing_cost_rows BIGINT NOT NULL,
    missing_retail_rows BIGINT NOT NULL,
    unavailable_sales_dollars_rows BIGINT NOT NULL,
    unavailable_sales_bottles_rows BIGINT NOT NULL,
    unavailable_sales_liters_rows BIGINT NOT NULL,
    missing_store_rows BIGINT NOT NULL,
    missing_item_rows BIGINT NOT NULL,
    missing_county_rows BIGINT NOT NULL,
    missing_category_rows BIGINT NOT NULL,
    rows_with_negative_measures BIGINT NOT NULL,
    money_check_eligible_rows BIGINT NOT NULL,
    money_mismatch_gt_001_rows BIGINT NOT NULL,
    volume_check_eligible_rows BIGINT NOT NULL,
    volume_mismatch_gt_001_liters_rows BIGINT NOT NULL,
    zero_bottle_rows BIGINT NOT NULL,
    integer_valued_sales_dollars_rows BIGINT NOT NULL,
    min_ordered_on DATE,
    max_ordered_on DATE,
    source_sha256 TEXT NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL,
    publication_status TEXT NOT NULL
);

TRUNCATE TABLE ops.iowa_quality_monthly;

INSERT INTO ops.iowa_quality_monthly
SELECT
    COALESCE(TO_CHAR(ordered_on, 'YYYY-MM'), 'INVALID_OR_MISSING_DATE'),
    COUNT(*),
    COUNT(*) FILTER (WHERE CARDINALITY(_invalid_fields) > 0),
    COUNT(*) FILTER (WHERE ordered_on IS NULL),
    COUNT(*) FILTER (WHERE 'state_bottle_cost' = ANY(_missing_fields)),
    COUNT(*) FILTER (WHERE 'state_bottle_retail' = ANY(_missing_fields)),
    COUNT(*) FILTER (WHERE sales_dollars IS NULL),
    COUNT(*) FILTER (WHERE sales_bottles IS NULL),
    COUNT(*) FILTER (WHERE sales_liters IS NULL),
    COUNT(*) FILTER (WHERE store_no IS NULL),
    COUNT(*) FILTER (WHERE item_no IS NULL),
    COUNT(*) FILTER (WHERE county_name IS NULL),
    COUNT(*) FILTER (WHERE category_code IS NULL),
    -- Negative adjustments are diagnostics, not automatically bad records.
    COUNT(*) FILTER (WHERE sales_dollars < 0 OR sales_bottles < 0 OR sales_liters < 0),
    COUNT(*) FILTER (WHERE sales_dollars IS NOT NULL
                     AND sales_bottles IS NOT NULL AND state_bottle_retail IS NOT NULL),
    -- Thresholds are exploratory. Do not repair values to force this identity.
    COUNT(*) FILTER (WHERE ABS(sales_dollars - sales_bottles::NUMERIC * state_bottle_retail) > 0.01),
    COUNT(*) FILTER (WHERE sales_liters IS NOT NULL
                     AND sales_bottles IS NOT NULL AND bottle_volume_ml IS NOT NULL),
    COUNT(*) FILTER (WHERE ABS(sales_liters - sales_bottles::NUMERIC * bottle_volume_ml / 1000) > 0.01),
    COUNT(*) FILTER (WHERE sales_bottles = 0),
    -- A high integer-valued share is a precision clue, not proof of rounding.
    COUNT(*) FILTER (WHERE sales_dollars IS NOT NULL AND sales_dollars = TRUNC(sales_dollars)),
    MIN(ordered_on), MAX(ordered_on),
    (SELECT source_sha256 FROM ops.pg_loaded_exports
     WHERE target_table = 'staging.iowa_sales_exact'),
    CURRENT_TIMESTAMP,
    'not_evaluated'
FROM staging.iowa_sales_typed
GROUP BY COALESCE(TO_CHAR(ordered_on, 'YYYY-MM'), 'INVALID_OR_MISSING_DATE');

-- The typed layer must preserve all registered input rows, including bad dates.
DO $$
DECLARE
    expected BIGINT;
    actual BIGINT;
BEGIN
    SELECT expected_rows INTO expected FROM ops.pg_loaded_exports
    WHERE target_table = 'staging.iowa_sales_exact';
    SELECT COALESCE(SUM(row_count), 0) INTO actual FROM ops.iowa_quality_monthly;
    IF actual IS DISTINCT FROM expected THEN
        RAISE EXCEPTION 'Row reconciliation failed: expected %, observed %', expected, actual;
    END IF;
END
$$;
COMMIT;

-- Small terminal output; the complete monthly report remains queryable in ops.
SELECT SUM(row_count) AS total_rows,
       SUM(rows_with_invalid_fields) AS rows_with_invalid_fields,
       SUM(invalid_or_missing_date_rows) AS invalid_or_missing_date_rows,
       SUM(missing_cost_rows) AS missing_cost_rows,
       SUM(missing_retail_rows) AS missing_retail_rows,
       SUM(money_check_eligible_rows) AS money_check_eligible_rows,
       SUM(money_mismatch_gt_001_rows) AS money_mismatch_gt_001_rows,
       SUM(volume_check_eligible_rows) AS volume_check_eligible_rows,
       SUM(volume_mismatch_gt_001_liters_rows) AS volume_mismatch_gt_001_liters_rows
FROM ops.iowa_quality_monthly;

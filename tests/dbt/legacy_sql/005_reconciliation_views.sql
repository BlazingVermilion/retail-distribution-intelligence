-- Purpose: compare reported measures with derived values without correcting sources.
-- Requires: successful 003_typed_views.sql (the corrected PL/pgSQL version).
-- Execute as the local administrative user. No source rows are changed or dropped.
-- Difference convention: reported minus calculated. NULL means not evaluable.
-- Policy version: reported_vs_calculated_v1.
-- Tolerances: strictly greater than 0.01 USD and 0.01 liters.
BEGIN;

CREATE OR REPLACE VIEW staging.iowa_sales_reconciled AS
SELECT
    -- Preserve existing typed columns and audit lineage for backward compatibility.
    t.*,
    t.sales_dollars AS reported_sales_dollars,
    c.calculated_sales_dollars,
    d.sales_dollars_difference,
    t.sales_liters AS reported_sales_liters,
    c.calculated_sales_liters,
    d.sales_liters_difference,
    (d.sales_dollars_difference IS NOT NULL) AS money_check_evaluable,
    (d.sales_liters_difference IS NOT NULL) AS volume_check_evaluable,
    -- A missing input is not a passing check: comparisons remain NULL.
    (ABS(d.sales_dollars_difference) > 0.01) AS money_mismatch,
    (ABS(d.sales_liters_difference) > 0.01) AS volume_mismatch,
    ARRAY_REMOVE(ARRAY[
        CASE WHEN CARDINALITY(t._invalid_fields) > 0 THEN 'INVALID_TYPED_FIELD' END,
        CASE WHEN t.ordered_on IS NULL THEN 'ORDER_DATE_UNAVAILABLE' END,
        CASE WHEN t.state_bottle_cost IS NULL THEN 'UNIT_COST_UNAVAILABLE' END,
        CASE WHEN t.state_bottle_retail IS NULL THEN 'UNIT_RETAIL_UNAVAILABLE' END,
        CASE WHEN t.sales_dollars IS NULL THEN 'REPORTED_SALES_UNAVAILABLE' END,
        CASE WHEN t.sales_bottles IS NULL THEN 'BOTTLE_COUNT_UNAVAILABLE' END,
        CASE WHEN t.sales_liters IS NULL THEN 'REPORTED_VOLUME_UNAVAILABLE' END,
        CASE WHEN t.bottle_volume_ml IS NULL THEN 'BOTTLE_VOLUME_UNAVAILABLE' END,
        CASE WHEN d.sales_dollars_difference IS NULL THEN 'MONEY_CHECK_NOT_EVALUABLE' END,
        CASE WHEN d.sales_liters_difference IS NULL THEN 'VOLUME_CHECK_NOT_EVALUABLE' END,
        CASE WHEN ABS(d.sales_dollars_difference) > 0.01 THEN 'MONEY_MISMATCH_GT_0_01_USD' END,
        CASE WHEN ABS(d.sales_liters_difference) > 0.01 THEN 'VOLUME_MISMATCH_GT_0_01_L' END,
        CASE WHEN t.sales_dollars < 0 OR t.sales_bottles < 0 OR t.sales_liters < 0
             THEN 'NEGATIVE_REPORTED_MEASURE' END,
        CASE WHEN t.bottle_volume_ml <= 0 THEN 'NONPOSITIVE_BOTTLE_VOLUME' END,
        -- This period was identified in the reviewed monthly report. The flag
        -- records an investigation boundary, not a proven correction rule.
        CASE WHEN t.ordered_on >= DATE '2025-11-01'
                  AND t.ordered_on < DATE '2026-02-01'
             THEN 'PRECISION_REVIEW_PERIOD' END
    ], NULL)::TEXT[] AS quality_flags,
    'reported_vs_calculated_v1'::TEXT AS calculation_policy,
    'not_evaluated'::TEXT AS publication_status
FROM staging.iowa_sales_typed t
CROSS JOIN LATERAL (
    -- Missing operands naturally yield NULL; no zero imputation or rounding.
    -- A finite numeric result does not prove that its source operands are correct.
    SELECT t.sales_bottles::NUMERIC * t.state_bottle_retail AS calculated_sales_dollars,
           t.sales_bottles::NUMERIC * t.bottle_volume_ml / 1000::NUMERIC
               AS calculated_sales_liters
) c
CROSS JOIN LATERAL (
    SELECT t.sales_dollars - c.calculated_sales_dollars AS sales_dollars_difference,
           t.sales_liters - c.calculated_sales_liters AS sales_liters_difference
) d;

COMMENT ON VIEW staging.iowa_sales_reconciled IS
'Reported and calculated measures; diagnostic comparisons only. No source corrections. Policy reported_vs_calculated_v1.';
COMMENT ON COLUMN staging.iowa_sales_reconciled.sales_dollars_difference IS
'Reported minus calculated USD. NULL when either side is unavailable; not an estimate of accounting loss.';
COMMENT ON COLUMN staging.iowa_sales_reconciled.sales_liters_difference IS
'Reported minus calculated liters. NULL when either side is unavailable.';
COMMENT ON COLUMN staging.iowa_sales_reconciled.quality_flags IS
'Diagnostic flags, not an automatic publication decision. Original field-level flags remain in _missing_fields and _invalid_fields.';

CREATE OR REPLACE VIEW staging.iowa_sales_sample_reconciled AS
SELECT
    -- Preserve existing typed columns and audit lineage for backward compatibility.
    t.*,
    t.sales_dollars AS reported_sales_dollars,
    c.calculated_sales_dollars,
    d.sales_dollars_difference,
    t.sales_liters AS reported_sales_liters,
    c.calculated_sales_liters,
    d.sales_liters_difference,
    (d.sales_dollars_difference IS NOT NULL) AS money_check_evaluable,
    (d.sales_liters_difference IS NOT NULL) AS volume_check_evaluable,
    -- A missing input is not a passing check: comparisons remain NULL.
    (ABS(d.sales_dollars_difference) > 0.01) AS money_mismatch,
    (ABS(d.sales_liters_difference) > 0.01) AS volume_mismatch,
    ARRAY_REMOVE(ARRAY[
        CASE WHEN CARDINALITY(t._invalid_fields) > 0 THEN 'INVALID_TYPED_FIELD' END,
        CASE WHEN t.ordered_on IS NULL THEN 'ORDER_DATE_UNAVAILABLE' END,
        CASE WHEN t.state_bottle_cost IS NULL THEN 'UNIT_COST_UNAVAILABLE' END,
        CASE WHEN t.state_bottle_retail IS NULL THEN 'UNIT_RETAIL_UNAVAILABLE' END,
        CASE WHEN t.sales_dollars IS NULL THEN 'REPORTED_SALES_UNAVAILABLE' END,
        CASE WHEN t.sales_bottles IS NULL THEN 'BOTTLE_COUNT_UNAVAILABLE' END,
        CASE WHEN t.sales_liters IS NULL THEN 'REPORTED_VOLUME_UNAVAILABLE' END,
        CASE WHEN t.bottle_volume_ml IS NULL THEN 'BOTTLE_VOLUME_UNAVAILABLE' END,
        CASE WHEN d.sales_dollars_difference IS NULL THEN 'MONEY_CHECK_NOT_EVALUABLE' END,
        CASE WHEN d.sales_liters_difference IS NULL THEN 'VOLUME_CHECK_NOT_EVALUABLE' END,
        CASE WHEN ABS(d.sales_dollars_difference) > 0.01 THEN 'MONEY_MISMATCH_GT_0_01_USD' END,
        CASE WHEN ABS(d.sales_liters_difference) > 0.01 THEN 'VOLUME_MISMATCH_GT_0_01_L' END,
        CASE WHEN t.sales_dollars < 0 OR t.sales_bottles < 0 OR t.sales_liters < 0
             THEN 'NEGATIVE_REPORTED_MEASURE' END,
        CASE WHEN t.bottle_volume_ml <= 0 THEN 'NONPOSITIVE_BOTTLE_VOLUME' END,
        -- This period was identified in the reviewed monthly report. The flag
        -- records an investigation boundary, not a proven correction rule.
        CASE WHEN t.ordered_on >= DATE '2025-11-01'
                  AND t.ordered_on < DATE '2026-02-01'
             THEN 'PRECISION_REVIEW_PERIOD' END
    ], NULL)::TEXT[] AS quality_flags,
    'reported_vs_calculated_v1'::TEXT AS calculation_policy,
    'not_evaluated'::TEXT AS publication_status
FROM staging.iowa_sales_sample_typed t
CROSS JOIN LATERAL (
    -- Missing operands naturally yield NULL; no zero imputation or rounding.
    -- A finite numeric result does not prove that its source operands are correct.
    SELECT t.sales_bottles::NUMERIC * t.state_bottle_retail AS calculated_sales_dollars,
           t.sales_bottles::NUMERIC * t.bottle_volume_ml / 1000::NUMERIC
               AS calculated_sales_liters
) c
CROSS JOIN LATERAL (
    SELECT t.sales_dollars - c.calculated_sales_dollars AS sales_dollars_difference,
           t.sales_liters - c.calculated_sales_liters AS sales_liters_difference
) d;

COMMENT ON VIEW staging.iowa_sales_sample_reconciled IS
'Reported and calculated measures; diagnostic comparisons only. No source corrections. Policy reported_vs_calculated_v1.';
COMMENT ON COLUMN staging.iowa_sales_sample_reconciled.sales_dollars_difference IS
'Reported minus calculated USD. NULL when either side is unavailable; not an estimate of accounting loss.';
COMMENT ON COLUMN staging.iowa_sales_sample_reconciled.sales_liters_difference IS
'Reported minus calculated liters. NULL when either side is unavailable.';
COMMENT ON COLUMN staging.iowa_sales_sample_reconciled.quality_flags IS
'Diagnostic flags, not an automatic publication decision. Original field-level flags remain in _missing_fields and _invalid_fields.';

-- Small regression checks execute before commit and do not scan the dataset.
-- Cover decimal arithmetic, sign convention, NULL handling and tolerance boundary.
DO $$
DECLARE
    example_money NUMERIC := 6::NUMERIC * 26::NUMERIC;
    example_volume NUMERIC := 6::NUMERIC * 750::NUMERIC / 1000::NUMERIC;
BEGIN
    IF example_money IS DISTINCT FROM 156::NUMERIC
       OR example_volume IS DISTINCT FROM 4.5::NUMERIC
       OR (157::NUMERIC - example_money) IS DISTINCT FROM 1::NUMERIC
       OR (4::NUMERIC - example_volume) IS DISTINCT FROM (-0.5)::NUMERIC
       OR (6::NUMERIC * NULL::NUMERIC) IS NOT NULL
       OR (ABS(NULL::NUMERIC) > 0.01) IS NOT NULL
       OR (ABS(0.01::NUMERIC) > 0.01)
       OR NOT (ABS(-0.02::NUMERIC) > 0.01)
    THEN
        RAISE EXCEPTION 'Reported-versus-calculated arithmetic contract failed';
    END IF;
END
$$;

GRANT SELECT ON staging.iowa_sales_reconciled,
                staging.iowa_sales_sample_reconciled TO retail_loader;
COMMIT;

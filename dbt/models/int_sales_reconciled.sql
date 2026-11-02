{{ config(materialized='view') }}

-- Preserve the reviewed SQL policy; changes require parity and regression tests.
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
FROM {{ ref('stg_iowa_sales') }} t
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
) d

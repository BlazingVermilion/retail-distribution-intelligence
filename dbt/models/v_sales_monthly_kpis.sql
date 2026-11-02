{{ config(materialized='view') }}

-- Preserve the reviewed SQL policy; changes require parity and regression tests.
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
FROM {{ ref('sales_monthly') }} m
-- Match the exact calendar month a year earlier; LAG(12) is unsafe if an
-- entire month is absent from the data.
LEFT JOIN {{ ref('sales_monthly') }} p
    ON p.month_start = (m.month_start - INTERVAL '1 year')::DATE

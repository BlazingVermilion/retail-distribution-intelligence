# Metrics in the monthly review

| Metric | Definition and interpretation |
|---|---|
| Reported sales | Sum of signed source-reported distribution dollars. Not consumer revenue or profit. |
| Net bottles | Sum of reported bottle quantities including signed adjustments. Forecast target at statewide monthly grain. |
| Active stores | Distinct non-null store identifiers observed in the month; not a count of all licensed stores. |
| Reported YoY | Percentage change from the exact same calendar month one year earlier when computable. Period completeness remains unverified. |
| Money coverage | Share of records with the inputs required to compare reported and calculated dollars. |
| Mismatch rate | Share of evaluable records flagged as monetary mismatches. No evaluable records means unavailable. |
| Absolute difference rate | Sum of absolute monetary differences divided by the sum of absolute reported dollars on evaluable records, as a percentage. Signed differences can offset; absolute differences do not. |

For the SQL definitions and comparison caveats see the [monthly model](../dbt/models/sales_monthly.sql) and [YoY model](../dbt/models/v_sales_monthly_kpis.sql).

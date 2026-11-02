-- Read a consistent view of both relations. Reject totals that do not reconcile.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
COPY (
 WITH forecast_panel_input AS (
SELECT date_trunc('month', ordered_on)::date AS month,
       COALESCE('code:' || NULLIF(trim(category_code), ''), 'missing:') AS category,
       count(*) AS records, count(sales_bottles) AS observed,
       sum(sales_bottles) AS bottles
FROM dbt_dev.fact_sales
GROUP BY 1, 2)
-- COPY below reads the facts once; carry monthly controls into the exported CSV.
 SELECT coalesce(p.month,k.month_start) AS month, p.category,p.records,p.observed,p.bottles,
        k.source_records AS control_records,k.sales_bottles AS control_bottles
 FROM forecast_panel_input p FULL JOIN marts.v_sales_monthly_kpis k ON p.month=k.month_start
 ORDER BY 1,2
) TO STDOUT WITH CSV HEADER;
ROLLBACK;


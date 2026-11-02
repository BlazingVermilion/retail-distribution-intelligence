-- Keep month and Monday together: a week crossing month end has two slices.
-- The monthly controls validate both the signed target and source row coverage.
COPY (
 WITH weekly AS (
   SELECT date_trunc('month',ordered_on)::date AS month,
          date_trunc('week',ordered_on)::date AS week,
          coalesce('store:' || nullif(trim(store_no),''),'missing:') AS store,
          count(*) AS records,count(sales_bottles) AS observed,sum(sales_bottles) AS bottles
   FROM dbt_dev.fact_sales GROUP BY 1,2,3
 )
 SELECT coalesce(w.month,k.month_start) AS month,w.week,w.store,w.records,w.observed,w.bottles,
        k.source_records AS control_records,k.sales_bottles AS control_bottles
 FROM weekly w FULL JOIN marts.v_sales_monthly_kpis k ON w.month=k.month_start
 ORDER BY 1,2,3
) TO STDOUT WITH CSV HEADER;

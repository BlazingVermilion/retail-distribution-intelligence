with f as (
select count(*)::numeric as records, sum(reported_sales_dollars) as dollars,
 count(reported_sales_dollars)::numeric as dollars_present,
 sum(sales_bottles::numeric) as bottles, count(sales_bottles)::numeric as bottles_present,
 sum(reported_sales_liters) as liters, count(reported_sales_liters)::numeric as liters_present,
 sum(sales_gallons) as gallons, count(sales_gallons)::numeric as gallons_present
from {{ ref('fact_sales') }}
), m as (
select sum(source_records) as records, sum(reported_sales_dollars) as dollars,
 sum(reported_sales_dollars_present) as dollars_present,
 sum(sales_bottles) as bottles, sum(sales_bottles_present) as bottles_present,
 sum(reported_sales_liters) as liters, sum(reported_sales_liters_present) as liters_present,
 sum(sales_gallons) as gallons, sum(sales_gallons_present) as gallons_present
from {{ ref('sales_monthly') }}
)
select 1 from f,m where to_jsonb(f) is distinct from to_jsonb(m)

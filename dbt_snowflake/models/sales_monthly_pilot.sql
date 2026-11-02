{{ config(materialized='table') }}
-- Distinct store counts describe one calendar month. Keep NULL coverage next to totals.
select
    date_trunc('month', ordered_on)::date as month_start,
    count(*) as rows_n,
    count(distinct audit_id) as unique_ids,
    count(distinct store_no) as stores,
    count(bottles) as bottles_n, count(dollars) as dollars_n, count(liters) as liters_n,
    sum(bottles) as bottles_sum, sum(dollars) as dollars_sum, sum(liters) as liters_sum
from {{ ref('stg_iowa_sales_pilot') }}
group by 1

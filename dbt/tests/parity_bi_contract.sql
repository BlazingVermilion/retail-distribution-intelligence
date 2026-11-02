{{ config(enabled=var('compare_legacy', false), tags=['parity']) }}
-- The legacy timestamp certifies its snapshot. The development preview has no such certification.
with a as (select to_jsonb(t) - 'kpi_snapshot_validated_at' as payload from {{ ref('bi_sales_monthly') }} t),
b as (select to_jsonb(t) - 'kpi_snapshot_validated_at' as payload from {{ source('legacy','bi_sales_monthly') }} t)
(select * from a except all select * from b)
union all
(select * from b except all select * from a)

{{ config(enabled=var('compare_legacy', false), tags=['parity']) }}
-- Bidirectional comparison catches missing, changed and extra rows.
(select * from {{ ref('v_sales_monthly_kpis') }} except all select * from {{ source('legacy', 'v_sales_monthly_kpis') }})
union all
(select * from {{ source('legacy', 'v_sales_monthly_kpis') }} except all select * from {{ ref('v_sales_monthly_kpis') }})

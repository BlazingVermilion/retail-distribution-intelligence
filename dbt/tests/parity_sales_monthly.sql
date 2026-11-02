{{ config(enabled=var('compare_legacy', false), tags=['parity']) }}
-- Bidirectional comparison catches missing, changed and extra rows.
(select * from {{ ref('sales_monthly') }} except all select * from {{ source('legacy', 'sales_monthly') }})
union all
(select * from {{ source('legacy', 'sales_monthly') }} except all select * from {{ ref('sales_monthly') }})

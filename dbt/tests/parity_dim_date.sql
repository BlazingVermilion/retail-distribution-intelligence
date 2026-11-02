{{ config(enabled=var('compare_legacy', false), tags=['parity']) }}
-- Bidirectional comparison catches missing, changed and extra rows.
(select * from {{ ref('dim_date') }} except all select * from {{ source('legacy', 'dim_date') }})
union all
(select * from {{ source('legacy', 'dim_date') }} except all select * from {{ ref('dim_date') }})

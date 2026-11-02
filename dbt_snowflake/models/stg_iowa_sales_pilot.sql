{{ config(materialized='view') }}
-- 12A already typed the six export columns. Preserve source precision and NULLs.
select audit_id, ordered_on, store_no, bottles, dollars, liters
from {{ source('pilot', 'iowa_sep_2026') }}

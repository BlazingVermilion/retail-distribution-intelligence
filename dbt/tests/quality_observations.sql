{{ config(severity='warn') }}
-- One result per affected month, not millions of raw failing records.
select month_start, money_evaluable_records, money_mismatch_records
from {{ ref('sales_monthly') }}
where money_evaluable_records < source_records or money_mismatch_records > 0

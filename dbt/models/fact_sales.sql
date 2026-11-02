{{ config(materialized='table') }}

-- Preserve the reviewed SQL policy; changes require parity and regression tests.
{{ config(indexes=[{'columns': ['_audit_row_id'], 'unique': true}, {'columns': ['ordered_on']}]) }}
select * from {{ ref('int_sales_reconciled') }}

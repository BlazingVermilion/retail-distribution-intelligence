{{ config(materialized='table') }}

-- Preserve the reviewed SQL policy; changes require parity and regression tests.
SELECT DISTINCT ON (item_no)
    item_no, im_desc, bottle_volume_ml, pack,
    ordered_on AS last_observed_on,
    _audit_row_id AS attribute_source_audit_row_id
FROM {{ ref('fact_sales') }}
WHERE item_no IS NOT NULL
ORDER BY item_no, ordered_on DESC NULLS LAST, _audit_row_id DESC

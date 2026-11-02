{{ config(materialized='table') }}

-- Preserve the reviewed SQL policy; changes require parity and regression tests.
SELECT DISTINCT ON (store_no)
    store_no, store_name, store_address, store_city, store_zip_code,
    county_fips_code, county_name,
    ordered_on AS last_observed_on,
    _audit_row_id AS attribute_source_audit_row_id
FROM {{ ref('fact_sales') }}
WHERE store_no IS NOT NULL
ORDER BY store_no, ordered_on DESC NULLS LAST, _audit_row_id DESC

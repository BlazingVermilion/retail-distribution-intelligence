{{ config(materialized='view') }}

-- Preserve the reviewed SQL policy; changes require parity and regression tests.
WITH normalized AS (
    SELECT _audit_row_id,
    NULLIF(BTRIM(invoice_id), '') AS invoice_id,
    NULLIF(BTRIM(ordered_on), '') AS ordered_on,
    NULLIF(BTRIM(store_no), '') AS store_no,
    NULLIF(BTRIM(store_name), '') AS store_name,
    NULLIF(BTRIM(store_address), '') AS store_address,
    NULLIF(BTRIM(store_city), '') AS store_city,
    NULLIF(BTRIM(store_zip_code), '') AS store_zip_code,
    NULLIF(BTRIM(county_fips_code), '') AS county_fips_code,
    NULLIF(BTRIM(county_name), '') AS county_name,
    NULLIF(BTRIM(category_code), '') AS category_code,
    NULLIF(BTRIM(category_name), '') AS category_name,
    NULLIF(BTRIM(vendor_number), '') AS vendor_number,
    NULLIF(BTRIM(vendor_name), '') AS vendor_name,
    NULLIF(BTRIM(item_no), '') AS item_no,
    NULLIF(BTRIM(im_desc), '') AS im_desc,
    NULLIF(BTRIM(pack), '') AS pack,
    NULLIF(BTRIM(bottle_volume_ml), '') AS bottle_volume_ml,
    NULLIF(BTRIM(state_bottle_cost), '') AS state_bottle_cost,
    NULLIF(BTRIM(state_bottle_retail), '') AS state_bottle_retail,
    NULLIF(BTRIM(sales_bottles), '') AS sales_bottles,
    NULLIF(BTRIM(sales_dollars), '') AS sales_dollars,
    NULLIF(BTRIM(sales_liters), '') AS sales_liters,
    NULLIF(BTRIM(sales_gallons), '') AS sales_gallons
    FROM {{ source('iowa', 'sales_exact') }}
)
SELECT s._audit_row_id, t.*,
    ARRAY_REMOVE(ARRAY[CASE WHEN s.invoice_id IS NULL THEN 'invoice_id' END, CASE WHEN s.ordered_on IS NULL THEN 'ordered_on' END, CASE WHEN s.store_no IS NULL THEN 'store_no' END, CASE WHEN s.store_name IS NULL THEN 'store_name' END, CASE WHEN s.store_address IS NULL THEN 'store_address' END, CASE WHEN s.store_city IS NULL THEN 'store_city' END, CASE WHEN s.store_zip_code IS NULL THEN 'store_zip_code' END, CASE WHEN s.county_fips_code IS NULL THEN 'county_fips_code' END, CASE WHEN s.county_name IS NULL THEN 'county_name' END, CASE WHEN s.category_code IS NULL THEN 'category_code' END, CASE WHEN s.category_name IS NULL THEN 'category_name' END, CASE WHEN s.vendor_number IS NULL THEN 'vendor_number' END, CASE WHEN s.vendor_name IS NULL THEN 'vendor_name' END, CASE WHEN s.item_no IS NULL THEN 'item_no' END, CASE WHEN s.im_desc IS NULL THEN 'im_desc' END, CASE WHEN s.pack IS NULL THEN 'pack' END, CASE WHEN s.bottle_volume_ml IS NULL THEN 'bottle_volume_ml' END, CASE WHEN s.state_bottle_cost IS NULL THEN 'state_bottle_cost' END, CASE WHEN s.state_bottle_retail IS NULL THEN 'state_bottle_retail' END, CASE WHEN s.sales_bottles IS NULL THEN 'sales_bottles' END, CASE WHEN s.sales_dollars IS NULL THEN 'sales_dollars' END, CASE WHEN s.sales_liters IS NULL THEN 'sales_liters' END, CASE WHEN s.sales_gallons IS NULL THEN 'sales_gallons' END], NULL)::TEXT[] AS _missing_fields,
    ARRAY_REMOVE(ARRAY[CASE WHEN s.ordered_on IS NOT NULL AND t.ordered_on IS NULL THEN 'ordered_on' END, CASE WHEN s.pack IS NOT NULL AND t.pack IS NULL THEN 'pack' END, CASE WHEN s.bottle_volume_ml IS NOT NULL AND t.bottle_volume_ml IS NULL THEN 'bottle_volume_ml' END, CASE WHEN s.state_bottle_cost IS NOT NULL AND t.state_bottle_cost IS NULL THEN 'state_bottle_cost' END, CASE WHEN s.state_bottle_retail IS NOT NULL AND t.state_bottle_retail IS NULL THEN 'state_bottle_retail' END, CASE WHEN s.sales_bottles IS NOT NULL AND t.sales_bottles IS NULL THEN 'sales_bottles' END, CASE WHEN s.sales_dollars IS NOT NULL AND t.sales_dollars IS NULL THEN 'sales_dollars' END, CASE WHEN s.sales_liters IS NOT NULL AND t.sales_liters IS NULL THEN 'sales_liters' END, CASE WHEN s.sales_gallons IS NOT NULL AND t.sales_gallons IS NULL THEN 'sales_gallons' END], NULL)::TEXT[] AS _invalid_fields
FROM normalized s
CROSS JOIN LATERAL (
    SELECT
    invoice_id AS invoice_id,
    {{ target.schema }}.try_iowa_date(ordered_on) AS ordered_on,
    store_no AS store_no,
    store_name AS store_name,
    store_address AS store_address,
    store_city AS store_city,
    store_zip_code AS store_zip_code,
    county_fips_code AS county_fips_code,
    county_name AS county_name,
    category_code AS category_code,
    category_name AS category_name,
    vendor_number AS vendor_number,
    vendor_name AS vendor_name,
    item_no AS item_no,
    im_desc AS im_desc,
    {{ target.schema }}.try_iowa_bigint(pack) AS pack,
    {{ target.schema }}.try_iowa_numeric(bottle_volume_ml) AS bottle_volume_ml,
    {{ target.schema }}.try_iowa_numeric(state_bottle_cost) AS state_bottle_cost,
    {{ target.schema }}.try_iowa_numeric(state_bottle_retail) AS state_bottle_retail,
    {{ target.schema }}.try_iowa_bigint(sales_bottles) AS sales_bottles,
    {{ target.schema }}.try_iowa_numeric(sales_dollars) AS sales_dollars,
    {{ target.schema }}.try_iowa_numeric(sales_liters) AS sales_liters,
    {{ target.schema }}.try_iowa_numeric(sales_gallons) AS sales_gallons
) t

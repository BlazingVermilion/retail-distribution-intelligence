-- Purpose: expose typed values without changing the audited source strings.
-- Run as the local administrative user on PostgreSQL 17.
-- Views retain every row. Missing and invalid values are separately flagged.
-- Monetary values use unconstrained NUMERIC to avoid rounding source precision.
BEGIN;

-- PL/pgSQL IF guards keep the cast in a separate statement. A SQL-language
-- CASE can be inlined and its constant cast evaluated during planning, even
-- when the validation condition would reject the value at execution time.
-- Expected invalid input returns NULL; unexpected database errors still surface.
CREATE OR REPLACE FUNCTION staging.try_iowa_numeric(value TEXT)
RETURNS NUMERIC
LANGUAGE plpgsql STABLE PARALLEL SAFE RETURNS NULL ON NULL INPUT AS $$
BEGIN
    -- Enforce finite decimal syntax before PostgreSQL numeric validation.
    IF value !~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$' THEN
        RETURN NULL;
    END IF;
    IF NOT pg_input_is_valid(value, 'numeric') THEN
        RETURN NULL;
    END IF;
    RETURN value::NUMERIC;
END;
$$;

CREATE OR REPLACE FUNCTION staging.try_iowa_bigint(value TEXT)
RETURNS BIGINT
LANGUAGE plpgsql STABLE PARALLEL SAFE RETURNS NULL ON NULL INPUT AS $$
BEGIN
    IF value !~ '^[+-]?[0-9]+$' THEN
        RETURN NULL;
    END IF;
    -- Test the BIGINT range before reaching the cast statement.
    IF NOT pg_input_is_valid(value, 'bigint') THEN
        RETURN NULL;
    END IF;
    RETURN value::BIGINT;
END;
$$;

CREATE OR REPLACE FUNCTION staging.try_iowa_date(value TEXT)
RETURNS DATE
LANGUAGE plpgsql STABLE PARALLEL SAFE RETURNS NULL ON NULL INPUT AS $$
BEGIN
    IF value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
        RETURN NULL;
    END IF;
    IF NOT pg_input_is_valid(value, 'date') THEN
        RETURN NULL;
    END IF;
    RETURN value::DATE;
END;
$$;

-- Small executable contract checks. Any failure aborts this migration.
DO $$
BEGIN
    IF staging.try_iowa_numeric('12.345') IS DISTINCT FROM 12.345::NUMERIC
       OR staging.try_iowa_numeric('NaN') IS NOT NULL
       OR staging.try_iowa_numeric('Infinity') IS NOT NULL
       OR staging.try_iowa_numeric('bad') IS NOT NULL
       OR staging.try_iowa_numeric('') IS NOT NULL
       OR staging.try_iowa_bigint('2.5') IS NOT NULL
       OR staging.try_iowa_bigint('9223372036854775808') IS NOT NULL
       OR staging.try_iowa_bigint('-9223372036854775809') IS NOT NULL
       OR staging.try_iowa_bigint('9223372036854775807') IS DISTINCT FROM 9223372036854775807::BIGINT
       OR staging.try_iowa_bigint('-9223372036854775808') IS DISTINCT FROM '-9223372036854775808'::BIGINT
       OR staging.try_iowa_bigint(NULL) IS NOT NULL
       OR staging.try_iowa_bigint('-2') IS DISTINCT FROM (-2)::BIGINT
       OR staging.try_iowa_date('2025-02-30') IS NOT NULL
       OR staging.try_iowa_date('2024-02-29') IS DISTINCT FROM DATE '2024-02-29'
    THEN
        RAISE EXCEPTION 'Typed conversion contract failed';
    END IF;
END
$$;

-- iowa_sales_exact: row identity and multiplicity are preserved; no joins or filters remove data.
CREATE OR REPLACE VIEW staging.iowa_sales_typed AS
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
    FROM staging.iowa_sales_exact
)
SELECT s._audit_row_id, t.*,
    ARRAY_REMOVE(ARRAY[CASE WHEN s.invoice_id IS NULL THEN 'invoice_id' END, CASE WHEN s.ordered_on IS NULL THEN 'ordered_on' END, CASE WHEN s.store_no IS NULL THEN 'store_no' END, CASE WHEN s.store_name IS NULL THEN 'store_name' END, CASE WHEN s.store_address IS NULL THEN 'store_address' END, CASE WHEN s.store_city IS NULL THEN 'store_city' END, CASE WHEN s.store_zip_code IS NULL THEN 'store_zip_code' END, CASE WHEN s.county_fips_code IS NULL THEN 'county_fips_code' END, CASE WHEN s.county_name IS NULL THEN 'county_name' END, CASE WHEN s.category_code IS NULL THEN 'category_code' END, CASE WHEN s.category_name IS NULL THEN 'category_name' END, CASE WHEN s.vendor_number IS NULL THEN 'vendor_number' END, CASE WHEN s.vendor_name IS NULL THEN 'vendor_name' END, CASE WHEN s.item_no IS NULL THEN 'item_no' END, CASE WHEN s.im_desc IS NULL THEN 'im_desc' END, CASE WHEN s.pack IS NULL THEN 'pack' END, CASE WHEN s.bottle_volume_ml IS NULL THEN 'bottle_volume_ml' END, CASE WHEN s.state_bottle_cost IS NULL THEN 'state_bottle_cost' END, CASE WHEN s.state_bottle_retail IS NULL THEN 'state_bottle_retail' END, CASE WHEN s.sales_bottles IS NULL THEN 'sales_bottles' END, CASE WHEN s.sales_dollars IS NULL THEN 'sales_dollars' END, CASE WHEN s.sales_liters IS NULL THEN 'sales_liters' END, CASE WHEN s.sales_gallons IS NULL THEN 'sales_gallons' END], NULL)::TEXT[] AS _missing_fields,
    ARRAY_REMOVE(ARRAY[CASE WHEN s.ordered_on IS NOT NULL AND t.ordered_on IS NULL THEN 'ordered_on' END, CASE WHEN s.pack IS NOT NULL AND t.pack IS NULL THEN 'pack' END, CASE WHEN s.bottle_volume_ml IS NOT NULL AND t.bottle_volume_ml IS NULL THEN 'bottle_volume_ml' END, CASE WHEN s.state_bottle_cost IS NOT NULL AND t.state_bottle_cost IS NULL THEN 'state_bottle_cost' END, CASE WHEN s.state_bottle_retail IS NOT NULL AND t.state_bottle_retail IS NULL THEN 'state_bottle_retail' END, CASE WHEN s.sales_bottles IS NOT NULL AND t.sales_bottles IS NULL THEN 'sales_bottles' END, CASE WHEN s.sales_dollars IS NOT NULL AND t.sales_dollars IS NULL THEN 'sales_dollars' END, CASE WHEN s.sales_liters IS NOT NULL AND t.sales_liters IS NULL THEN 'sales_liters' END, CASE WHEN s.sales_gallons IS NOT NULL AND t.sales_gallons IS NULL THEN 'sales_gallons' END], NULL)::TEXT[] AS _invalid_fields
FROM normalized s
CROSS JOIN LATERAL (
    SELECT
    invoice_id AS invoice_id,
    staging.try_iowa_date(ordered_on) AS ordered_on,
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
    staging.try_iowa_bigint(pack) AS pack,
    staging.try_iowa_numeric(bottle_volume_ml) AS bottle_volume_ml,
    staging.try_iowa_numeric(state_bottle_cost) AS state_bottle_cost,
    staging.try_iowa_numeric(state_bottle_retail) AS state_bottle_retail,
    staging.try_iowa_bigint(sales_bottles) AS sales_bottles,
    staging.try_iowa_numeric(sales_dollars) AS sales_dollars,
    staging.try_iowa_numeric(sales_liters) AS sales_liters,
    staging.try_iowa_numeric(sales_gallons) AS sales_gallons
) t;

-- iowa_sales_sample: row identity and multiplicity are preserved; no joins or filters remove data.
CREATE OR REPLACE VIEW staging.iowa_sales_sample_typed AS
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
    FROM staging.iowa_sales_sample
)
SELECT s._audit_row_id, t.*,
    ARRAY_REMOVE(ARRAY[CASE WHEN s.invoice_id IS NULL THEN 'invoice_id' END, CASE WHEN s.ordered_on IS NULL THEN 'ordered_on' END, CASE WHEN s.store_no IS NULL THEN 'store_no' END, CASE WHEN s.store_name IS NULL THEN 'store_name' END, CASE WHEN s.store_address IS NULL THEN 'store_address' END, CASE WHEN s.store_city IS NULL THEN 'store_city' END, CASE WHEN s.store_zip_code IS NULL THEN 'store_zip_code' END, CASE WHEN s.county_fips_code IS NULL THEN 'county_fips_code' END, CASE WHEN s.county_name IS NULL THEN 'county_name' END, CASE WHEN s.category_code IS NULL THEN 'category_code' END, CASE WHEN s.category_name IS NULL THEN 'category_name' END, CASE WHEN s.vendor_number IS NULL THEN 'vendor_number' END, CASE WHEN s.vendor_name IS NULL THEN 'vendor_name' END, CASE WHEN s.item_no IS NULL THEN 'item_no' END, CASE WHEN s.im_desc IS NULL THEN 'im_desc' END, CASE WHEN s.pack IS NULL THEN 'pack' END, CASE WHEN s.bottle_volume_ml IS NULL THEN 'bottle_volume_ml' END, CASE WHEN s.state_bottle_cost IS NULL THEN 'state_bottle_cost' END, CASE WHEN s.state_bottle_retail IS NULL THEN 'state_bottle_retail' END, CASE WHEN s.sales_bottles IS NULL THEN 'sales_bottles' END, CASE WHEN s.sales_dollars IS NULL THEN 'sales_dollars' END, CASE WHEN s.sales_liters IS NULL THEN 'sales_liters' END, CASE WHEN s.sales_gallons IS NULL THEN 'sales_gallons' END], NULL)::TEXT[] AS _missing_fields,
    ARRAY_REMOVE(ARRAY[CASE WHEN s.ordered_on IS NOT NULL AND t.ordered_on IS NULL THEN 'ordered_on' END, CASE WHEN s.pack IS NOT NULL AND t.pack IS NULL THEN 'pack' END, CASE WHEN s.bottle_volume_ml IS NOT NULL AND t.bottle_volume_ml IS NULL THEN 'bottle_volume_ml' END, CASE WHEN s.state_bottle_cost IS NOT NULL AND t.state_bottle_cost IS NULL THEN 'state_bottle_cost' END, CASE WHEN s.state_bottle_retail IS NOT NULL AND t.state_bottle_retail IS NULL THEN 'state_bottle_retail' END, CASE WHEN s.sales_bottles IS NOT NULL AND t.sales_bottles IS NULL THEN 'sales_bottles' END, CASE WHEN s.sales_dollars IS NOT NULL AND t.sales_dollars IS NULL THEN 'sales_dollars' END, CASE WHEN s.sales_liters IS NOT NULL AND t.sales_liters IS NULL THEN 'sales_liters' END, CASE WHEN s.sales_gallons IS NOT NULL AND t.sales_gallons IS NULL THEN 'sales_gallons' END], NULL)::TEXT[] AS _invalid_fields
FROM normalized s
CROSS JOIN LATERAL (
    SELECT
    invoice_id AS invoice_id,
    staging.try_iowa_date(ordered_on) AS ordered_on,
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
    staging.try_iowa_bigint(pack) AS pack,
    staging.try_iowa_numeric(bottle_volume_ml) AS bottle_volume_ml,
    staging.try_iowa_numeric(state_bottle_cost) AS state_bottle_cost,
    staging.try_iowa_numeric(state_bottle_retail) AS state_bottle_retail,
    staging.try_iowa_bigint(sales_bottles) AS sales_bottles,
    staging.try_iowa_numeric(sales_dollars) AS sales_dollars,
    staging.try_iowa_numeric(sales_liters) AS sales_liters,
    staging.try_iowa_numeric(sales_gallons) AS sales_gallons
) t;

-- Existing loader may inspect the views; it does not gain schema creation rights.
GRANT SELECT ON staging.iowa_sales_typed, staging.iowa_sales_sample_typed TO retail_loader;
COMMIT;

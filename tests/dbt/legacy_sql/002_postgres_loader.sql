-- Purpose: create a derived-data landing area and auditable load bookkeeping.
-- Run as the local administrative user after 001_create_schemas.sql.
-- Source strings remain unchanged; typed business models are a later step.
-- No CSV is loaded and no existing table is dropped by this script.
BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'retail_loader') THEN
        CREATE ROLE retail_loader LOGIN;
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS staging.iowa_sales_sample (
    invoice_id TEXT NOT NULL,
    ordered_on TEXT NOT NULL,
    store_no TEXT NOT NULL,
    store_name TEXT NOT NULL,
    store_address TEXT NOT NULL,
    store_city TEXT NOT NULL,
    store_zip_code TEXT NOT NULL,
    county_fips_code TEXT NOT NULL,
    county_name TEXT NOT NULL,
    category_code TEXT NOT NULL,
    category_name TEXT NOT NULL,
    vendor_number TEXT NOT NULL,
    vendor_name TEXT NOT NULL,
    item_no TEXT NOT NULL,
    im_desc TEXT NOT NULL,
    pack TEXT NOT NULL,
    bottle_volume_ml TEXT NOT NULL,
    state_bottle_cost TEXT NOT NULL,
    state_bottle_retail TEXT NOT NULL,
    sales_bottles TEXT NOT NULL,
    sales_dollars TEXT NOT NULL,
    sales_liters TEXT NOT NULL,
    sales_gallons TEXT NOT NULL,
    -- This ID is unique only within the one audit export accepted for this table.
    _audit_row_id BIGINT PRIMARY KEY CHECK (_audit_row_id > 0)
);

-- Keep the trial load physically separate from the full-data table.
CREATE TABLE IF NOT EXISTS staging.iowa_sales_exact
    (LIKE staging.iowa_sales_sample INCLUDING ALL);

CREATE TABLE IF NOT EXISTS ops.pg_load_runs (
    run_id UUID PRIMARY KEY,
    target_table TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    expected_rows BIGINT NOT NULL CHECK (expected_rows >= 0),
    loaded_rows BIGINT,
    state TEXT NOT NULL CHECK (state IN ('RUNNING','COMPLETED','SKIPPED','FAILED')),
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ops.pg_loaded_exports (
    -- One accepted export per target prevents mixing distinct snapshot versions.
    target_table TEXT PRIMARY KEY,
    source_sha256 TEXT NOT NULL,
    source_path TEXT NOT NULL,
    expected_rows BIGINT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('sample','full')),
    summary_sha256 TEXT NOT NULL,
    audit_summary JSONB NOT NULL,
    run_id UUID NOT NULL REFERENCES ops.pg_load_runs(run_id),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- The loader can insert and inspect data, but cannot truncate or delete it.
-- Test fixture: grant against the disposable database rather than a fixed name.
DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO retail_loader', current_database()); END $$;
GRANT USAGE ON SCHEMA staging, ops TO retail_loader;
GRANT SELECT, INSERT ON staging.iowa_sales_sample, staging.iowa_sales_exact TO retail_loader;
GRANT SELECT, INSERT, UPDATE ON ops.pg_load_runs TO retail_loader;
GRANT SELECT, INSERT ON ops.pg_loaded_exports TO retail_loader;
COMMIT;

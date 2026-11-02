-- Step 10B: controlled replacement of a complete audited source snapshot.
-- Requires migration 010. Run once as the administrative migration user.
BEGIN;
SET LOCAL lock_timeout = '10s';
SELECT pg_advisory_xact_lock(690011);
DO $$ BEGIN
 IF to_regclass('publication.current_snapshot') IS NULL THEN
  RAISE EXCEPTION 'Install migration 010 before snapshot ingestion';
 END IF;
END $$;
CREATE ROLE retail_snapshot_loader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE TABLE ops.snapshot_bundles (
 bundle_id TEXT PRIMARY KEY CHECK (bundle_id ~ '^[0-9a-f]{64}$'),
 manifest JSONB NOT NULL,
 bundle_path TEXT NOT NULL,
 registered_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE ops.snapshot_state (
 singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
 bundle_id TEXT REFERENCES ops.snapshot_bundles(bundle_id)
);
INSERT INTO ops.snapshot_state VALUES(TRUE,NULL);
CREATE TABLE ops.snapshot_load_attempts (
 run_id UUID PRIMARY KEY REFERENCES ops.pg_load_runs(run_id),
 bundle_id TEXT NOT NULL REFERENCES ops.snapshot_bundles(bundle_id),
 previous_export_sha256 TEXT,
 reason TEXT,
 accepted_removals BOOLEAN NOT NULL,
 accepted_row_decrease BOOLEAN NOT NULL
);
CREATE TABLE ops.source_build_state (
 singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
 valid BOOLEAN NOT NULL DEFAULT FALSE,
 source_identity JSONB,
 code_sha256 TEXT,
 dbt_invocation_id TEXT,
 completed_at TIMESTAMPTZ
);
INSERT INTO ops.source_build_state(singleton) VALUES(TRUE);

GRANT USAGE ON SCHEMA staging,ops TO retail_snapshot_loader;
GRANT SELECT,INSERT,TRUNCATE,MAINTAIN ON staging.iowa_sales_exact TO retail_snapshot_loader;
GRANT SELECT,INSERT,UPDATE ON ops.pg_load_runs,ops.pg_loaded_exports TO retail_snapshot_loader;
GRANT SELECT,INSERT ON ops.snapshot_bundles,ops.snapshot_load_attempts TO retail_snapshot_loader;
GRANT SELECT,UPDATE ON ops.snapshot_state TO retail_snapshot_loader;
GRANT SELECT ON ops.source_build_state TO retail_snapshot_loader;
GRANT UPDATE(valid) ON ops.source_build_state TO retail_snapshot_loader;
GRANT USAGE ON SCHEMA ops TO retail_dbt;
GRANT SELECT ON ops.pg_loaded_exports TO retail_dbt;
GRANT SELECT,UPDATE ON ops.source_build_state TO retail_dbt;
GRANT SELECT ON ops.source_build_state TO retail_publisher;
DO $$ BEGIN
 EXECUTE format('GRANT CONNECT,TEMPORARY ON DATABASE %I TO retail_snapshot_loader',current_database());
END $$;
COMMENT ON TABLE ops.source_build_state IS
'Full successful dbt build bound to registered source identity and dbt code; invalidated by source replacement or mutating dbt commands.';
COMMIT;

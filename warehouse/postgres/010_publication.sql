-- Step 10A: bootstrap an immutable-by-workflow monthly publication history.
-- PostgreSQL 17+. Run once as the administrative migration user.
-- No source or legacy fact rows are changed. Existing BI rows are copied first.
BEGIN;
SET LOCAL lock_timeout = '10s';
SELECT pg_advisory_xact_lock(690010);
CREATE SCHEMA publication;
REVOKE ALL ON SCHEMA publication FROM PUBLIC;
CREATE ROLE retail_publisher LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

CREATE TABLE publication.snapshots (
    snapshot_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('LEGACY_BOOTSTRAP', 'DBT_VALIDATED')),
    fingerprint TEXT CHECK (fingerprint IS NULL OR fingerprint ~ '^[0-9a-f]{64}$'),
    source_identity JSONB NOT NULL,
    evidence JSONB NOT NULL,
    month_count INTEGER NOT NULL CHECK (month_count > 0)
);
-- One bootstrap row identifies the BI snapshot that was already in service.
INSERT INTO publication.snapshots
SELECT gen_random_uuid(), clock_timestamp(), 'LEGACY_BOOTSTRAP', NULL,
       '{"kind":"legacy_marts"}'::JSONB,
       '{"validation":"existing_snapshot_preserved; not revalidated by migration 010"}'::JSONB,
       COUNT(*) FROM marts.bi_sales_monthly;

CREATE TABLE publication.monthly_snapshots AS
SELECT s.snapshot_id AS _snapshot_id, b.*
FROM publication.snapshots s CROSS JOIN marts.bi_sales_monthly b;
ALTER TABLE publication.monthly_snapshots
    ADD PRIMARY KEY (_snapshot_id, month_start),
    ADD FOREIGN KEY (_snapshot_id) REFERENCES publication.snapshots(snapshot_id);
CREATE TABLE publication.current_snapshot (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    snapshot_id UUID NOT NULL REFERENCES publication.snapshots(snapshot_id),
    switched_at TIMESTAMPTZ NOT NULL
);
INSERT INTO publication.current_snapshot
SELECT TRUE, snapshot_id, clock_timestamp() FROM publication.snapshots;

CREATE TABLE publication.runs (
    run_id UUID PRIMARY KEY,
    action TEXT NOT NULL CHECK (action IN ('PUBLISH', 'ROLLBACK')),
    state TEXT NOT NULL CHECK (state IN ('RUNNING','PUBLISHED','UNCHANGED','ROLLED_BACK','FAILED')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    finished_at TIMESTAMPTZ,
    snapshot_id UUID REFERENCES publication.snapshots(snapshot_id),
    previous_snapshot_id UUID REFERENCES publication.snapshots(snapshot_id),
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    error_message TEXT
);

-- Replacement keeps the view identity, names/types/order and existing BI grants.
CREATE OR REPLACE VIEW marts.bi_sales_monthly AS
SELECT
    p.month_start,
    p.calendar_year,
    p.calendar_month,
    p.source_records,
    p.active_stores,
    p.active_products,
    p.reported_sales_dollars,
    p.sales_bottles,
    p.reported_sales_liters,
    p.negative_sales_records,
    p.negative_sales_dollars,
    p.money_evaluable_records,
    p.money_mismatch_records,
    p.money_check_coverage_pct,
    p.money_mismatch_pct_of_evaluable,
    p.money_signed_difference,
    p.money_absolute_difference,
    p.reported_sales_dollars_absolute_evaluable,
    p.money_absolute_difference_pct,
    p.money_reconciliation_status,
    p.volume_evaluable_records,
    p.volume_mismatch_records,
    p.volume_check_coverage_pct,
    p.volume_mismatch_pct_of_evaluable,
    p.volume_absolute_difference,
    p.reported_sales_liters_absolute_evaluable,
    p.volume_absolute_difference_pct,
    p.volume_reconciliation_status,
    p.first_observed_date,
    p.last_observed_date,
    p.observed_sales_days,
    p.period_completeness_status,
    p.precision_review_period,
    p.prior_year_month_start,
    p.prior_year_reported_sales_dollars,
    p.reported_sales_yoy_difference,
    p.reported_sales_yoy_pct,
    p.yoy_calculation_status,
    p.yoy_caveats,
    p.kpi_policy,
    p.kpi_snapshot_validated_at
FROM publication.monthly_snapshots p
JOIN publication.current_snapshot c ON c.snapshot_id = p._snapshot_id;

GRANT USAGE ON SCHEMA publication, staging, dbt_dev, ops TO retail_publisher;
GRANT SELECT ON publication.snapshots, publication.monthly_snapshots,
    publication.current_snapshot, publication.runs TO retail_publisher;
GRANT INSERT ON publication.snapshots, publication.monthly_snapshots,
    publication.runs TO retail_publisher;
GRANT UPDATE ON publication.current_snapshot, publication.runs TO retail_publisher;
GRANT SELECT, MAINTAIN ON staging.iowa_sales_exact, ops.pg_loaded_exports TO retail_publisher;
-- MAINTAIN permits SHARE locks without granting INSERT/UPDATE/DELETE on source data.
GRANT SELECT, MAINTAIN ON ALL TABLES IN SCHEMA dbt_dev TO retail_publisher;
-- dbt replaces tables, so privileges must also apply to future objects it owns.
ALTER DEFAULT PRIVILEGES FOR ROLE retail_dbt IN SCHEMA dbt_dev
    GRANT SELECT, MAINTAIN ON TABLES TO retail_publisher;
DO $$ BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO retail_publisher', current_database());
    IF NOT has_table_privilege('retail_bi','marts.bi_sales_monthly','SELECT')
       OR has_table_privilege('retail_bi','publication.monthly_snapshots','SELECT')
       OR has_table_privilege('retail_publisher','staging.iowa_sales_exact','UPDATE') THEN
        RAISE EXCEPTION 'Publication permission boundary is not as expected';
    END IF;
END $$;
COMMENT ON VIEW marts.bi_sales_monthly IS
'Published monthly snapshot. Publication changes atomically; source completeness is not certified.';
COMMIT;

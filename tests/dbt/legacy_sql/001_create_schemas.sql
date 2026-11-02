-- Purpose:
--   Create the logical layers of the local analytics database.
--
-- Execution:
--   Run explicitly with psql after PostgreSQL is ready.
--
-- Repeatability:
--   Existing schemas are preserved. No tables or data are deleted.
--
-- Scope:
--   This script creates schemas only.
--   Pipeline users, permissions and tables will be added separately.

BEGIN;

-- Prevent ordinary users from creating objects in the public schema.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- Preserve source values and ingestion provenance.
CREATE SCHEMA IF NOT EXISTS raw;

-- Store typed, validated and deduplicated data.
CREATE SCHEMA IF NOT EXISTS staging;

-- Store business-facing analytical tables.
CREATE SCHEMA IF NOT EXISTS marts;

-- Store pipeline execution and data-quality metadata.
CREATE SCHEMA IF NOT EXISTS ops;

COMMIT;

-- Verify that all required schemas exist.
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name IN ('raw', 'staging', 'marts', 'ops')
ORDER BY schema_name;
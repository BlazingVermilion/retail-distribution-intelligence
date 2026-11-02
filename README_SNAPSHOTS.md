# Step 10B — Repeatable full-source snapshot refresh

## What changes

The existing audited export loader intentionally accepts only one export. This
release adds a dedicated replacement path for **complete source snapshots**, while
preserving published Power BI data until a new candidate passes validation.

The four explicit tasks are:

1. **prepare**: discover CSVs, fingerprint inputs, exact-deduplicate all selected years and retain a recoverable export bundle.
2. **load**: validate/stage that export, then replace the active source and its registry in one transaction.
3. **dbt build**: rebuild all nine models, run tests and bind successful build evidence to the current source and code.
4. **publish**: validate the current candidate and switch the independent monthly publication.

These are individual task entry points for the next Airflow phase. No custom
scheduler or alternative orchestration framework is introduced.

## Before merging

Requirements: existing step-9 dbt project, step-10A publication, the original
`scripts/audit_duplicates.py` version 2 and `scripts/load_postgres.py`, PostgreSQL
17 and Python 3.12 `.venv-dbt`. Keep all required stack components in scope:
Python, PostgreSQL, dbt, Airflow, Snowflake, AI reporting, Power BI and CI.

Back up or commit the project, then merge the ZIP contents into its root. This
overlay **replaces** `scripts/run_dbt.py` and `scripts/publish_snapshot.py` to add
coordination and current-source build checks. Review any local edits before
merging. It adds `snapshot_ingestion.py`, `warehouse_state.py`, migration 011,
tests, documentation and a CI workflow. Existing audit/initial-loader scripts,
raw data, `.env`, dbt SQL and Power BI files are not replaced.

## 1. Install dependencies and run offline checks

```powershell
.\.venv-dbt\Scripts\python.exe --version
.\.venv-dbt\Scripts\python.exe -m pip install -r requirements-snapshots.txt
.\.venv-dbt\Scripts\python.exe -m pip check
.\.venv-dbt\Scripts\python.exe -m unittest discover -s tests/snapshots -v
.\.venv-dbt\Scripts\python.exe -m unittest discover -s tests/publication -v
```

Expected: Python 3.12.x, no dependency conflicts, 16 snapshot/build-evidence tests
and 9 publication tests passing. Installing this release does not start a load.

## 2. Install migration 011 once

Do not run another ingestion, dbt or publication command during installation.

```powershell
docker compose exec postgres psql -U postgres -d retail_analytics -v ON_ERROR_STOP=1 -f /workspace/sql/011_snapshot_ingestion.sql
```

Expected: COMMIT. Do not rerun a successfully committed migration. It creates
metadata tables and a dedicated snapshot loader role; it does not replace source
rows or change the current Power BI snapshot.

Set the dedicated role password interactively:

```powershell
docker compose exec postgres psql -U postgres -d retail_analytics
```

At the psql prompt:

```text
\password retail_snapshot_loader
\q
```

Append the password to your existing `.env`:

```dotenv
PG_SNAPSHOT_PASSWORD='your-dedicated-snapshot-loader-password'
```

Retain the existing dbt/publisher settings. All task wrappers use the same
DBT_HOST / DBT_PORT / DBT_DATABASE settings and documented defaults. No database
administrator password is used by the snapshot loader.

Migration 011 starts the new build record as invalid. Before any subsequent
publish, a full `scripts/run_dbt.py build` must finish successfully. The existing
Power BI publication remains available while this happens.

## 3. Inspect the complete source collection

Expected structure: `data/raw/<YYYY>/*.csv`. Nested folders inside a year are
supported, and new years such as 2027 are discovered automatically. If your year
folders are under another directory, pass that directory as `--input-root` in
both plan and prepare commands.

```powershell
.\.venv-dbt\Scripts\python.exe scripts/snapshot_ingestion.py plan --input-root data/raw
```

Expected output: `PLANNED`, file count, discovered years and per-file SHA-256.
This reads/hashes files but does not write to PostgreSQL. Confirm all intended
years are included. Do not point it at only the newest month/year.

Input policy:

- The input root represents the **complete current collection** to be loaded.
- Keep one selected version of each upstream extract. Store superseded raw files
  outside the active input root so both old/new versions are not unintentionally
  included in the next exact-record union.
- Same-invoice records with different values remain distinct. No invoice-level
  correction/upsert rule is inferred.
- CSVs outside YYYY folders are rejected rather than silently omitted.
- Discovery uses contents, not modification times alone.

## 4. Prepare the retained bundle

```powershell
.\.venv-dbt\Scripts\python.exe scripts/snapshot_ingestion.py prepare --input-root data/raw
if ($LASTEXITCODE -ne 0) { throw "Snapshot preparation failed; do not continue" }
```

Expected: `PREPARED` on first preparation, or `REUSED` for an unchanged valid
bundle. Output lives under `artifacts/snapshots/<bundle_id>/`; `latest.json`
points to the last successfully prepared bundle.

A bundle includes:
- `manifest.json`: input inventory, audit implementation identity, export/summary hashes and row count.
- `exact_deduplicated.csv`: retained 23 source strings plus audit-local row ID.
- `summary.json`, `audit.sqlite` and audit/lineage reports from the existing auditor.

Inputs are fingerprinted before and after auditing. A changed inventory or
incomplete audit never becomes the new latest pointer. Keep previous bundles:
they are the source-recovery material, not disposable logs.

**The first preparation repeats the full audit over your complete dataset.**
It does not reuse an older unregistered audit directory automatically. With
17,337,629 retained rows, this can require substantial time and disk space for
SQLite, exports and reports. Unchanged future preparations reuse the bundle
although input hashes are still read. No incremental ingestion is claimed.

## 5. Load the prepared full snapshot

```powershell
.\.venv-dbt\Scripts\python.exe scripts/snapshot_ingestion.py load
if ($LASTEXITCODE -ne 0) { throw "Snapshot load failed; inspect the error before building" }
```

Default input: `artifacts/snapshots/latest.json`. To load one specific retained
bundle, use `--bundle artifacts/snapshots/<bundle_id>`.

Expected:
- `COMPLETED`: the candidate has been staged, checked, and committed as the active source.
- `SKIPPED`: the exact export and summary are already registered and the active row count matches.

An identical load preserves the completed-load registry's run ID. That avoids
creating a false new source identity on every retry. Different summary/provenance
bytes can require a new registered snapshot even if business rows are unchanged.

The first bundle may cause a complete source replacement even with unchanged
business data, because its retained audit location/provenance differs from the
original load. It must preserve the full intended population.

The loader creates a temporary candidate table and validates COPY/counts and
file hashes **before touching the active source**. Then it executes TRUNCATE,
INSERT and registry/build-state changes inside one transaction. Any failure in
that transaction restores the old source and registry. Published monthly data
is independent and is never written by the loader.

Disk must accommodate the candidate, active source during replacement, indexes,
WAL and later dbt replacement tables. Streaming avoids loading the whole CSV into
Python memory, but does not eliminate database or disk requirements.

## 6. Rebuild all dbt models

```powershell
.\.venv-dbt\Scripts\python.exe scripts/run_dbt.py build
if ($LASTEXITCODE -ne 0) { throw "dbt build failed; keep the existing Power BI publication" }
```

Expected: successful dbt build followed by `BUILD_VALIDATED` JSON. The record
binds current source export/summary/run identity, dbt code hash and invocation.
A `quality_observations` warning remains expected for the known source issues.

Use a **full** build here, without `--select`, `--exclude` or `--selector`.
A partial build or another mutating dbt command invalidates the certification;
it must not certify the whole snapshot. Do not enable `compare_legacy` on new
source snapshots: historical marts are migration references, not current truth.

This check matters even when the old and new exports have exactly the same
number of rows. A matching row count alone cannot prove that facts were built
from the new source.

## 7. Publish and refresh Power BI

```powershell
.\.venv-dbt\Scripts\python.exe scripts/publish_snapshot.py publish
if ($LASTEXITCODE -ne 0) { throw "Publication failed; the previous report remains active" }

.\.venv-dbt\Scripts\python.exe scripts/publish_snapshot.py status
```

Expected: `PUBLISHED`, or `UNCHANGED` if current source/code/report identity is
already published. Refresh Power BI Desktop normally. Keep the same
`marts.bi_sales_monthly` query and credentials.

## 8. Verify replay without duplicating data

With unchanged input, run prepare, load and publish again:

```powershell
.\.venv-dbt\Scripts\python.exe scripts/snapshot_ingestion.py prepare --input-root data/raw
if ($LASTEXITCODE -ne 0) { throw "Prepare failed" }
.\.venv-dbt\Scripts\python.exe scripts/snapshot_ingestion.py load
if ($LASTEXITCODE -ne 0) { throw "Load failed" }
.\.venv-dbt\Scripts\python.exe scripts/publish_snapshot.py publish
```

Expected: `REUSED`, `SKIPPED`, `UNCHANGED`. The successful full build from step 6
remains valid because a skipped identical load does not invalidate it. Do not
skip build after a changed load or changed dbt code.

## Recovery rules

| Failed task | State retained | Safe next action |
| --- | --- | --- |
| prepare | Previous latest pointer, database and publication | Fix source/schema and prepare again |
| candidate COPY or active replacement | Previous active source/registry; publication | Correct problem and retry load |
| dbt build | New active source, possibly partial development models; old publication | Fix code/data, then run a full build |
| publish | Old published snapshot | Resolve validation error; rebuild if required; retry publish |
| uncertain connection failure | Commit outcome may be unknown | Inspect registry/current pointer; replay the same bundle safely |

To restore the source from a previous retained bundle:

```powershell
.\.venv-dbt\Scripts\python.exe scripts/snapshot_ingestion.py load --bundle "artifacts/snapshots/PASTE-OLD-BUNDLE-ID" --reason "Restore previous source snapshot"
```

Then full build and publish. This source recovery is different from the existing
publication rollback, which only selects older monthly report rows.

If an intentional correction/removal reduces rows or removes source files, the
loader fails by default. Review the differences first; explicitly acknowledge
only the applicable condition:

```powershell
.\.venv-dbt\Scripts\python.exe scripts/snapshot_ingestion.py load --allow-row-decrease --accept-source-removals --reason "Describe the reviewed upstream correction"
```

These are operator decisions, not automatic cleanup flags. The first legacy load
has no comparable new-format inventory; the first bundle establishes that
baseline, while the row-decrease guard still applies. Row-count safeguards do
not establish full upstream period completeness.

## Coordination and audit boundaries

- Use `scripts/run_dbt.py`; direct `dbt.exe` bypasses warehouse coordination.
- A shared session lock permits tests/publication together. An exclusive lock
  serializes source loading and dbt transformations. Busy operations fail rather
  than queue indefinitely.
- Existing initial-loader lock 782902 is also acquired during source replacement.
- Power BI queries independent publication storage, so source replacement does
  not truncate the report's data.
- PostgreSQL TRUNCATE is transaction-safe but not MVCC-safe for unrelated old
  snapshots. Do not run unmanaged source queries/updates across a replacement.
  The coordinated project commands and independent BI source are the supported
  interfaces for this local implementation.
- A hard-killed preparation can leave `prepare.lock`. Check its PID and confirm
  no preparation process is running before manually removing the stale lock.
- Failed `.preparing-*` directories are retained for inspection and never loaded.
- A hard-killed database job can leave RUNNING history. Inspect the completed
  registry before retrying; also check for orphaned dbt processes before rebuild.
- Direct administrative SQL can bypass these safeguards. This is a trusted local
  workflow, not a tamper-proof or multi-tenant service.

Metadata: `ops.snapshot_bundles`, `ops.snapshot_state`,
`ops.snapshot_load_attempts`, `ops.source_build_state` and the existing
`ops.pg_load_runs` / `ops.pg_loaded_exports`.

Keep bundles until a retention/backup policy is implemented. They are outside git
under the already ignored `artifacts/` directory. Do not upload real exports or
credentials as CI artifacts.

## Validation and next phase

Read `docs/SNAPSHOT_VALIDATION.md` for checks actually executed. The new
`.github/workflows/snapshots.yml` runs the full Python/dbt/PostgreSQL 17 path on
synthetic data, including an insertion failure after TRUNCATE. Its execution has
not been observed here; files alone do not constitute a passing CI run.

After a local successful refresh and replay, the next implementation is Airflow:
prepare → load → full dbt build → publish, with visible retries and recovery.
Snowflake execution and evaluated AI reporting remain required afterwards.

References:
- https://www.postgresql.org/docs/17/sql-truncate.html
- https://www.postgresql.org/docs/17/functions-admin.html

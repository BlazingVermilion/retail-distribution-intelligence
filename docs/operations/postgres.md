# Operate the PostgreSQL warehouse

Run these PowerShell commands from the repository root. For the full dataset, use PostgreSQL 17, Python 3.12 and your local credentials. The [fixture demo](../getting_started.md) has no database prerequisites.

## Bootstrap an empty warehouse

Skip bootstrap on a populated installation. From the repository root, set the local passwords in .env and start the postgres service. Place original exports in data/raw/YYYY. Apply migrations with:

```powershell
docker compose exec postgres psql -U postgres -d retail_analytics -v ON_ERROR_STOP=1 -f /workspace/sql/001_create_schemas.sql
```

1. Apply 001 and 002 from [warehouse/postgres](../../warehouse/postgres) in order. Set the retail_loader password interactively using psql's `\password retail_loader`; put the matching PG_LOADER_PASSWORD in your local .env.
2. In a Python environment with requirements-postgres.txt installed, run the exact-row audit and load its retained export:
   ```powershell
   python scripts/audit_duplicates.py --input-root data/raw --years 2020 2021 2022 2023 2024 2025 2026 --output-dir artifacts/initial-audit
   python scripts/load_postgres.py --file artifacts/initial-audit/exact_deduplicated.csv --summary artifacts/initial-audit/summary.json
   ```
3. Apply migrations 003 through 008 in numeric order using the psql command above with the corresponding filename. These establish typed views, reconciliation, legacy marts and the BI reader. Set the retail_bi password interactively for Power BI.
4. Continue with migration 009 and dbt below, then initialize publication (010) and snapshot refresh (011). Stop if a command exits unsuccessfully; do not blindly rerun the initial migrations on an existing database.

## Model the source with dbt

Nine models reproduce the reviewed PostgreSQL transformations in `dbt_dev`:

| Model | Materialization | Responsibility |
| --- | --- | --- |
| stg_iowa_sales | View | Normalize blank strings, safe types, missing/invalid flags |
| int_sales_reconciled | View | Reported/calculated diagnostics without corrections |
| fact_sales | Table | Retain every exact-deduplicated record and lineage |
| dim_store | Table | Latest observed store attributes |
| dim_product | Table | Latest observed product attributes |
| dim_date | Table | Continuous calendar |
| sales_monthly | Table | Aggregate observed months with preservation controls |
| v_sales_monthly_kpis | View | Coverage, discrepancy ratios and exact-month YoY |
| bi_sales_monthly | View | Scalar-column development preview of the BI contract |

There are 34 dbt tests when legacy comparisons are enabled: 27 ordinary tests
and 7 parity tests. One ordinary test deliberately reports known source-quality
findings as warnings. Structural and preservation checks use error severity.
Fact parity compares counts, non-NULL counts and numeric sums; it is not a
byte-for-byte comparison of every descriptive fact field. Dimension, monthly,
KPI and BI comparisons are bidirectional row comparisons. The BI comparison
excludes only the snapshot-validation timestamp.

`dbt_dev.bi_sales_monthly.kpi_snapshot_validated_at` is NULL deliberately. This
preview is not a published snapshot and does not invent a successful audit.
Power BI must continue reading **marts.bi_sales_monthly** with `retail_bi`.
The dbt account cannot write the existing warehouse schemas.

### Install into a separate Python environment

Run in PowerShell from your existing project root:

```powershell
python --version
python -m venv .venv-dbt
.\.venv-dbt\Scripts\python.exe -m pip install -r requirements-dbt.txt
```

Use Python 3.12 for the documented setup (CI also targets 3.12). This environment
is independent of the ingestion `.venv`; you do not need to activate either one
when using the explicit interpreter paths below. No external dbt packages are
required, so there is no `dbt deps` step.

### Create the development account and schema once

Your existing Compose bind mount exposes `warehouse/postgres` as `/workspace/sql`.

```powershell
docker compose ps
docker compose exec postgres psql -U postgres -d retail_analytics -v ON_ERROR_STOP=1 -f /workspace/sql/009_dbt_access.sql
```

Expected result: CREATE ROLE, CREATE SCHEMA, GRANT and COMMIT. The script
intentionally fails if `retail_dbt` or `dbt_dev` already exists. After a successful
run, skip this step on subsequent sessions. Do not drop the schema to silence an
unexpected error; inspect it first.

Set a **new dedicated password** interactively:

```powershell
docker compose exec postgres psql -U postgres -d retail_analytics
```

At the psql prompt:

```text
\password retail_dbt
\q
```

Enter the new password twice when prompted. It is not your Power BI or loader
password. No password is stored in the migration.

### Add dbt settings to your existing local .env

Open `.env` and append the following, replacing the placeholder with the password
just assigned. Keep all existing lines unchanged.

```dotenv
DBT_ENV_SECRET_PASSWORD='replace-with-your-retail-dbt-password'
DBT_HOST=127.0.0.1
```

The wrapper reads `POSTGRES_PORT` and `POSTGRES_DB` from your existing `.env`.
If you need explicit overrides, add `DBT_PORT=5433` and
`DBT_DATABASE=retail_analytics`. Existing shell variables take precedence over
`.env`. Use valid dotenv quoting if your password contains quotes or special
characters. Never commit `.env` or paste it into a public issue.

The `DBT_ENV_SECRET_` prefix supports dbt's secret handling; it does not replace
protecting your local credential file.

### Check connectivity

```powershell
.\.venv-dbt\Scripts\python.exe scripts/run_dbt.py debug
```

Confirm the connection test passes for `retail_dbt`, database `retail_analytics`,
schema `dbt_dev`, port `5433`. If authentication fails, reset the dedicated
password and update its `.env` entry. If connection is refused, inspect
`docker compose ps` and the host port.

### Build and test the development snapshot

Keep the loaded source unchanged throughout this run. Do not run ingestion or
another dbt build concurrently. The current project does not yet implement
cross-model snapshot isolation or orchestration locks.

```powershell
.\.venv-dbt\Scripts\python.exe scripts/run_dbt.py build
if ($LASTEXITCODE -ne 0) { throw "dbt build failed; inspect dbt/logs/dbt.log" }
```

This reads all currently loaded years; no year list or CSV filenames are needed.
It reads `staging.iowa_sales_exact`, not `data/raw`, so it uses the already
exact-deduplicated population and does not deduplicate by invoice again.

Expect a full scan and a new fact table containing your 17,337,629 rows, if the
source has not changed. This will take time and additional disk space. Subsequent
builds also rebuild tables; dbt may temporarily hold both old and replacement
development tables. This is deliberately not an incremental implementation.

A WARN for `quality_observations` is expected for missing prices and known
mismatches. It is not a reason to overwrite reported values. Any ERROR/FAIL must
be investigated before moving forward. `run_results.json` is the evidence;
a completed model alone does not mean all its tests passed.

### Compare with your existing marts

Run this only while the source and legacy marts still represent the same export:

```powershell
.\.venv-dbt\Scripts\python.exe scripts/run_dbt.py test --select tag:parity --vars 'compare_legacy: true'
if ($LASTEXITCODE -ne 0) { throw "Legacy parity failed; keep Power BI on existing marts" }
```

Expected: all seven parity tests PASS. A failure after changing the source may
mean the old marts are stale; do not rerun migrations 006/007 as a refresh or
relax tests just to make the comparison pass.

Inspect counts and some monthly outputs:

```powershell
docker compose exec postgres psql -U postgres -d retail_analytics -P pager=off -c "SELECT COUNT(*) AS fact_rows FROM dbt_dev.fact_sales;"
docker compose exec postgres psql -U postgres -d retail_analytics -P pager=off -c "SELECT month_start, reported_sales_dollars, reported_sales_yoy_pct, money_reconciliation_status FROM dbt_dev.v_sales_monthly_kpis ORDER BY month_start DESC LIMIT 12;"
```

### Generate lineage documentation

```powershell
.\.venv-dbt\Scripts\python.exe scripts/run_dbt.py docs generate
.\.venv-dbt\Scripts\python.exe scripts/run_dbt.py docs serve --port 8081
```

Open `http://localhost:8081`. Use the lineage graph to inspect source → staging
→ reconciliation → fact → monthly KPIs. Stop the local server with Ctrl+C.
Do not commit generated logs or the `target` directory. Save run evidence outside
git when needed for portfolio screenshots or issue investigation.

## Publish validated monthly KPIs

### Behavior

| Situation | Outcome |
| --- | --- |
| Initial migration | Copy the current BI rows into a retained legacy snapshot; preserve the 41-column view contract and BI grants |
| Successful publish | Lock source/models, run fresh dbt tests, copy validated monthly rows, switch the current pointer in one transaction |
| Identical current content, source identity and code | Revalidate, return UNCHANGED, create no extra snapshot |
| Known source-quality warning | Retain the warning in snapshot evidence; publication may proceed |
| Failed/skipped/missing test or unexpected warning | Fail publication; retain the existing pointer and rows |
| Source/model write in progress | Wait at most five seconds for each lock, then fail safely if unavailable |
| Another publisher in progress | Fail immediately on the publication advisory lock |
| Rollback | Switch to a retained snapshot with a required operator reason |

Source and model data locks permit reads but prevent writes and dbt table swaps
while the publication tests run. View definitions are protected with ACCESS SHARE
locks. MAINTAIN privileges allow the publisher to acquire stronger table locks
without receiving source INSERT, UPDATE, DELETE or TRUNCATE privileges.

A transaction makes the pointer change atomic for each database statement. A
Power BI Import report still requires Refresh to load the new snapshot into its
local model. Multiple separate queries spanning a switch can observe different
committed snapshots; this release does not coordinate multi-query refreshes.

### Prerequisites

- A completed dbt build with working Python 3.12 `.venv-dbt`, PostgreSQL 17 and dbt models.
- Successful dbt build and migration parity checks already reviewed locally.
- The original `ops.pg_loaded_exports` full-export registry entry is present.
- No ingestion, dbt build or manual model edits during publication.
- Your current source and dbt models are trusted project assets. Tests establish
  defined contracts, not the correctness of every upstream business value.

### Install the publication dependency

In PowerShell, from the project root:

```powershell
.\.venv-dbt\Scripts\python.exe --version
.\.venv-dbt\Scripts\python.exe -m pip install -r requirements-publication.txt
.\.venv-dbt\Scripts\python.exe -m pip check
.\.venv-dbt\Scripts\python.exe -m unittest discover -s tests/publication -v
```

Expected: Python 3.12.x, no dependency conflicts, nine offline tests passing.
The `(.venv)` prefix is irrelevant when invoking the full `.venv-dbt` path.

### Install publication storage once

```powershell
docker compose exec postgres psql -U postgres -d retail_analytics -v ON_ERROR_STOP=1 -f /workspace/sql/010_publication.sql
```

This migration runs inside a transaction. It copies the existing BI result,
creates the publication tables/role and replaces the view's query while keeping
its name and column contract. It does not copy the 17-million-row fact table.

Expected: COMMIT. Do not rerun after success: existing schema/role errors are
intentional. If an error occurs before commit, the migration rolls back.

Set the dedicated publisher password interactively:

```powershell
docker compose exec postgres psql -U postgres -d retail_analytics
```

At the psql prompt:

```text
\password retail_publisher
\q
```

Append to your existing `.env`, using the password you just assigned:

```dotenv
PG_PUBLISHER_PASSWORD='replace-with-your-dedicated-publisher-password'
```

Keep `DBT_ENV_SECRET_PASSWORD` and all existing settings. Publication uses the
same host, port and database settings as the step-9 dbt wrapper. No administrative
password is used by the publication script. Do not commit `.env`.

### Inspect the bootstrap snapshot

```powershell
.\.venv-dbt\Scripts\python.exe scripts/publish_snapshot.py status
```

Expect a `LEGACY_BOOTSTRAP` snapshot with `is_current: true`. Record its
`snapshot_id` if you want to demonstrate rollback later. This row preserves your
existing report; it is not presented as a newly validated dbt snapshot.

### Publish the completed dbt output

```powershell
.\.venv-dbt\Scripts\python.exe scripts/publish_snapshot.py publish
```

The script deliberately runs dbt tests again while holding locks. A previous
successful run alone would not prove that the candidate has stayed unchanged.
The existing fact is scanned by tests but not rebuilt or recopied.

Do not run `dbt build` concurrently. Tests may take time on 17,337,629 rows.
The default test timeout is 7,200 seconds. If needed, set a documented override:

```powershell
.\.venv-dbt\Scripts\python.exe scripts/publish_snapshot.py publish --test-timeout 10800
```

Expected final JSON includes `state: PUBLISHED`, `snapshot_id`,
`previous_snapshot_id`, a fresh dbt `invocation_id`, and test/warning evidence.
A normal publication checks 27 tests. The seven migration parity tests are
excluded: comparing all future snapshots to the old static marts is not a
valid ongoing publication gate.

Only the known `quality_observations` warning is accepted. Unexpected warnings,
failed/skipped/missing tests, changed code, an empty result or a mismatched BI
contract abort publication. This preserves source-reported numbers; it does not
repair mismatches, fill missing prices or certify completeness.

### Verify and refresh Power BI

```powershell
.\.venv-dbt\Scripts\python.exe scripts/publish_snapshot.py status

docker compose exec postgres psql -U postgres -d retail_analytics -P pager=off -c "SELECT COUNT(*) AS months, MIN(month_start) AS first_month, MAX(month_start) AS last_month, MIN(kpi_snapshot_validated_at) AS validated_at FROM marts.bi_sales_monthly;"
```

In Power BI Desktop, use **Home → Refresh**. Keep the existing server/database,
`retail_bi` account and `marts.bi_sales_monthly` source. Do not change the query to
`dbt_dev`, and do not import the publication history tables.

Legacy `marts.fact_sales`, `marts.sales_monthly` and `marts.v_sales_monthly_kpis`
remain historical comparison objects. After this migration, the BI view has a
separate publication lifecycle. Do not assume those legacy tables refresh when
publication changes.

### Demonstrate idempotence

Run the same publish command again with unchanged code/source/models:

```powershell
.\.venv-dbt\Scripts\python.exe scripts/publish_snapshot.py publish
```

Expected: `state: UNCHANGED`, the same snapshot ID, and no extra snapshot rows.
Tests run again and the attempt is recorded in `publication.runs`.
Fingerprinting includes executable dbt project files, registered source identity
and ordered JSONB monthly business rows. Validation timestamps are excluded.
Source registry metadata is trusted provenance from the existing loader, not a
fresh rehash of all raw CSV files. The prepare task handles input rediscovery.

### Optional recovery demonstration

List retained snapshot IDs with `status`. To return to the bootstrap snapshot:

```powershell
.\.venv-dbt\Scripts\python.exe scripts/publish_snapshot.py rollback --snapshot "PASTE-BOOTSTRAP-UUID-HERE" --reason "Recovery demonstration after first dbt publication"
```

Expected: `ROLLED_BACK`. Refresh Power BI if you want to observe that version.
To restore the validated snapshot, repeat `rollback` with its UUID and an
appropriate reason. The command selects retained data; it does not mutate the
snapshot rows or rerun dbt tests.

Do not intentionally corrupt your local 17-million-row project to test failure.
The integration test performs fault injection only in an empty disposable
`*_ci` database. It is not a command to run against `retail_analytics`.

### Auditing, permissions and limitations

- `publication.snapshots`: retained snapshot metadata, source identity and evidence.
- `publication.monthly_snapshots`: retained 41-column BI rows with a snapshot ID.
- `publication.current_snapshot`: the one active pointer.
- `publication.runs`: attempts, outcomes and rollback reasons.
- `artifacts/publication/<run_id>/`: fresh dbt manifest, results and logs.

Publisher has SELECT/INSERT on snapshot storage and cannot UPDATE/DELETE existing
snapshot rows. Direct INSERT access is an operational trust boundary; only use
the CLI for publication. This is not tamper-proof storage or an adversarial audit
system. No SECURITY DEFINER superuser functions are introduced.

Caught failures are recorded as FAILED after rollback. A hard kill or connection
loss can leave a RUNNING attempt. Do not assume RUNNING means active or failed:
inspect the current pointer and run history before retrying. The pointer and
PUBLISHED state commit together; a retry after an uncertain commit is safe and
can return UNCHANGED. History is retained; automatic cleanup is not implemented.

Changes to the BI schema require an explicit migration. All 41 column names,
order and PostgreSQL types must match before publication proceeds.

## Refresh a complete source snapshot

### Install dependencies and run offline checks

```powershell
.\.venv-dbt\Scripts\python.exe --version
.\.venv-dbt\Scripts\python.exe -m pip install -r requirements-snapshots.txt
.\.venv-dbt\Scripts\python.exe -m pip check
.\.venv-dbt\Scripts\python.exe -m unittest discover -s tests/snapshots -v
.\.venv-dbt\Scripts\python.exe -m unittest discover -s tests/publication -v
```

Expected: Python 3.12.x, no dependency conflicts, 16 snapshot/build-evidence tests
and 9 publication tests passing. Installing this release does not start a load.

### Install migration 011 once

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

### Inspect the complete source collection

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

### Prepare the retained bundle

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

### Load the prepared full snapshot

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

### Rebuild all dbt models

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

### Publish and refresh Power BI

```powershell
.\.venv-dbt\Scripts\python.exe scripts/publish_snapshot.py publish
if ($LASTEXITCODE -ne 0) { throw "Publication failed; the previous report remains active" }

.\.venv-dbt\Scripts\python.exe scripts/publish_snapshot.py status
```

Expected: `PUBLISHED`, or `UNCHANGED` if current source/code/report identity is
already published. Refresh Power BI Desktop normally. Keep the same
`marts.bi_sales_monthly` query and credentials.

### Verify replay without duplicating data

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

### Recovery rules

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

### Coordination and audit boundaries

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

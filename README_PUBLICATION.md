# Step 10A — Validated monthly snapshot publication

## Purpose and scope

Publish the existing dbt monthly output without exposing partially rebuilt models
to Power BI. A publication is an independent copy of monthly rows plus metadata.
The existing `marts.bi_sales_monthly` view reads the currently selected snapshot.

This is the publication half of step 10. **New-export ingestion, automatic file
change discovery and end-to-end snapshot replacement remain step 10B.** The
existing loader still rejects a different export in its populated target. Do not
truncate the staging table or edit its load registry to bypass that safeguard.

This release does not introduce Airflow scheduling, Snowflake execution or AI
reporting. These remain required subsequent phases in the architecture baseline.
The publication CLI is one task that Airflow will call later, not a scheduler.

## Behavior

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

## Prerequisites

- Completed step 9 with working Python 3.12 `.venv-dbt`, PostgreSQL 17 and dbt models.
- Successful dbt build and migration parity checks already reviewed locally.
- The original `ops.pg_loaded_exports` full-export registry entry is present.
- No ingestion, dbt build or manual model edits during publication.
- Your current source and dbt models are trusted project assets. Tests establish
  defined contracts, not the correctness of every upstream business value.

## 1. Merge this overlay

Back up or commit your project. Copy the contents of the ZIP's
`retail-distribution-intelligence` directory into the existing project root.
Keep `.env`, data, existing SQL, Power BI files and the step-9 dbt directory.

Most files are additions. The overlay updates the architecture baseline and one
**test-only** legacy SQL fixture: `tests/dbt/legacy_sql/002_postgres_loader.sql`.
That fixture now grants CONNECT on the disposable database instead of hard-coding
`retail_analytics`. Your actual migration 002 is not replaced.

## 2. Install the publication dependency

In PowerShell, from the project root:

```powershell
.\.venv-dbt\Scripts\python.exe --version
.\.venv-dbt\Scripts\python.exe -m pip install -r requirements-publication.txt
.\.venv-dbt\Scripts\python.exe -m pip check
.\.venv-dbt\Scripts\python.exe -m unittest discover -s tests/publication -v
```

Expected: Python 3.12.x, no dependency conflicts, nine offline tests passing.
The `(.venv)` prefix is irrelevant when invoking the full `.venv-dbt` path.

## 3. Install publication storage once

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

## 4. Inspect the bootstrap snapshot

```powershell
.\.venv-dbt\Scripts\python.exe scripts/publish_snapshot.py status
```

Expect a `LEGACY_BOOTSTRAP` snapshot with `is_current: true`. Record its
`snapshot_id` if you want to demonstrate rollback later. This row preserves your
existing report; it is not presented as a newly validated dbt snapshot.

## 5. Publish the completed dbt output

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

## 6. Verify and refresh Power BI

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

## 7. Demonstrate idempotence

Run the same publish command again with unchanged code/source/models:

```powershell
.\.venv-dbt\Scripts\python.exe scripts/publish_snapshot.py publish
```

Expected: `state: UNCHANGED`, the same snapshot ID, and no extra snapshot rows.
Tests run again and the attempt is recorded in `publication.runs`.
Fingerprinting includes executable dbt project files, registered source identity
and ordered JSONB monthly business rows. Validation timestamps are excluded.
Source registry metadata is trusted provenance from the existing loader, not a
fresh rehash of all raw CSV files. Step 10B will handle input rediscovery.

## 8. Optional recovery demonstration

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

## Auditing, permissions and limitations

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

## Validation and CI

See `docs/PUBLICATION_VALIDATION.md` for executed checks and their limits.
The new `.github/workflows/publication.yml` runs the actual Python/dbt path on
PostgreSQL 17 with synthetic input. This workflow has been supplied but has not
been observed running in GitHub Actions during preparation.

Optional SQL smoke test (requires Node/npm; not needed for normal usage):

```powershell
npm --prefix tests/publication install
npm --prefix tests/publication test
```

## Next: step 10B, then Airflow

Implement versioned loading of new exact-deduplicated exports, file fingerprints,
changed-input handling and recoverable rebuilds. Keep the last published monthly
snapshot available when ingestion or dbt fails. Then attach the implemented tasks
to Airflow, execute the Snowflake path, and build evaluated AI reporting.

References:
- https://www.postgresql.org/docs/17/sql-lock.html
- https://www.postgresql.org/docs/17/sql-createview.html

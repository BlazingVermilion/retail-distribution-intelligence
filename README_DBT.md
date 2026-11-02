# Step 9: PostgreSQL dbt migration

This is an **overlay**, not a complete replacement repository. Merge its contents
into the existing `retail-distribution-intelligence` directory. It adds dbt and a
separate CI workflow. Keep the current source data, SQL migrations, scripts,
Power BI report, root README and `.env`.

## What this release does

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

## 1. Merge the overlay

1. Back up or commit your current project.
2. Extract this ZIP outside the project directory.
3. Copy the **contents** of its `retail-distribution-intelligence` directory into
   your existing project. Do not create a nested project directory.
4. Merge the supplied `.gitignore` if you have local additions. The version in
   this ZIP preserves the uploaded rules and adds `.venv-dbt/` and dbt metadata.
5. Do not copy any example password over your existing database password.

Expected new paths include `dbt/dbt_project.yml`, `requirements-dbt.txt`,
`scripts/run_dbt.py`, `warehouse/postgres/009_dbt_access.sql`, and
`.github/workflows/dbt.yml`.

## 2. Install into a separate Python environment

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

## 3. Create the development account and schema once

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

## 4. Add dbt settings to your existing local .env

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

## 5. Check connectivity

```powershell
.\.venv-dbt\Scripts\python.exe scripts/run_dbt.py debug
```

Confirm the connection test passes for `retail_dbt`, database `retail_analytics`,
schema `dbt_dev`, port `5433`. If authentication fails, reset the dedicated
password and update its `.env` entry. If connection is refused, inspect
`docker compose ps` and the host port.

## 6. Build and test the development snapshot

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

## 7. Compare with your existing marts

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

## 8. Generate lineage documentation

```powershell
.\.venv-dbt\Scripts\python.exe scripts/run_dbt.py docs generate
.\.venv-dbt\Scripts\python.exe scripts/run_dbt.py docs serve --port 8081
```

Open `http://localhost:8081`. Use the lineage graph to inspect source → staging
→ reconciliation → fact → monthly KPIs. Stop the local server with Ctrl+C.
Do not commit generated logs or the `target` directory. Save run evidence outside
git when needed for portfolio screenshots or issue investigation.

## Validation included in this delivery

See `docs/DBT_VALIDATION.md` for the exact checks executed while preparing this
release and the runtime checks that remain unverified. The supplied integration
workflow uses a disposable PostgreSQL 17 service and synthetic fixtures, never
your production extracts or uploaded credentials.

The legacy SQL copies in `tests/dbt/legacy_sql` are test reference fixtures.
**Do not run that directory against your current database.** The integration
runner additionally requires an empty database whose name ends in `_ci`.

## Architecture boundaries and next steps

This release implements the development dbt migration. It does not publish a new
BI snapshot or claim Airflow/Snowflake/AI completion. See
`docs/PROJECT_ARCHITECTURE_BASELINE.md` for the mandatory full scope.

Next, after your local build/parity results pass: implement repeatable snapshot
ingestion and safe publication, then Airflow orchestration, actual Snowflake
execution/comparison, and evaluated AI reporting. PostgreSQL-specific arrays,
conversion functions and DISTINCT ON still need a tested Snowflake adapter path.

Reference documentation:
- https://docs.getdbt.com/docs/core/connect-data-platform/postgres-setup
- https://docs.getdbt.com/reference/dbt-jinja-functions/env_var
- https://docs.getdbt.com/reference/commands/build

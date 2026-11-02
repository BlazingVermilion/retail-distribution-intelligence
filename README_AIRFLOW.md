# Step 11: Run the Iowa refresh through Airflow

The DAG runs on demand. Its four tasks use the existing audit, snapshot loader,
dbt wrapper, and publication gate. Airflow owns dependencies, retries, task
logs and run history. Power BI continues to read marts.bi_sales_monthly; a
failed build cannot expose partially rebuilt models through that view.

## 1. Install the overlay on Windows

Start in the existing project root, beside compose.yaml and .env. The ZIP has
no enclosing project folder. Extract it here. It updates the step 10B versions
of scripts/warehouse_state.py and docs/PROJECT_ARCHITECTURE_BASELINE.md.
If you edited either locally, merge your changes first. No warehouse migration
is included. Leave your raw data, Power BI files, and existing named volumes in place.

Prerequisites: the complete step 10B installation, warehouse migrations through
011, all three application-role passwords in .env, and Python 3.12. Keep the
full set of intended source years under data/raw/YYYY. If you have been using a
different raw root, set RDI_RAW_DIR in the current PowerShell session to its
absolute path before running Compose. Do not point this at a single year.

Run these from the project root (stop at a nonzero exit):

```powershell
.\.venv-dbt\Scripts\python.exe airflow/setup_local.py
.\.venv-dbt\Scripts\python.exe -m unittest discover -s tests/airflow -v
$af = @('-f','compose.yaml','-f','compose.airflow.yaml')
docker compose @af config --quiet
docker compose @af up -d postgres
docker compose @af exec postgres psql -U postgres -d retail_analytics -c "SELECT valid, completed_at FROM ops.source_build_state; SELECT snapshot_id FROM publication.current_snapshot;"
```

Setup only appends missing, randomly generated Airflow settings to your local
.env. Do not commit .env or paste its contents into an issue. If a required
object or password is missing, finish README_SNAPSHOTS.md before triggering.
The DAG does not create application accounts. A false build flag means a full
build is required; the DAG includes that build.

## 2. Start Airflow and check its connections

```powershell
docker compose @af build airflow-init
docker compose @af up -d airflow-api airflow-dag-processor airflow-scheduler
docker compose @af ps -a
docker compose @af exec airflow-scheduler airflow dags list-import-errors
docker compose @af exec airflow-scheduler airflow tasks list retail_snapshot_pipeline
```

The image includes dbt in a separate Python 3.12 environment. The metadata
database and migration start as dependencies: airflow-init should exit with
code 0; airflow-api and airflow-scheduler should become healthy. The DAG
processor takes a moment to discover the file. If it is still absent, inspect
the import errors and the dag-processor logs. Do not use a bare
`docker compose config` in shared output: expanded configuration contains secrets.

Verify the file mount and dbt connection before triggering the expensive run:

```powershell
docker compose @af exec airflow-scheduler python -c "from pathlib import Path; r=Path('/opt/project/data/raw'); print(sorted(p.name for p in r.iterdir() if p.is_dir())); print('CSV files:',sum(1 for p in r.rglob('*') if p.is_file() and p.suffix.lower()=='.csv'))"
docker compose @af exec airflow-scheduler /opt/airflow/pipeline-venv/bin/python /opt/project/scripts/run_dbt.py debug
```

Check that the years match your intended full collection and that CSV files are
present. In containers the warehouse is postgres:5432; on Windows it remains
127.0.0.1:5433 by default. The separate airflow-meta database stores orchestration
metadata only. Allow disk space for any new audit bundle, PostgreSQL candidate,
WAL and rebuilt fact table. Reuse the existing artifacts/snapshots directory.

## 3. Trigger one real refresh

Open http://localhost:8088. The local SimpleAuthManager user is **analyst**.
Read its generated password on your own terminal:

```powershell
docker compose @af exec airflow-api cat /opt/airflow/simple_auth_manager_passwords.json.generated
```

If the credentials file is not there yet, open the UI and check that the API
server finished starting. Recreating that container can regenerate the password.
Do not share the password or unredacted API startup logs. In **Dags**, open
**retail_snapshot_pipeline**, unpause it, then select **Trigger** once. No JSON
configuration is needed. The DAG has no automatic schedule or catch-up.
Open the run's task grid and select each task's logs.

| Task | Successful outcome | Where to look |
| --- | --- | --- |
| prepare | PREPARED or REUSED; exact duplicates removed across all years by the existing auditor | Bundle path, row count and per-run receipt |
| load | COMPLETED when replacement is necessary, SKIPPED when both registered hashes match | Load attempt ID and active input changes |
| dbt_build | A full build of all nine models and BUILD_VALIDATED | dbt invocation ID, test results and source identity |
| publish | PUBLISHED or UNCHANGED after fresh validation | Snapshot ID, prior ID, test warnings, evidence directory |

Run IDs map to artifacts/airflow/<sha256-of-Airflow-run-id>/. The receipt pins
input and summary hashes so load does not follow a mutable latest.json. A
coordinated source replacement between tasks is detected when building/publishing.
LocalExecutor runs tasks on the scheduler. Only one run is active; avoid manual
warehouse updates during a run. No approval flags for source removal or reduced
row counts are supplied by the DAG.

## 4. Verify publication and replay

```powershell
docker compose @af exec postgres psql -U postgres -d retail_analytics -P pager=off -c "SELECT run_id, state, snapshot_id, previous_snapshot_id FROM publication.runs ORDER BY started_at DESC LIMIT 4;"
docker compose @af exec postgres psql -U postgres -d retail_analytics -c "SELECT COUNT(*) AS months, MAX(month_start) AS latest_month FROM marts.bi_sales_monthly;"
```

Trigger a second, new DAG run without changing any input or model. Expect
REUSED, SKIPPED, a successful build and UNCHANGED. Compare the two **Airflow**
publication IDs. The first Airflow run can legitimately produce a new snapshot
if source identity changed from an earlier manual run. A new test invocation ID
or artifacts hash alone does not require a new published snapshot. In Power BI
Desktop click Refresh to read the published snapshot.

For your portfolio, keep the two DAG IDs and durations, task grid, input row
count, both publication results and warning details. A warning about 81 monthly
quality observations is different from 81 failed dbt tests.

## 5. Demonstrate a failure and recovery without editing real input

Do this only with the scheduler idle. Note the currently published snapshot ID.
The following commands temporarily mount a separate directory containing one
malformed CSV. The expected failure is in prepare; load/build/publish must not
execute. No real source file needs to be edited.

```powershell
$oldRaw = $env:RDI_RAW_DIR
$demo = Join-Path $PWD 'artifacts/airflow-drill-input'
New-Item -ItemType Directory -Force "$demo/2025" | Out-Null
Set-Content -Encoding ascii "$demo/2025/bad.csv" @('invalid_header','broken')
$env:RDI_RAW_DIR = $demo
docker compose @af up -d --no-deps airflow-scheduler
```

Trigger a **new** DAG run. Inspect the header failure and confirm the same
current snapshot and queryable BI view using section 4. Once the run finishes,
restore the real raw mount before retrying:

```powershell
if ($null -eq $oldRaw) { Remove-Item Env:RDI_RAW_DIR } else { $env:RDI_RAW_DIR = $oldRaw }
docker compose @af up -d --no-deps airflow-scheduler
```

Verify the years and file count again. In the failed run, clear **prepare and
its downstream tasks** for that run only; do not include past/future runs.
Follow the corrected run to success. This drill proves failure handling before
ingestion. Use the isolated step 10 publication integration fixture to exercise
a candidate that fails dbt validation; do not corrupt production marts to
demonstrate that separate failure mode.

## Operations and troubleshooting

- If prepare sees no CSVs: verify the host mount and YYYY directories. If it
  reports an existing prepare.lock after a hard stop, confirm no preparer on
  Windows or inside Docker is running before removing a stale lock.
- If load rejects a reduced row count or missing old input paths: compare the
  inventory with the intended full source. An exceptional source correction
  requires the separate documented step 10B procedure and a recorded reason.
- If dbt fails, inspect its first error, not the downstream upstream_failed
  status. A failed run can leave newer staging/models while the previous
  published BI snapshot remains readable. Check publication.runs and the
  current pointer after any worker interruption around commit.
- If the API port is occupied, set RDI_AF_PORT to another free host port,
  recreate airflow-api, and use that port in your browser.
- To stop the Airflow services while keeping the warehouse running:
  `docker compose @af stop airflow-scheduler airflow-dag-processor airflow-api airflow-meta`.
  Start again with section 2. Do not run **down -v** on the combined Compose project.
- If you open a new PowerShell window, define $af again. Restore any non-default
  raw path/port settings before starting Compose.

## Validation boundary

The DAG imported under Apache Airflow 3.1.7 / Python 3.12. Three offline
regressions exercised the real CSV preparation path, a corrected retry, a
run-specific load handoff with a mocked database loader, and rejection of a
different registered source. This is not evidence of a successful Docker DAG
run against the full Iowa warehouse. Record that separately on the target host.
The supplied .github/workflows/airflow.yml builds the runtime and repeats the DAG and fixture checks on GitHub; no remote CI execution is claimed. Snowflake execution and evaluated AI reporting follow the orchestration milestone.

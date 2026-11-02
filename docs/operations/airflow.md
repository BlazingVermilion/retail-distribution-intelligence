# Run Airflow and the monthly brief

The manual DAG prepares the input, loads PostgreSQL, builds dbt and publishes a snapshot. Reporting and the optional Snowflake mirror then consume that run’s publication receipt.

## Start the local services

Prerequisites: a validated source snapshot, warehouse migrations through
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
object or password is missing, finish the PostgreSQL guide in this directory before triggering.
The DAG does not create application accounts. A false build flag means a full
build is required; the DAG includes that build.

### Start Airflow and check its connections

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

### Trigger one real refresh

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
| report | RENDERED or REUSED for the pinned publication | Run-specific reporting receipt |
| sync_snowflake | Optional: INSERTED or UNCHANGED with verified readback | Run-specific cloud receipt |
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

### Verify publication and replay

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

## Troubleshooting

- If prepare sees no CSVs: verify the host mount and YYYY directories. If it
  reports an existing prepare.lock after a hard stop, confirm no preparer on
  Windows or inside Docker is running before removing a stale lock.
- If load rejects a reduced row count or missing old input paths: compare the
  inventory with the intended full source. An exceptional source correction
  requires the snapshot refresh procedure and a recorded reason.
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

## Configure the reporting engine

### Start and check
~~~powershell
$af = @('-f','compose.yaml','-f','compose.airflow.yaml')
docker compose @af config --quiet
docker compose @af build airflow-init
docker compose @af up -d airflow-api airflow-dag-processor airflow-scheduler
docker compose @af exec airflow-scheduler airflow dags list-import-errors
docker compose @af exec airflow-scheduler airflow tasks list retail_snapshot_pipeline
docker compose @af exec airflow-scheduler curl -fsS http://host.docker.internal:11434/api/tags
~~~
Confirm qwen2.5:3b is listed. If Windows Ollama cannot be reached, start the optional private service (no public port; separate model download):
~~~powershell
$af += @('-f','compose.reporting-ollama.yaml')
docker compose @af up -d reporting-ollama
docker compose @af exec reporting-ollama ollama pull qwen2.5:3b
docker compose @af up -d airflow-scheduler
docker compose @af exec airflow-scheduler curl -fsS http://reporting-ollama:11434/api/tags
~~~
Trigger a NEW retail_snapshot_pipeline run in the existing UI. Old runs do not contain publication.json. If reporting fails, inspect logs, fix the cause and clear only report. No fallback or failed draft is indexed. Failure does not roll back the Power BI publication.

### Receipts
Look for report_state RENDERED, or REUSED on the next identical run. Open the folder in the receipt:
~~~powershell
$file = Get-ChildItem artifacts/airflow -Recurse -Filter report.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$r = Get-Content -Raw $file.FullName | ConvertFrom-Json
$r | Select-Object airflow_run_id,state,snapshot_id,report_state,month,model,report_folder
Get-Content -Raw (Join-Path $r.report_folder 'brief.md')
~~~
Verify the receipt belongs to the intended DAG run. Publication and reporting receipts live under artifacts/airflow/<hash of run ID>/. The index key includes snapshot, month, policy, engine, model tag and reporting-code hashes. Reuse verifies eight output hashes and retains the original report ID; the new DAG run has its own receipt. If replacing the model weights under an unchanged model tag, invalidate the corresponding index entry. Manual reporting evaluation remains separate.

## Evaluate the brief

~~~powershell
.\.venv-forecast\Scripts\python.exe scripts/evaluate_briefs.py --model qwen2.5:3b
~~~
Each month is run in deterministic and local LLM modes. Read the printed evaluation.json and each run's claim_sources.json, response.json (LLM only), checks.json and brief.md. Review source snapshot IDs when comparing engines. Policy priority and data-quality caveats are supplied by code; their presence does not demonstrate model skill. Python binds every passage to its source field. The model writes text; checks enforce field structure, numeric tokens, selected semantics and forecast method/value bindings. Unsupported paraphrases may be rejected, and generic keyword checks do not prove factual entailment. Review accepted passages alongside their evidence. A rejected draft or unavailable service is a failure, not a baseline success. No automatic publication, no Airflow schedule change.

Version 3.1: Python renders the quality passage verbatim from published evidence. Ollama receives only the remaining fields and cannot submit a quality field. Quality text and lead ordering are not LLM performance metrics. Signed YoY is accepted as the original source sentence or as a narrowly defined equivalent English increase/decrease sentence. Other wording can still be rejected and should be reviewed. Run tests/test_narrative_regression.py to replay the two field-level failures. Compare new runs separately from v3; report the policy version and scope.

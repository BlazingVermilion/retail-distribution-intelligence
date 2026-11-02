# Verify and mirror KPIs in Snowflake

PostgreSQL remains the system of record. The September detail pilot below provisions the account objects used by the monthly mirror. For an existing pilot, start at **Sync a published month series**.

## Provision and compare the September pilot

1. In Windows PowerShell at the root, run: `.\.venv-dbt\Scripts\python.exe scripts/export_snowflake_pilot.py`. PostgreSQL must be running. The script reads the reconciled view and creates a six-column CSV and a comparison query in artifacts/snowflake/2026-09. No Snowflake account is needed for this step. Do not commit the CSV.
2. Use your own Snowflake account and a SQL worksheet in Snowsight. Run warehouse/snowflake/001_pilot_setup.sql. This assumes SYSADMIN rights in a personal sandbox; in a managed account request provisioning and use an authorized role. Dedicated project/service roles are a later step. Inspect existing objects if any names already exist.
3. In Snowsight open the internal stage RDI_PILOT_DB.PILOT.RDI_STAGE. Upload the generated iowa_2026_09.csv unchanged at the stage root. In a worksheet run 002_load_pilot.sql. Check LIST and the COPY result; if the stage stored a compressed name, use that exact filename in FILES. A failed COPY must be investigated before comparison.
4. In the same worksheet/session run the generated 003_compare.sql. Require PASS for the nine aggregate checks, not just a successful COPY. Save the COPY and comparison query IDs, status, rows loaded and elapsed time. Suspend RDI_PILOT_WH after use if running. Execution can consume Snowflake credits.
5. If the file is revised, use an isolated new pilot table and clean stage path; do not force-reload into a non-empty table. No automatic delete, truncate or overwrite is performed.
6. This pilot tests transport, types, null coverage and aggregate agreement for one month. It does not establish row-level parity, source completeness, or a working Snowflake dbt port. After PASS: port and test models on this slice before scaling or integrating orchestration. AI reporting remains in scope.

## Configure the dbt service role

```powershell
py -3.12 -m venv .venv-snowflake
.\.venv-snowflake\Scripts\python.exe -m pip install -r requirements-snowflake.txt
.\.venv-snowflake\Scripts\python.exe scripts/run_snowflake_pilot.py setup
```

Choose and retain a local key passphrase. The script creates an encrypted private key outside the repository and writes only the public key into artifacts/snowflake/2026-09/004_setup_dbt_role.sql. Do not share the private key or passphrase. Rerunning setup reuses the existing key. If a service user with the same name already exists, setup does not overwrite its public key.

In Snowsight open a SQL file. Run 004_setup_dbt_role.sql in order: the first two statements as SYSADMIN, the remainder as SECURITYADMIN. These are administrative roles for one-time provisioning in your own trial account. If your SQL editor overrides USE ROLE, select the applicable role in the editor before running each block. Do not grant either administrative role to the service user. The service role can read the one input table and write to DBT_PILOT.

To get the account identifier, run this in your Snowflake SQL editor:
```sql
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME() AS account_identifier;
```

In the same PowerShell window, replace ORG-ACCOUNT with the exact returned value, without https:// or a domain:
```powershell
$env:RDI_SF_ACCOUNT = 'ORG-ACCOUNT'
.\.venv-snowflake\Scripts\python.exe scripts/run_snowflake_pilot.py debug
.\.venv-snowflake\Scripts\python.exe scripts/run_snowflake_pilot.py build
```

Enter the local private-key passphrase when prompted. Stop if debug fails. Build reads the numeric reference from 003_compare.sql and runs a staging view, a monthly table and six data tests. The parity test fails for a missing or extra month, different counts, NULL mismatches or different sums. Use this runner, not a bare dbt build without vars.

After the build, as SYSADMIN inspect:
```sql
USE ROLE SYSADMIN;
USE WAREHOUSE RDI_PILOT_WH;
SELECT * FROM RDI_PILOT_DB.DBT_PILOT.SALES_MONTHLY_PILOT;
```

Keep the dbt summary and artifacts/snowflake/2026-09/dbt_target/run_results.json. Record the Snowflake query IDs and elapsed times from Query History (tag RDI_STEP12B). The warehouse may resume and consume trial credits during use. Suspend it after inspection if still running. No Airflow schedule, input replacement, or dashboard switch is introduced.

Local verification in the delivery environment: dbt parse and a check of the expected-reference parser. A real debug/build must run against the user's Snowflake account before recording cloud execution as successful.

## Sync a published month series

Run from the project root. Requires the running PostgreSQL service and the dbt service role, account identifier, encrypted key and .venv-snowflake. Use the exact snapshot_id from an Airflow report receipt. Do not use the run_id. The source is publication.monthly_snapshots joined to DBT_VALIDATED publication metadata. The separate target is RDI_PILOT_DB.DBT_PILOT.MONTHLY_KPI_SNAPSHOTS. Existing pilot transactions are untouched.

~~~powershell
$sid = 'bae8dc30-62b6-4d3d-9368-f7d3b57f7163'
$env:RDI_SF_ACCOUNT = '<organization>-<account>'
$py = '.\.venv-snowflake\Scripts\python.exe'
& $py scripts/sync_snowflake_kpis.py preview --snapshot-id $sid
& $py scripts/sync_snowflake_kpis.py sync --snapshot-id $sid
& $py scripts/sync_snowflake_kpis.py verify --snapshot-id $sid
& $py scripts/sync_snowflake_kpis.py sync --snapshot-id $sid
~~~

Run one command at a time; stop on an error. Expected states on an initially empty target: PREVIEW, INSERTED, VERIFIED, UNCHANGED. The preview only reads PostgreSQL. The cloud commands prompt for the existing private-key passphrase; they use the existing X-Small warehouse and can consume credits. A verify checks every row without creating or changing tables. On detected mismatch the tool stops; never drop the table to force a pass. A new source snapshot creates separate history. Do not run simultaneous writers: the primary key on a standard Snowflake table is informational; this manual pilot tests sequential reruns only.

Check the last receipt and share its state, dates and month count; never share keys. Receipts are in artifacts/snowflake/monthly_kpis/<snapshot-id>/. Local unit tests: python tests/test_snowflake_sync.py. Tests use a fake cursor, not a live Snowflake account.

## Enable the Airflow branch

Prerequisites: a working local DAG, successful manual verification, an encrypted service key, RDI_SF_ACCOUNT set in the shell and the local pilot Python environment. Keep your existing Compose options (including the Ollama overlay if used).

1. Dot-source scripts/setup_sf_airflow.ps1 from the project root in Windows PowerShell. It reads the installed pilot connector version, resolves the encrypted key and creates a user-restricted local plaintext passphrase file outside the repo. Keep both files private. Re-run setup in a fresh shell to restore environment variables. For rotation, stop the scheduler and replace the passphrase file, then recreate the scheduler.
2. Append -f compose.snowflake-sync.yaml to the existing Compose arguments. Run config --quiet, build airflow-init, and up -d airflow-api airflow-dag-processor airflow-scheduler. Stop at any nonzero exit. The scheduler alone receives both file secrets; the connector is in the isolated pipeline environment. Confirm the scheduler can read both files without printing them.
3. List import errors and tasks. Trigger a new retail_snapshot_pipeline run. LocalExecutor still limits task concurrency to one. Both report and sync_snowflake depend directly on publish, so a failed cloud sync can fail the run but cannot undo publication or prevent its sibling from running.
4. Inspect artifacts/airflow/<run hash>/snowflake.json and publication.json. Match airflow_run_id and snapshot_id; sync_state is INSERTED or UNCHANGED; verification must be VERIFIED. The current 81-month mirror should be UNCHANGED. Receipts are written only after verification. A retry after a committed insert can legitimately show UNCHANGED.
5. For recovery, fix credentials or connectivity and clear only sync_snowflake on the same run. For local-only operation omit the Snowflake Compose overlay and recreate the scheduler. The task then skips without connecting. Cloud-enabled runs use the pilot warehouse.

### Locking and scope

The updated manual CLI and scheduler share artifacts/snowflake/monthly_kpis/writer.lock through the existing bind mount. A hard kill can leave an empty lock directory. Stop/check ALL writers first; only then remove the empty stale directory and retry. This is a single-host pilot: external writers or older unpatched copies do not honor this lock. Do not run them against the target.

Run the two Python test files under tests/ individually. They simulate connectors; final acceptance requires Docker Desktop and the real pilot account.

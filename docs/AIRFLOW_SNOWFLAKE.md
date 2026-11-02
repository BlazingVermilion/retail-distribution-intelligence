# Step 15.2: publish monthly KPIs to Snowflake from Airflow

Prerequisites: working Step 14 DAG, successful Step 15.1 manual verification, encrypted service key and local pilot Python environment. Apply the overlay in the repository root when no run is active. Back up locally edited DAG and sync script first. Keep your existing Compose options (including the Ollama overlay if used).

1. Dot-source scripts/setup_sf_airflow.ps1 from the project root in Windows PowerShell. It reads the installed pilot connector version, resolves the encrypted key and creates a user-restricted local plaintext passphrase file outside the repo. Keep both files private. Re-run setup in a fresh shell to restore environment variables. For rotation, stop the scheduler and replace the passphrase file, then recreate the scheduler.
2. Append -f compose.snowflake-sync.yaml to the existing Compose arguments. Run config --quiet, build airflow-init, and up -d airflow-api airflow-dag-processor airflow-scheduler. Stop at any nonzero exit. The scheduler alone receives both file secrets; the connector is in the isolated pipeline environment. Confirm the scheduler can read both files without printing them.
3. List import errors and tasks. Trigger a new retail_snapshot_pipeline run. LocalExecutor still limits task concurrency to one. Both report and sync_snowflake depend directly on publish, so a failed cloud sync can fail the run but cannot undo publication or prevent its sibling from running.
4. Inspect artifacts/airflow/<run hash>/snowflake.json and publication.json. Match airflow_run_id and snapshot_id; sync_state is INSERTED or UNCHANGED; verification must be VERIFIED. The current 81-month mirror should be UNCHANGED. Receipts are written only after verification. A retry after a committed insert can legitimately show UNCHANGED.
5. For recovery, fix credentials or connectivity and clear only sync_snowflake on the same run. For local-only operation omit the Snowflake Compose overlay and recreate the scheduler. The task then skips without connecting. Cloud-enabled runs use the pilot warehouse.

## Locking and scope

The updated manual CLI and scheduler share artifacts/snowflake/monthly_kpis/writer.lock through the existing bind mount. A hard kill can leave an empty lock directory. Stop/check ALL writers first; only then remove the empty stale directory and retry. This is a single-host pilot: external writers or older unpatched copies do not honor this lock. Do not run them against the target. Stress and failure-injection testing remain deferred.

Run the two Python test files under tests/ individually. They simulate connectors; final acceptance requires Docker Desktop and the real pilot account.

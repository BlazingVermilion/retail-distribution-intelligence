# Step 15.1: monthly KPI parity pilot
Run from the project root. Requires the running PostgreSQL service and the Step 12B role, account identifier, encrypted key and .venv-snowflake. Use the exact snapshot_id from an Airflow report receipt. Do not use the run_id. The source is publication.monthly_snapshots joined to DBT_VALIDATED publication metadata. The separate target is RDI_PILOT_DB.DBT_PILOT.MONTHLY_KPI_SNAPSHOTS. Existing pilot transactions are untouched.

~~~powershell
$sid = 'bae8dc30-62b6-4d3d-9368-f7d3b57f7163'
$env:RDI_SF_ACCOUNT = 'BXDVXCA-GS45600'
$py = '.\.venv-snowflake\Scripts\python.exe'
& $py scripts/sync_snowflake_kpis.py preview --snapshot-id $sid
& $py scripts/sync_snowflake_kpis.py sync --snapshot-id $sid
& $py scripts/sync_snowflake_kpis.py verify --snapshot-id $sid
& $py scripts/sync_snowflake_kpis.py sync --snapshot-id $sid
~~~

Run one command at a time; stop on an error. Expected states on an initially empty target: PREVIEW, INSERTED, VERIFIED, UNCHANGED. The preview only reads PostgreSQL. The cloud commands prompt for the existing private-key passphrase; they use the existing X-Small warehouse and can consume credits. A verify checks every row without creating or changing tables. On detected mismatch the tool stops; never drop the table to force a pass. A new source snapshot creates separate history. Do not run simultaneous writers: the primary key on a standard Snowflake table is informational; this manual pilot tests sequential reruns only. Keep this command outside Airflow until a noninteractive secret and concurrency policy are in place.

Check the last receipt and share its state, dates and month count; never share keys. Receipts are in artifacts/snowflake/monthly_kpis/<snapshot-id>/. Local unit tests: python tests/test_snowflake_sync.py. Tests use a fake cursor, not a live Snowflake account.

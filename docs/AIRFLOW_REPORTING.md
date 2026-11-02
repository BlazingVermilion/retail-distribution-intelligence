# Step 14: Airflow monthly reporting
Apply the overlay in the project root beside compose.yaml. Keep the existing .env and named volumes. The manual DAG now runs prepare → load → dbt_build → publish → report. The reporting task uses a read-only PostgreSQL session and the exact snapshot returned by publish. Both PUBLISHED and UNCHANGED produce a receipt. Each run targets the latest month in its snapshot. Windows standalone reporting still works.

## Start and check
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

## Receipts
Look for report_state RENDERED, or REUSED on the next identical run. Open the folder in the receipt:
~~~powershell
$file = Get-ChildItem artifacts/airflow -Recurse -Filter report.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$r = Get-Content -Raw $file.FullName | ConvertFrom-Json
$r | Select-Object airflow_run_id,state,snapshot_id,report_state,month,model,report_folder
Get-Content -Raw (Join-Path $r.report_folder 'brief.md')
~~~
Verify the receipt belongs to the intended DAG run. Publication and reporting receipts live under artifacts/airflow/<hash of run ID>/. The index key includes snapshot, month, policy, engine, model tag and reporting-code hashes. Reuse verifies eight output hashes and retains the original report ID; the new DAG run has its own receipt. If replacing the model weights under an unchanged model tag, invalidate the corresponding index entry. Manual reporting evaluation remains separate. The stress/failure-injection suite is deferred.

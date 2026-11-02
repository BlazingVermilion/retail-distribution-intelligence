# Step 12B — Build and test two Snowflake models

Status: the owner reported PASS for the nine 12A aggregate checks. This does not establish row-by-row parity or validate all years. The input is the six-column September 2026 pilot table, not the raw 23-column source. Reconciliation, dimensions and YoY cannot be rebuilt from these six columns. The PostgreSQL dbt project and the Power BI publication stay in place.

## Windows setup

Extract this overlay beside compose.yaml. Keep the original artifacts/snowflake/2026-09/003_compare.sql, the reference used in 12A. No repeat upload is needed.

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

Keep the dbt summary and artifacts/snowflake/2026-09/dbt_target/run_results.json. Record the Snowflake query IDs and elapsed times from Query History (tag RDI_STEP12B). The warehouse may resume and consume trial credits during use. Suspend it after inspection if still running. No Airflow schedule, input replacement, or dashboard switch is introduced. Stress/failure testing remains deferred in docs/STRESS_FAIL_TESTS.md.

Local verification in the delivery environment: dbt parse and a check of the expected-reference parser. A real debug/build must run against the user's Snowflake account before recording cloud execution as successful.

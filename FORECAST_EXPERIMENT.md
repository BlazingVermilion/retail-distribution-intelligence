# Iowa monthly bottle forecast experiment
Predict next month's statewide reported net bottles. Use the same forecast origin, target and months for every candidate. Reported shipments are not consumer demand. Keep the production baseline while evaluating challengers.

## Run from the project root (Windows PowerShell)
1. Copy the two included directories into the project, preserving paths. Start the existing PostgreSQL service. Confirm dbt_dev.fact_sales has category_code, ordered_on and sales_bottles. The control relation is marts.v_sales_monthly_kpis; equal monthly counts and net bottles verify agreement on these totals only.
2. Export the grouped input. This reads the fact table once; do not export all transactions. The Python reader accepts UTF-8 with or without a byte-order mark.
~~~powershell
New-Item -Force -ItemType Directory artifacts/forecast_panel | Out-Null
Get-Content -Raw warehouse/postgres/forecast_panel_export.sql | docker compose exec -T postgres psql -X -q -v ON_ERROR_STOP=1 -U postgres -d retail_analytics | Out-File -Encoding utf8 artifacts/forecast_panel/input.csv
if ($LASTEXITCODE -ne 0) { throw "Panel export failed; do not train on this file." }
.\.venv-forecast\Scripts\python.exe scripts/forecast_panel_xgb.py artifacts/forecast_panel/input.csv
~~~
Use your existing forecasting Python environment with NumPy if its path differs.

## Experimental contract
- Choose the 12 largest category codes by sum of absolute monthly net bottles in 2020–22 only. Keep all other codes in OTHER. An absent group contributes zero in an observed month. Missing bottle values, month gaps, duplicate group keys or unreconciled controls stop the run. A complete extract is still not proof of complete source reporting.
- Compare last year's month, a statewide residual Ridge, and the same Ridge pooled across product groups with predictions summed to the state. The learner predicts the difference from last year, scaled by trailing 12-month mean absolute volume. Inputs are the last three observed year-over-year changes and known weekday-count differences from the target month last year. Group rows share coefficients; they are not independent time periods.
- Fit scaling and coefficients anew before each target month. All groups of a month stay on the same side of the split. No random split. The first eligible supervised target is April 2021 because the features need 15 prior months. Evaluate January 2023 onward. Penalty fixed before evaluating the panel. Inspect category_errors.csv for offsetting errors and category recodes.
- Select using only 2023–25: require at least 5% lower MAE and absolute signed bias no worse than baseline. This existing gate is strict when positive and negative baseline errors cancel. Also inspect annual MAE, WAPE and signed bias. Do not change the gate after inspecting 2026.
- January–September 2026 was already examined during development. Its results are retrospective diagnostics, not unseen performance. Before the next unobserved month, archive the input hash, code version, issued timestamp, forecast and baseline. Score both after actuals arrive, retaining source versions. Do not promote or automate publication based on this experiment alone.
- This module trains and backtests only. It does not overwrite any snapshot, register a production model, or claim accuracy for an unobserved period.

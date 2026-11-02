# Historical forecast experiments

These alternatives are retained for reproducibility. The [published forecast](../../README.md#forecasting-and-reporting) uses statewide monthly series.

## Category panel

Predict next month's statewide reported net bottles. Use the same forecast origin, target and months for every candidate. Reported shipments are not consumer demand. Keep the production baseline while evaluating challengers.

### Run from the project root (Windows PowerShell)
1. Copy the two included directories into the project, preserving paths. Start the existing PostgreSQL service. Confirm dbt_dev.fact_sales has category_code, ordered_on and sales_bottles. The control relation is marts.v_sales_monthly_kpis; equal monthly counts and net bottles verify agreement on these totals only.
2. Export the grouped input. This reads the fact table once; do not export all transactions. The Python reader accepts UTF-8 with or without a byte-order mark.
~~~powershell
New-Item -Force -ItemType Directory artifacts/forecast_panel | Out-Null
Get-Content -Raw warehouse/postgres/forecast_panel_export.sql | docker compose exec -T postgres psql -X -q -v ON_ERROR_STOP=1 -U postgres -d retail_analytics | Out-File -Encoding utf8 artifacts/forecast_panel/input.csv
if ($LASTEXITCODE -ne 0) { throw "Panel export failed; do not train on this file." }
.\.venv-forecast\Scripts\python.exe scripts/forecast_panel_xgb.py artifacts/forecast_panel/input.csv
~~~
Use your existing forecasting Python environment with NumPy if its path differs.

### Experimental contract
- Choose the 12 largest category codes by sum of absolute monthly net bottles in 2020–22 only. Keep all other codes in OTHER. An absent group contributes zero in an observed month. Missing bottle values, month gaps, duplicate group keys or unreconciled controls stop the run. A complete extract is still not proof of complete source reporting.
- Compare last year's month, a statewide residual Ridge, and the same Ridge pooled across product groups with predictions summed to the state. The learner predicts the difference from last year, scaled by trailing 12-month mean absolute volume. Inputs are the last three observed year-over-year changes and known weekday-count differences from the target month last year. Group rows share coefficients; they are not independent time periods.
- Fit scaling and coefficients anew before each target month. All groups of a month stay on the same side of the split. No random split. The first eligible supervised target is April 2021 because the features need 15 prior months. Evaluate January 2023 onward. Penalty fixed before evaluating the panel. Inspect category_errors.csv for offsetting errors and category recodes.
- Select using only 2023–25: require at least 5% lower MAE and absolute signed bias no worse than baseline. This existing gate is strict when positive and negative baseline errors cancel. Also inspect annual MAE, WAPE and signed bias. Do not change the gate after inspecting 2026.
- January–September 2026 was already examined during development. Its results are retrospective diagnostics, not unseen performance. Before the next unobserved month, archive the input hash, code version, issued timestamp, forecast and baseline. Score both after actuals arrive, retaining source versions. Do not promote or automate publication based on this experiment alone.
- This module trains and backtests only. It does not overwrite any snapshot, register a production model, or claim accuracy for an unobserved period.

## XGBoost

From the project root, install requirements-forecast-xgb.txt in the existing forecasting environment. Reuse the reconciled category-month CSV produced by the v2 export. If needed, follow the export instructions in the category panel section above. Run:

~~~powershell
.\.venv-forecast\Scripts\python.exe -m pip install -r requirements-forecast-xgb.txt
.\.venv-forecast\Scripts\python.exe scripts/forecast_panel_xgb.py artifacts/forecast_panel/input.csv
~~~

The archived v2 protocol describes input controls, feature definitions and the baseline gate. The new runner includes all three v2 comparators plus pooled residual XGBoost. Hyperparameters are fixed: depth 2, 80 rounds, learning rate 0.04, minimum child weight 12 and L2 penalty 5. No search or early stopping on 2026. Each origin trains on earlier months only. Months from 2026 onward are retrospective diagnostics, not part of selection. The gate uses statewide validation MAE and absolute bias, not category-level errors.

Inspect artifacts/forecast_panel_xgb/result.json for annual MAE (bottles), bias (forecast minus actual), WAPE (%), and the validation candidate. Compare panel_xgboost against both seasonal_naive and panel_residual (pooled Ridge). predictions.csv contains matched statewide forecasts; category_errors.csv contains group forecasts and actuals. panel_xgboost.json is the challenger refit through the latest input month. Its next-month forecast is a scenario, not an automatically promoted forecast. Archive dated runs before refreshing; the default output directory is overwritten. Use --out to keep separate runs. Source reporting completeness remains unverified.

## Weekly store TCN

Forecast statewide net wholesale bottles for the next calendar month. This is a research workflow; it does not update a published snapshot. Start from the repository root using the existing forecasting Python environment (Python 3.10–3.13, 64-bit). On Windows PowerShell:

~~~powershell
.\.venv-forecast\Scripts\python.exe -m pip install torch==2.9.0 --index-url https://download.pytorch.org/whl/cpu
.\scripts\export_store_weekly.ps1
.\.venv-forecast\Scripts\python.exe scripts/store_tcn.py artifacts/store_tcn/store_weekly.csv --out artifacts/store_tcn/run_001
~~~

The runner uses NumPy from the existing forecasting environment. Select a new output directory for each run. The CPU runner prints the forecast month and flushes its predictions after each fold. No GPU, cloud account or data reload is needed.

### Input and cutoff
The SQL reads dbt_dev.fact_sales and reconciles against marts.v_sales_monthly_kpis.sales_bottles and source_records in a single database statement. It keeps calendar-month slices of Monday-starting weeks, so the final partial week cannot include the target month. Missing bottle values or a month missing from either relation stop the run. Months with reported activity may still be incomplete. Absent store-week rows are treated as zero reported activity within a reconciled statewide month. This cannot distinguish an unreported order from no order. Unknown store IDs form a separate bucket. Reported negatives are preserved.

### Identical inputs and fair comparisons
Each known store has eight weekly signed counts scaled by its historical monthly absolute volume (floor 30 bottles), week exposure, the normalized same-month-last-year anchor, and target-month length. Both learned models predict a correction to that store's seasonal anchor. Known stores with short histories use available observations and zeros before entry, with a zero seasonal anchor where appropriate. Previously unseen stores have no known identifiers at forecast time: both challengers add the average total first-month volume of entrants in the prior three months. Closed stores remain in the known universe; false forecasts for them count as errors. The seasonal baseline is exactly the prior-year statewide total. New and dormant stores may drive errors; the CSV provides the entrant allowance and MAE over known stores for diagnosis.

Ridge flattens the same sequences and solves a penalized linear fit. The TCN shares convolution weights across stores, uses left padding, eight hidden channels and dilations 1/2/4. Its zero-initialized output starts at zero correction. Both losses combine mean squared normalized store residual error with squared normalized statewide total error, weighting each training month equally. Adam uses backpropagation for four fixed epochs. Both models refit from scratch before each monthly prediction. No hyperparameter search on 2026.

### Decision and artifacts
2020–22 precede validation. January 2021 is the first supervised target (12 months needed for the anchor). Score every month starting January 2023, always fitting on earlier targets only. The 36 months in 2023–25 determine selection: reduce statewide MAE by at least 5% with absolute bias no worse than seasonal naive. The previously inspected 2026 period is retrospective diagnostic evidence. The final fold fits through the last input month and issues an unscored next-month scenario. Late source revisions and period completeness are not verified. For prospective scoring archive a run before actuals arrive.

- result.json: per-model sample count, statewide MAE (bottles), bias (forecast minus actual), WAPE, validation choice, input hash and next forecast.
- predictions.csv: month, model, statewide forecast/actual, known-store MAE and new-store forecast. The final actual is blank.
- tcn_weights.pt and ridge.npy: final challenger parameters; reproduce alongside the code and source export.
- Compare validation and 2026 baseline MAE to the earlier run if its snapshot is identical. Compare TCN vs store Ridge before attributing a gain to deep learning. A production promotion is a separate decision.

Run the cutoff and cold-start regression test with the same interpreter:
~~~powershell
.\.venv-forecast\Scripts\python.exe tests/experiments/test_store_tcn.py
~~~

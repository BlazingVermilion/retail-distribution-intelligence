# Iowa store-level temporal convolution experiment

Forecast statewide net wholesale bottles for the next calendar month. This is a research workflow; it does not update a published snapshot. Start from the repository root using the existing forecasting Python environment (Python 3.10–3.13, 64-bit). On Windows PowerShell:

~~~powershell
.\.venv-forecast\Scripts\python.exe -m pip install torch==2.9.0 --index-url https://download.pytorch.org/whl/cpu
.\scripts\export_store_weekly.ps1
.\.venv-forecast\Scripts\python.exe scripts/store_tcn.py artifacts/store_tcn/store_weekly.csv --out artifacts/store_tcn/run_001
~~~

The runner uses NumPy from the existing forecasting environment. Select a new output directory for each run. The CPU runner prints the forecast month and flushes its predictions after each fold. No GPU, cloud account or data reload is needed.

## Input and cutoff
The SQL reads dbt_dev.fact_sales and reconciles against marts.v_sales_monthly_kpis.sales_bottles and source_records in a single database statement. It keeps calendar-month slices of Monday-starting weeks, so the final partial week cannot include the target month. Missing bottle values or a month missing from either relation stop the run. Months with reported activity may still be incomplete. Absent store-week rows are treated as zero reported activity within a reconciled statewide month. This cannot distinguish an unreported order from no order. Unknown store IDs form a separate bucket. Reported negatives are preserved.

## Identical inputs and fair comparisons
Each known store has eight weekly signed counts scaled by its historical monthly absolute volume (floor 30 bottles), week exposure, the normalized same-month-last-year anchor, and target-month length. Both learned models predict a correction to that store's seasonal anchor. Known stores with short histories use available observations and zeros before entry, with a zero seasonal anchor where appropriate. Previously unseen stores have no known identifiers at forecast time: both challengers add the average total first-month volume of entrants in the prior three months. Closed stores remain in the known universe; false forecasts for them count as errors. The seasonal baseline is exactly the prior-year statewide total. New and dormant stores may drive errors; the CSV provides the entrant allowance and MAE over known stores for diagnosis.

Ridge flattens the same sequences and solves a penalized linear fit. The TCN shares convolution weights across stores, uses left padding, eight hidden channels and dilations 1/2/4. Its zero-initialized output starts at zero correction. Both losses combine mean squared normalized store residual error with squared normalized statewide total error, weighting each training month equally. Adam uses backpropagation for four fixed epochs. Both models refit from scratch before each monthly prediction. No hyperparameter search on 2026.

## Decision and artifacts
2020–22 precede validation. January 2021 is the first supervised target (12 months needed for the anchor). Score every month starting January 2023, always fitting on earlier targets only. The 36 months in 2023–25 determine selection: reduce statewide MAE by at least 5% with absolute bias no worse than seasonal naive. The previously inspected 2026 period is retrospective diagnostic evidence. The final fold fits through the last input month and issues an unscored next-month scenario. Late source revisions and period completeness are not verified. For prospective scoring archive a run before actuals arrive.

- result.json: per-model sample count, statewide MAE (bottles), bias (forecast minus actual), WAPE, validation choice, input hash and next forecast.
- predictions.csv: month, model, statewide forecast/actual, known-store MAE and new-store forecast. The final actual is blank.
- tcn_weights.pt and ridge.npy: final challenger parameters; reproduce alongside the code and source export.
- Compare validation and 2026 baseline MAE to the earlier run if its snapshot is identical. Compare TCN vs store Ridge before attributing a gain to deep learning. A production promotion is a separate decision.

Run the cutoff and cold-start regression test with the same interpreter:
~~~powershell
.\.venv-forecast\Scripts\python.exe tests/experiments/test_store_tcn.py
~~~

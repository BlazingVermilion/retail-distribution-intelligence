# Step 13F1 — Statewide monthly bottle forecasting

## What runs now

One command exports a consistent validated monthly PostgreSQL snapshot, reproduces the January–September 2026 seasonal baseline, fits statistical and machine-learning candidates, and renders an English forecast brief. Inputs and outputs are local. No Snowflake warehouse, Ollama server, migration, Airflow run or Power BI refresh is required. This milestone produces research artifacts, not live-issued forecasts or a database forecast registry.

## Windows

Extract the overlay beside compose.yaml. Do not install forecasting packages in the dbt or Airflow environment.
```powershell
py -3.12 -m venv .venv-forecast
.\.venv-forecast\Scripts\python.exe -m pip install -r requirements-forecast.txt
docker compose up -d postgres
.\.venv-forecast\Scripts\python.exe scripts/forecast_iowa.py
```

Stop on errors; do not continue with a failed run. The SQL reads the monthly publication in one statement via the project's local Docker postgres account. There are no database writes. Use a restricted publication reader when adding scheduled jobs.

## Reading the experiment

- manifest.json: run status, UTC time, snapshot ID, code and input SHA-256, software versions and last month consumed. series.csv: replayable source export with original quality statuses. These are current-vintage observations, not historical releases as originally known.
- metrics.csv: one row per model and evaluation period. Compare phase rolling_test_2026_01_09 for identical nine-month windows, and validation_2023_25 for the frozen selection. Counts, MAE and signed bias use bottles; WAPE uses percent. Positive bias means overforecast. Slice rows for each validation year are diagnostic only.
- predictions.csv: per-model forecast origin, target, actual, signed error and interval when available. Filter by phase: validation, rolling_test, fixed_dec_2025, or next_after_data. Never pool horizons or phases when reporting accuracy.
- result.json: chosen spec, benchmark comparison, coverage and width, excluded validation fits, source quality and next-after-data scenario. The scenario is deliberately not tagged as a live forecast: the target may already have started. A future issuance job must enforce its real release deadline.
- forecast_brief.md: deterministic English comparison for the selected model. It is a reporting baseline, not an LLM response. Use its numeric evidence for the later evaluated AI narrative.

If inputs disagree with the previously reviewed benchmark, series.csv and a FAILED manifest are retained. Compare the actual monthly series and snapshot with the earlier reference; only after confirming an intended revision rerun with --accept-revision. Never change values to force agreement. Replay using --input PATH_TO_SERIES_CSV. Replays create separate audit directories; they never update published BI or forecasts.

## Acceptance

1. Original snapshot: seasonal-naive MAE 54,167.67; WAPE 2.2133%; signed bias +39,890.56 for Jan–Sep 2026.
2. A full eligible validation run has 36 h=1 predictions per candidate. Nonconvergent validation specs are explicitly excluded wholesale. Selected model must pass the predeclared MAE and absolute-bias gate or fall back to seasonal naive. A test-period fitting failure stops the run; do not silently remove a hard month.
3. Compare selected model and baseline on nine later targets; do not tune on 2026 scores. The 80% bounds use earlier absolute errors for that specification only (24 minimum). Sampling uncertainty and revised historical data limit interpretation. No independent month-completeness certification is available; scores are provisional when source coverage is unverified.
4. Fixed-origin outlook for Jan–Dec 2026 uses data through Dec 2025 only. Actuals and errors remain empty where unavailable. These rows do not have horizon-specific interval calibration.
5. For local verification: run `.\.venv-forecast\Scripts\python.exe -m unittest discover -s tests/forecasting -v`. The tests use synthetic warm-up history and the published reference slice. Their simulated candidate performance is not project evidence.

Next: verify real run results; add versioned, deadline-aware issuance and scoring; then connect to validated AI narratives, Airflow and Power BI. The final infrastructure stress/failure drill remains deferred.

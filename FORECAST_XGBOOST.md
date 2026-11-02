# Monthly wholesale bottle forecast: XGBoost challenger

From the project root, install requirements-forecast-xgb.txt in the existing forecasting environment. Reuse the reconciled category-month CSV produced by the v2 export. If needed, follow the export instructions in FORECAST_EXPERIMENT.md. Run:

~~~powershell
.\.venv-forecast\Scripts\python.exe -m pip install -r requirements-forecast-xgb.txt
.\.venv-forecast\Scripts\python.exe scripts/forecast_panel_xgb.py artifacts/forecast_panel/input.csv
~~~

The archived v2 protocol describes input controls, feature definitions and the baseline gate. The new runner includes all three v2 comparators plus pooled residual XGBoost. Hyperparameters are fixed: depth 2, 80 rounds, learning rate 0.04, minimum child weight 12 and L2 penalty 5. No search or early stopping on 2026. Each origin trains on earlier months only. Months from 2026 onward are retrospective diagnostics, not part of selection. The gate uses statewide validation MAE and absolute bias, not category-level errors.

Inspect artifacts/forecast_panel_xgb/result.json for annual MAE (bottles), bias (forecast minus actual), WAPE (%), and the validation candidate. Compare panel_xgboost against both seasonal_naive and panel_residual (pooled Ridge). predictions.csv contains matched statewide forecasts; category_errors.csv contains group forecasts and actuals. panel_xgboost.json is the challenger refit through the latest input month. Its next-month forecast is a scenario, not an automatically promoted forecast. Archive dated runs before refreshing; the default output directory is overwritten. Use --out to keep separate runs. Source reporting completeness remains unverified.

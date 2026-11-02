# Retail Distribution Intelligence: AI architecture and evaluation contract

> Historical design record. The [implemented architecture](architecture.md), [run evidence](acceptance/RUN_EVIDENCE.md) and [forecast evaluation](../README.md#forecasting-and-reporting) supersede older implementation-status statements below.

Decision: add an independently evaluated forecasting component to monthly reporting. Design v1, 2026-10-31. This is a new scope decision; the existing 13A brief is a reporting prototype. No trained model result or prospective forecast is claimed.

## Business decision and source contract

Forecast next month's statewide net bottles distributed to licensed Iowa stores for volume planning. The label is the published monthly sales_bottles, with source signs retained. It is not end-consumer demand, an inventory order recommendation or gross shipments. Primary horizon h=1. A separate fixed-origin outlook for 2026 answers a different question and must be scored by horizon, not pooled with h=1 results.

Read month_start, sales_bottles, source_records, completeness, reconciliation flags, and snapshot_id from the validated monthly PostgreSQL publication. Power BI continues using the existing monthly interface. Do not infer full-month coverage from a nonzero total; require a completed calendar month and documented extract coverage, retain UNVERIFIED labels, and separate provisional from confirmed scores. Missing months or NULL targets are missing, not zero. Abort the regular monthly fit for gaps until a resolution is documented. Dollar precision flags are not grounds to drop bottle counts. Retain negative adjustments. Establish a source arrival cut-off and prevent publication of a nominal next-month forecast if the origin is stale. Record actual release time and data-through month separately.

## Component boundaries

1. dbt/PostgreSQL: extract an ordered monthly series bound to one validated snapshot. Read exactly the as-of prefix on each simulated origin. Store a source manifest and series digest; distinguish actual historical vintages from today's revised vintage.
2. Python forecast runner: deterministic feature construction, fitting, interval calibration, rolling-origin backtest, model selection and future inference. It never calls the LLM.
3. Forecast registry: persist run_id, model/spec/code versions, training snapshot, data-through month, origin, issue timestamp, target month, horizon, point and lower/upper bounds, execution mode (backtest/live), and validation decision. Keep rows immutable; actuals and scores have their own snapshot/version. Replaying one run must not duplicate published forecasts.
4. Reporting: numeric evidence combines published actuals, the forecast that existed at its recorded origin, signed and absolute error when actuals exist, interval, baseline comparison and caveats. SQL/Python do all arithmetic. Keep deterministic English report as control. LLM may draft cited observations, never invent a cause or a future actual. Validate numeric value, metric, sign, unit, period, evidence IDs and mandatory caveats. Reject unsupported claims; retain the deterministic brief if validation fails. A reference ID alone does not establish entailment; report ambiguous novel language as unverified.
5. Airflow target: after a successful publication, score matured forecasts, then issue the next forecast, validate evidence, and generate the report. Do not retrain merely because an identical input is replayed. Make report failure independent of the validated BI snapshot. Expose forecast vs actual, intervals and error in a separate Power BI view. Snowflake's one-month six-column pilot is not training history. No LangGraph, RAG or CoCo dependency is needed for this workflow.

## Models and features

Controls: last observed month and seasonal naive (same calendar month in the prior year). Primary comparator: seasonal naive. Statistical candidate: additive seasonal ETS (period 12), with no trend or a damped additive trend. ML candidate: ridge regression on lagged bottles at 1, 2, 3 and 12 months, trailing 3-month average ending at the origin, annual sine/cosine and number of weekdays in the target month from the calendar. Predeclare ridge alpha in {0.1, 1, 10}; fit scaling only on training rows in each fold. Exclude future observed sales days, store counts, prices, dollar totals and reconciliation outcomes. Virtual regressors for h>1 must be calendar-known or recursively forecast; never substitute actual intermediate months. Start with small models: 2020-01 through 2026-09 has at most 81 statewide monthly observations, regardless of the source fact row count.

## Backtest and promotion protocol

- Assuming all months are present, use 2020-2022 as warm-up and Jan 2023-Dec 2025 as up to 36 expanding-window one-step validation origins/targets (one prediction per target, using only earlier observations). Select specs by lowest pooled MAE on identical eligible dates. Check yearly slices and bias. Fix tie order: seasonal naive, last-month naive, ETS, ridge. Freeze selection before scoring 2026. Never random-split a time series.
- Design target: at least 5% lower validation MAE than seasonal naive, with no worse absolute validation bias, to promote a challenger. These are engineering criteria, not evidence of statistical significance. Otherwise keep seasonal naive. Any future model change starts a new version. All models' diagnostic scores may be reported; 2026 must not become a tuning set.
- Rolling 2026 replay: issue Jan using data through Dec 2025; refit the frozen specification for Feb using data through Jan, etc. Separately freeze at Dec 2025 to predict Jan-Dec 2026 without updating; score only observed target months (currently Jan-Sep). The already inspected actuals mean this is retrospective evaluation, not a blind or prospective trial. Full-year totals remain unverified until actuals cover the year.
- With no vintage archive for each historical origin, explicitly label results latest-vintage retrospective backtests. Estimate genuine operational performance by storing forecasts before target observations arrive, and scoring them against a documented first accepted actual, retaining any revisions. Report sample size, dates, exclusions and time-series coverage.
- Primary MAE (bottles/month); WAPE = sum(abs(forecast-actual))/sum(abs(actual)); mean signed error = mean(forecast-actual), positive means overforecast. RMSE emphasizes large misses. Relative MAE skill = 1 - MAE(model)/MAE(seasonal naive) on the same dates. Return NA for a zero denominator. Never present 1-WAPE as a probability or guaranteed accuracy.
- For a nominal 80% interval use only previously available out-of-sample errors of the same horizon (e.g. empirical 80th percentile of absolute errors around the point forecast). Require at least 24 earlier errors; mark insufficient history rather than estimating intervals from 2026 test outcomes. Record empirical coverage AND average width. Report no interval guarantee; nine test months cannot establish calibration.
- Forecast vs narrative evaluation is separate. For reports record supported numerical claims / total numerical claims, required caveats present / required caveats, unsupported claims counted under a declared rule set, validation/fallback rate, model/prompt/snapshot IDs, latency, tokens and direct fees. Evaluate baseline vs LLM on identical evidence, including March 2025, January 2026 and September 2026. These are objective checks of fidelity, not evidence that stakeholders found the report useful.

## First concrete benchmark: September year-to-date, measured in bottles

Source: the owner's displayed PostgreSQL monthly KPI table, Jan-Sep 2025 and Jan-Sep 2026. These are reproduced reference results, not a new database query. Each forecast below simply repeats its 2025 counterpart. For these nine months this particular baseline yields the same numbers in both forecast protocols.

| Target | Seasonal-naive forecast | Reported actual | Forecast minus actual |
|---|---:|---:|---:|
| 2026-01 | 2,309,799 | 2,163,052 | +146,747 |
| 2026-02 | 2,206,814 | 2,192,141 | +14,673 |
| 2026-03 | 2,416,496 | 2,414,717 | +1,779 |
| 2026-04 | 2,595,432 | 2,483,580 | +111,852 |
| 2026-05 | 2,571,012 | 2,576,531 | -5,519 |
| 2026-06 | 2,642,511 | 2,582,939 | +59,572 |
| 2026-07 | 2,542,822 | 2,593,396 | -50,574 |
| 2026-08 | 2,550,030 | 2,461,391 | +88,639 |
| 2026-09 | 2,550,832 | 2,558,986 | -8,154 |

Total reported actual: 22,026,733. Total forecast: 22,385,748. Net overforecast: 359,015. Sum of monthly absolute misses: 487,509. MAE: 54,167.67 bottles/month. WAPE: 2.2133%. Mean signed error: +39,890.56 bottles/month. RMSE: 73,276.03 bottles/month. This is the benchmark to beat, not ML performance. Recompute from the versioned input and flag any mismatch before fitting challengers.

## Implementation sequence and acceptance

First capture the versioned monthly series, profile dates and recreate the benchmark. Next implement and freeze the historical experiment; retain per-origin results for every candidate. Then issue a timestamped next-month forecast and serve it separately from replayed forecasts. Finally connect validated numbers to the reporting baseline and the LLM; compare results before wiring Airflow and Power BI.

Method reference: Hyndman & Athanasopoulos, Forecasting: Principles and Practice, time series cross-validation and forecast accuracy, https://otexts.com/fpp3/toolbox.html .

# Retail Distribution Intelligence

Retail Distribution Intelligence turns Iowa liquor distribution records into a monthly sales dashboard, a statewide bottle forecast and a brief whose figures can be traced back to the published data. It is designed for an analyst preparing a monthly review: **how much did retailers purchase, how did that change from last year, and which figures need a closer look?** The records describe purchases by licensed retailers, not individual consumer sales.

## What the project delivers

| Output | What it tells the analyst | Observed result |
|---|---|---|
| Power BI dashboard | Sales, bottles, purchasing stores and year-over-year change, alongside the quality of the underlying figures | September 2026: **$35.76M** in reported sales, **1,990** stores and **+1.72%** versus September 2025 |
| Versioned analytical warehouse | A consistent set of monthly figures for the dashboard and reporting jobs | **17,337,629** exact-deduplicated records in PostgreSQL; **81** monthly KPI rows verified in Snowflake, January 2020–September 2026 |
| Forecast and monthly brief | A next-month bottle estimate and a reviewable summary that retains source caveats | Seasonal naive achieved **2.21% WAPE** on nine held-out months; the local Qwen reporting workflow passed its checks on **3/3** evaluation months |

## A finding behind the dashboard

In January 2026, all **182,995** records had the inputs needed to check reported sales against quantity × unit price. The **sum of absolute differences was $972,656**, or 3.3995% of absolute reported value on evaluable records. The month is marked for review. The dashboard preserves the source figures: this discrepancy is a diagnostic, not a financial loss.

![Power BI Data Quality page showing January 2026 flagged for review](docs/images/data-quality.png)

[See the sales and growth dashboards, Airflow run and Snowflake verification →](docs/acceptance/RUN_EVIDENCE.md)

## How it works

1. **Prepare and load.** Python discovers CSVs across year folders and audits exact duplicates across files. Different rows sharing an invoice ID are retained. PostgreSQL stores the deduplicated dataset.
2. **Model and publish.** Nine dbt models type the fields, reconcile quantities and amounts, and build facts, dimensions and monthly KPIs. Publication validates the candidate before switching the snapshot read by Power BI.
3. **Report and mirror.** After publication, an on-demand Airflow DAG runs two independent tasks: generate a brief from the pinned snapshot and optionally sync its monthly KPIs to Snowflake. The observed six-task run completed in **7m 17s** on unchanged input; this is not a full-load benchmark.

[Airflow DAG](airflow/dags/retail_snapshot_pipeline.py) · [dbt models](dbt/models) · [publication code](scripts/publish_snapshot.py) · [architecture diagram](docs/architecture.md)

## Forecasting and reporting

The forecasting target is statewide monthly **net bottles**. For each month from January through September 2026, both methods used only observations before that target. Seasonal naive uses the same month of the previous year.

| Method | Mean absolute error (bottles) | Weighted absolute percentage error |
|---|---:|---:|
| Seasonal naive | 54,167.67 | 2.2133% |
| Damped additive Holt-Winters | 65,937.69 | 2.6942% |

The simpler forecast had lower error, so it remains the primary plan. The comparison uses one historical data vintage; it does not establish future accuracy. [Reproduce the backtest](docs/getting_started.md#replay-the-forecast).

Qwen 2.5 3B runs locally through Ollama to write parts of the narrative. Python supplies the numbers, renders the protected quality statement and checks the draft before publication. Both the deterministic baseline and Qwen passed the same three selected cases; this measures adherence to the report contract on those cases. [Read the September brief](docs/evidence/brief.md) or [inspect the evaluation records](docs/evidence/evaluation.json).

## Try it

Run from the repository root with Python 3.11 or 3.12. This small demo requires no credentials, database or model download:

```sh
python scripts/inspect_snapshot.py --year 2026 --files data/fixtures/transactions.csv --output artifacts/demo-manifest.json
python -m unittest discover -s tests -v
```

The first command inspects four synthetic records and writes a manifest. It does not reproduce the full warehouse. For setup, operating instructions and source attribution, see the [documentation guide](docs/guide.md).

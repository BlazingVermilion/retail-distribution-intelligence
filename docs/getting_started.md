# Getting started

## Inspect the fixture

Open the cloned repository root (the directory with compose.yaml) in a terminal. With Python 3.11 or 3.12 run:

```sh
python scripts/inspect_snapshot.py --year 2026 --files data/fixtures/transactions.csv --output artifacts/demo-manifest.json
python -m unittest discover -s tests -v
```

The fixture contains four synthetic records, including a repeated row and a negative adjustment. The inspector validates the 23-column header and primitive values and writes a manifest. It does not remove duplicates, publish a snapshot or certify data completeness.

## Replay the forecast

In a separate Python 3.12 environment:

```sh
python -m pip install numpy==2.2.6 scipy==1.15.3
python scripts/backtest_monthly.py
```

The script reads the [81 published monthly observations](evidence/monthly-evidence.json) and scores nine one-month-ahead forecasts. No Snowflake account or raw CSV is needed.

## Full installation

Keep original exports in data/raw/YYYY, outside Git. For a new installation copy .env.example to .env, choose distinct local credentials and start PostgreSQL with `docker compose up -d postgres`. The full warehouse requires its source load and numbered SQL migrations; a running empty database is not sufficient. See the [operator guide](operations/postgres.md) and [data source](data_sources.md). The dashboard images and brief can be reviewed independently of the warehouse.

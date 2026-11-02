# Implemented architecture

```mermaid
flowchart TD
  A["Year-partitioned Iowa CSVs"] --> B["Prepare: audit and exact deduplication"]
  B --> C["Load PostgreSQL"]
  C --> D["dbt build and data tests"]
  D --> E["Publish validated snapshot"]
  E --> F["Power BI monthly views"]
  E --> G["Statistical outlook and checked Qwen brief"]
  E --> H["Optional Snowflake sync and readback"]
```

Airflow runs on demand. Report and cloud sync depend on the publication from their own run. Power BI refreshes separately. The [six-task run](docs/images/airflow-run.png) succeeded in 7m 17s on an unchanged input; that duration is not a benchmark for a fresh 17-million-row load.

PostgreSQL is the system of record. See the [acceptance record](acceptance/RUN_EVIDENCE.md) for observed runs.

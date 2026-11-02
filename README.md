# Retail Distribution Intelligence

A portfolio project for reliable retail distribution analytics and evidence-backed automated reporting, using public Iowa Liquor Sales data.

**Status: initial scaffold and local CSV inspection utility.** Snowflake ingestion, dbt transformations, Airflow orchestration, Power BI reports, and AI reporting are planned, not implemented. No cloud deployment or business-impact claim is made.

## Business problem

An analyst needs to understand changes in purchasing activity across stores and products without mistaking incomplete, duplicated, or lower-precision data for business performance. The intended system preserves source snapshots, validates reporting eligibility, and generates reviewable explanations supported by query results.

The source describes purchases by licensed retail establishments. It does not represent individual consumer checkout transactions or inventory levels.

## Available now

- A standard-library Python CLI that inspects explicit CSV inputs, validates their 23-column header and primitive types, preserves leading-zero identifiers, and produces a content-based input manifest.
- Synthetic fixtures and unit tests for input validation and manifest identity.
- Business requirements, data contract, metric definitions, target architecture, implementation roadmap, and recorded source-data findings.
- A GitHub Actions CI workflow for the inspection utility.

The manifest is an input inventory, not a warehouse load or publication approval. A successful inspection does not establish source completeness or business correctness.

## Quick start

Requires Python 3.11 or later. No Snowflake account, API key, or third-party runtime package is needed for the fixture demo.

```bash
python scripts/inspect_snapshot.py --year 2026 --files data/fixtures/transactions.csv --output artifacts/demo-manifest.json
python -m unittest discover -s tests -v
```

See [Getting started](docs/getting_started.md) for Windows and real-data instructions.

## Target stack

| Component | Intended responsibility | Status |
|---|---|---|
| Python | Input inspection and snapshot ingestion | Inspection only |
| Snowflake | Raw storage, analytics and publication versions | Planned |
| dbt Core | Transformations, lineage and data tests | Planned |
| Airflow | Data workflow scheduling and recovery | Planned |
| Power BI | Business analysis and data reliability views | Planned |
| LangGraph + LLM | Evidence-backed report workflow with human review | Planned |
| PostgreSQL | Application state/checkpoints if required | Planned |

## Documentation

- [Business requirements](docs/business_requirements.md)
- [Data sources and attribution](docs/data_sources.md)
- [Discovery findings](docs/data_discovery.md)
- [Data contract](docs/data_contract.md)
- [Data dictionary](docs/data_dictionary.md)
- [Metric definitions](docs/metric_definitions.md)
- [Target architecture](docs/architecture.md)
- [Warehouse model](docs/warehouse_model.md)
- [Quality and publication policy](docs/quality_policy.md)
- [Evaluation plan](docs/evaluation_plan.md)
- [Implementation roadmap](docs/roadmap.md)
- [Demo plan](docs/demo_plan.md)
- [Architecture decisions](docs/decisions/README.md)

## Dataset boundary

Raw downloads are not bundled. The initial 2025 working set consists of parts 1–4; the supplied part 5 duplicates records already present in parts 3–4 and must not be appended. The 2026 working set consists of four CSV members in the supplied ZIP. These are working exports, not certified reconciliations to the originating transaction system.

## Limitations

Invoice identifier semantics change across the supplied data; cross-period invoice counts are not yet approved. Price fields are missing for early 2025, and numeric precision differs across periods. Forecasting, net-profit analysis, inventory optimization, and causal explanations are out of the initial implementation scope.

## License

Repository code and original documentation: [MIT](LICENSE). Dataset terms and attribution are separate: [Data sources](docs/data_sources.md). Synthetic fixtures are explicitly labeled and are not empirical findings.

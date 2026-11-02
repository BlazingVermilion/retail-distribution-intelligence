# dbt migration validation evidence

> Historical migration evidence. For the current implementation see [run evidence](acceptance/RUN_EVIDENCE.md) and the repository’s GitHub Actions checks.

Prepared 2026-10-23. Scope: supplied overlay, not the user's running machine.

## Executed successfully

- Installed dbt-core 1.9.10 and dbt-postgres 1.9.1 into an isolated Python 3.12 environment.
- Parsed the dbt project with legacy comparisons enabled: 9 models, 34 tests and the startup hook.
- Parsed all 21 model/singular-test SQL files and the generated conversion-function SQL using PostgreSQL's parser through pglast.
- Python syntax compilation for the dbt wrapper and integration runner.

These checks establish configuration and syntax validity, not database execution correctness.

## Not executed here

- PostgreSQL integration, full dbt build, data tests, parity comparisons and repeated-build behavior.
- GitHub Actions workflow execution.
- The user's 17,337,629-row dataset and runtime/resource measurements.
- Power BI refresh against development outputs, Snowflake, Airflow or AI reporting.

The local environment denied operating-system user switching needed to start an
isolated PostgreSQL server. No successful runtime result is inferred from static parsing.

## Executable integration coverage supplied

The PostgreSQL 17 CI workflow creates an empty test database, loads 11 synthetic
records, builds the uploaded legacy SQL reference and runs the dbt migration twice.
It compares both implementations and checks same-invoice retention, missing and
invalid numeric values, overflow handling, leading-zero identifiers, exact-month
YoY, zero/negative comparison bases, and known precision-review warnings.
It deliberately changes a monthly total, expects the preservation test to fail,
then rebuilds downstream models. This workflow remains pending its first actual run.

The copied legacy SQL is a migration-equivalence oracle, not an independent proof
of business correctness. The explicit fixture assertions and conversion test add
separate checks for selected edge cases.

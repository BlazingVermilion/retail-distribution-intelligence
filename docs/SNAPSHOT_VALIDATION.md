# Step 10B validation evidence

Prepared 2026-10-31.

## Prior local execution evidence supplied by the user

Step 10A successfully published run `13b211bf-0b94-40fa-86e4-46258183d941`,
snapshot `17344d4b-961e-4f23-b0e5-9eca35033df7`, with 27 data tests:
26 passed and one known source-quality warning covering 81 months.
The hook plus tests completed in 36.85 seconds. Power BI screenshots displayed
the new validation timestamp and the expected reported measures.
No UNCHANGED replay log was supplied before this release.

## Executed for this release

- Installed the supplied requirements in isolated Python 3.12; pip check passed.
- 16 snapshot/build-evidence unit tests passed.
- 9 existing publication unit tests passed after integration changes.
- dbt 1.9.10 project parsing passed.
- Python syntax compilation passed.
- Embedded PostgreSQL 18.6 / PGlite 0.5.11 SQL checks passed:
  migration 011, dedicated loader privileges, source replacement, rollback after
  a deliberately injected post-TRUNCATE error, build-state invalidation and
  unchanged published BI rows during source replacement.

Preparation tests execute the actual SQLite audit on small CSV fixtures. They
cover cross-file/cross-year exact duplicates, same-invoice variants, leading-zero
codes, decimal strings, changed bytes with unchanged row counts, retained old
bundles, cache replay, corruption rejection and preservation of the previous
latest pointer after failed preparation.

A PostgreSQL 17.5 PGlite 0.3.14 trial failed during the older fixture's database
CONNECT grant with `tuple concurrently deleted`, before migration 011 ran.
That embedded trial is not counted as a passing PostgreSQL 17 integration.
The PostgreSQL 18.6 SQL smoke check is additional evidence, not a substitute.

## Not executed here

- Python driver + actual dbt CLI + PostgreSQL 17 Docker end-to-end integration.
- Multi-session concurrency integration on PostgreSQL 17.
- The user's complete 17,337,629-row preparation/load/rebuild or its resource use.
- GitHub Actions execution, Airflow, Snowflake or AI reporting.

The supplied PostgreSQL 17 CI test runs the previous publication integration,
then tests changed input loading, exact replay, rejection of concurrent loading,
injected failure after TRUNCATE, same-row-count stale-build rejection, successful
rebuild/publication and final UNCHANGED replay. It remains pending execution.

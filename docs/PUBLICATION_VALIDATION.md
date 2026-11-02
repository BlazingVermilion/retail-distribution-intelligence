# Publication validation evidence

Prepared 2026-10-24. User reported completing the local dbt stage; exact runtime
logs and timings were not provided in this turn.

## Executed during preparation

1. Nine Python unittest cases passed: complete evidence, known warning, structural
   fail/error/skipped/warn rejection, missing/duplicate results, stale invocation,
   missing required test, parity rejection, repeatable identity and changed inputs.
2. Python syntax compilation passed for publication and integration entry points.
3. SQL smoke tests passed on PGlite 0.5.11, PostgreSQL 18.6 compiled to WebAssembly:
   - Legacy BI rows preserved exactly by migration 010.
   - All 41 BI columns retained.
   - Publisher can acquire source/model locks using its own privileges.
   - Transactional publication pointer switch succeeds.
   - Deliberate transaction failure rolls the pointer back.
   - Explicit pointer rollback restores a retained snapshot.
   - BI role can read the public view but not publication storage directly.
   - Publisher cannot UPDATE source data.
   - Future dbt-owned tables receive SELECT/MAINTAIN grants.

The smoke harness executes PostgreSQL SQL and role checks, but renders model SQL
with a limited harness rather than running dbt. It does not establish behavior
of concurrent sessions, Python database connections or Docker PostgreSQL 17.

## Supplied but not executed here

The PostgreSQL 17 GitHub Actions integration runs the actual dbt CLI and publisher
with synthetic data, checks a second publication returns UNCHANGED, tests two
sessions competing for publication/data locks, injects a monthly total mismatch,
checks the old snapshot survives, rebuilds the candidate and exercises rollback.

No successful GitHub CI run, Docker PostgreSQL 17 end-to-end run, 17-million-row
publication runtime, or Power BI refresh is claimed from preparation checks.

## Existing test fixture correction

The step-9 test copy of migration 002 granted CONNECT on the literal database
`retail_analytics`. Its integration harness instead creates `retail_analytics_ci`.
The test fixture now uses current_database() for this grant. Actual production
migration 002 and all ingestion behavior are unchanged.

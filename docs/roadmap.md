# Delivery status

The PostgreSQL warehouse, dbt publication, Airflow DAG, Power BI report, classical outlook, checked local reporting and monthly Snowflake mirror have local execution evidence. See [run evidence](acceptance/RUN_EVIDENCE.md).

Release gates: green PR checks, review, merge and a successful version tag build with image pullback. [Release procedure](RELEASE.md). Failure-injection drills remain [deferred](STRESS_FAIL_TESTS.md).

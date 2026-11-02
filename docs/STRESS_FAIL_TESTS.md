# Stress and failure tests — final project phase

Owner: Huy Vu. Status: DEFERRED, not passed. Run this checklist after all planned components (including Snowflake, evaluated AI reporting and portfolio integration) are implemented. It is not a prerequisite for starting Snowflake.

## AF-01 — malformed source, publication continuity and recovery

- [ ] With no active DAG, record the current publication snapshot ID, the number of months served by marts.bi_sales_monthly and the latest published month.
- [ ] Follow the failure drill in README_AIRFLOW.md: mount an isolated directory with one invalid-header CSV as RDI_RAW_DIR for the scheduler. Preserve the previous mount setting. Never edit the real source.
- [ ] Trigger a new retail_snapshot_pipeline run. Save the DAG run ID, failed prepare log and evidence that load, dbt_build and publish did not execute.
- [ ] While the DAG is failed, run the same BI query. Require an unchanged snapshot ID, month count and latest month, and a readable BI view.
- [ ] Restore the original mount, confirm all intended year folders, then clear prepare and its downstream tasks for this run only.
- [ ] Require four successful tasks. For unchanged real input, check load SKIPPED and publish UNCHANGED. Record the final snapshot ID.
- [ ] Archive before/after SQL results and task logs without credentials. Record PASS or FAIL, execution date, evidence links and any defect.

Evidence already observed separately: four successful Airflow tasks, replay load SKIPPED on 17,337,629 rows and publication UNCHANGED. These do not establish failure recovery or performance under load.

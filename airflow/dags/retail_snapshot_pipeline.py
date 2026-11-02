"""Manually refresh the local Iowa warehouse and its validated Power BI snapshot."""
from datetime import datetime, timedelta, timezone

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

with DAG(
    dag_id="retail_snapshot_pipeline",
    schedule=None,
    start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=1,
    tags=["iowa", "postgres", "dbt"],
) as dag:
    tasks = []
    for step in ("prepare", "load", "dbt_build", "publish", "report"):
        # Only fixed task names enter shell syntax. The run ID is data passed via the environment.
        tasks.append(BashOperator(
            task_id=step,
            bash_command=f"exec /opt/airflow/pipeline-venv/bin/python /opt/project/scripts/airflow_task.py {step}",
            env={"RDI_RUN_ID": "{{ run_id }}"},
            append_env=True,
            do_xcom_push=False,
            skip_on_exit_code=None,
            retries=0 if step == "prepare" else 1,
            retry_delay=timedelta(minutes=2),
            execution_timeout=timedelta(hours=12),
        ))
    for upstream, downstream in zip(tasks, tasks[1:]):
        upstream >> downstream

    # Both consumers require a successful publication; neither depends on its sibling.
    tasks[3] >> BashOperator(
        task_id="sync_snowflake",
        bash_command="exec /opt/airflow/pipeline-venv/bin/python /opt/project/scripts/airflow_snowflake.py",
        env={"RDI_RUN_ID": "{{ run_id }}"}, append_env=True,
        do_xcom_push=False, skip_on_exit_code=99, retries=1,
        retry_delay=timedelta(minutes=2), execution_timeout=timedelta(minutes=15),
    )

FROM apache/airflow:3.1.7-python3.12
USER airflow
COPY --chown=airflow:0 requirements-dbt.txt requirements-publication.txt requirements-snapshots.txt /tmp/pipeline-requirements/
# dbt and Airflow have independent dependency constraints. Never install dbt in Airflow's interpreter.
RUN python -m venv /opt/airflow/pipeline-venv \
 && PIP_USER=false /opt/airflow/pipeline-venv/bin/python -m pip install --no-cache-dir -r /tmp/pipeline-requirements/requirements-snapshots.txt \
 && PIP_USER=false /opt/airflow/pipeline-venv/bin/python -m pip install --no-cache-dir numpy==2.2.6 scipy==1.15.3 \
 && /opt/airflow/pipeline-venv/bin/python -m pip check

# CI and delivery

Pull requests and pushes to main run offline fixture checks on Python 3.11/3.12, dbt against PostgreSQL 17, publication and snapshot integration, and the Airflow image/DAG checks. The default offline suite includes narrative and Snowflake adapter contracts. Historical TCN tests remain available separately with the experiment's dependencies: python -m unittest discover -s tests/experiments -v.

After review and merge, a maintainer may tag the tested main commit v0.1.0. The release workflow repeats all five checks at the tagged commit, builds the base Airflow runtime, publishes version and commit tags to GHCR, and pulls and starts the versioned image. See the release job for the image name and digest. This is delivery of the local runtime; DAGs and scripts are repository mounts. The Snowflake-enabled scheduler uses its separate Dockerfile and connector version. No cloud deployment or released image is claimed before a successful tag run.

# ADR-003 — One data workflow and one reporting workflow

Status: accepted for V1 design.

Decision: Airflow will coordinate data ingestion, transformation and publication; LangGraph will coordinate evidence-backed report generation and review. Snowflake/dbt serve analytical storage and SQL transformation. Kafka, Spark, RAG and multi-agent reporting are outside V1 unless a concrete requirement justifies them.

Consequences: smaller operational scope for a solo project. The first runnable slice is local inspection; cloud services are added only with integration tests and cost measurement.

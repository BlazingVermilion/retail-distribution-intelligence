# Orchestration boundary

Airflow coordinates local ingestion, dbt, publication and both downstream consumers. PostgreSQL holds the analytical state. Python and Ollama produce the monthly report; deterministic code owns the figures, protected caveats and checks. Snowflake receives the optional KPI mirror. LangGraph, RAG and autonomous external messaging are not part of this implementation.

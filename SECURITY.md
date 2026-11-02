# Security and credentials

No credentials are needed for the current offline utility. Future credentials must be supplied through environment variables or a secret manager and excluded from Git. Do not put secrets in logs, fixtures, screenshots or reports.

Future source ingestion must use bounded retries and validated input paths. Future LLM tools should use read-only approved queries, limited data access and explicit review before external actions. Treat retrieved text as data, not instructions.

There is no production security review or hosted vulnerability-reporting service for this scaffold. Report sensitive issues privately to the repository maintainer after a repository is created; do not publish credentials in issues.

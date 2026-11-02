# Implementation roadmap

| Milestone | Scope | Completion evidence | Current status |
|---|---|---|---|
| M0 | Requirements, contract and source investigation | Reviewed docs and open decisions | Initial documentation available |
| M1 | Local manifests and ingestion safeguards | Fixture tests plus real-export validation | Inspector implemented; overlap/publication gates pending |
| M2 | Snowflake RAW loader | Reconciled load and replay test | Not implemented |
| M3 | dbt staging, fact and monthly mart | Data tests and totals reconciliation | Not implemented |
| M4 | Publication and Airflow | Success, failure and recovery demonstrations | Not implemented |
| M5 | Power BI views | DAX/SQL parity and quality display | Not implemented |
| M6 | AI reports | Evaluation set, evidence validation, review workflow | Not implemented |
| M7 | Forecast experiment | Honest chronological baseline comparison | Deferred |

## Next implementation slice

1. Add warehouse precision/scale and required-field rules.
2. Add persistent run registry and snapshot membership/completeness checks.
3. Implement explicit overlap handling without deleting legitimate duplicate rows.
4. Build a Snowflake fixture loader and exact reconciliation.
5. Implement one monthly mart before adding further dimensions or services.

Every completed feature needs reproducible evidence. Keep README status synchronized with actual behavior. Do not present the target stack as implemented experience until demonstrated.

# Source and publication contract

The CSV header and column order must match the [source schema](../configs/source_schema.json). Preserve identifier strings, including leading zeros. Raw inputs retain their original bytes. The audit compares all 23 parsed source fields across files and years; the deduplicated export retains one copy of each exact record. An invoice ID alone is not a business key. See [audit implementation](../scripts/audit_duplicates.py).

Typed models keep missing and invalid field indicators. Reported and calculated amounts remain separate; missing prices are not imputed from later periods. Keep signed observations; a negative row is not by itself proof of a return. Publication tests protect row counts, model relationships and monthly totals. The technical gate does not certify the original publisher supplied every transaction in a period.

PostgreSQL is the analytical system of record. A published snapshot pins downstream reporting and monthly cloud parity to one version. See [warehouse relations](warehouse_model.md).

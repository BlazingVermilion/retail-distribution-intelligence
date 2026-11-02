# Warehouse model — target

| Schema / object | Grain | Logical key |
|---|---|---|
| CONTROL.INGESTION_RUNS | One execution attempt | run_id |
| CONTROL.SNAPSHOTS | One selected source snapshot | snapshot_id |
| CONTROL.SNAPSHOT_FILES | One source file in snapshot | snapshot_id + file_id |
| RAW.TRANSACTION_RECORDS | One source record | snapshot_id + file_id + source_row_number |
| CONTROL.QUALITY_RESULTS | One check on a scope | check_result_id |
| CONTROL.RELEASES | One publishable analytical version | release_id |
| CONTROL.RELEASE_SNAPSHOTS | Selected snapshot for a year | release_id + source_year |
| ANALYTICS.FCT_TRANSACTION_RECORDS | One standardized source record | source technical key |
| ANALYTICS.DIM_DATE | Calendar day | date |
| ANALYTICS.DIM_STORE_VERSION | Observed store attributes | version surrogate key |
| ANALYTICS.DIM_PRODUCT_VERSION | Observed product attributes | version surrogate key |
| ANALYTICS.MART_MONTHLY_PERFORMANCE | Month within snapshot | snapshot_id + month |
| ANALYTICS.MART_MONTHLY_STORE | Store-month within snapshot | snapshot_id + month + store_no |
| ANALYTICS.MART_MONTHLY_CATEGORY | Category-month within snapshot | snapshot_id + month + category_key |

Logical uniqueness must be tested in transformations; declaring a key is not evidence it is enforced or correct.

## Dimension version strategy

Attach facts to the observed attribute combination on their source row. Use a deterministic canonical representation with unambiguous separators/null encoding for version hashing. A code can have multiple observed versions. Do not join facts to all versions by business code alone. These are observed versions, not a claim of reconstructed effective-dated SCD2 history.

## RAW metadata

Keep snapshot_id, source_file_id, source_row_number, ingested_at and source_row_hash. Retain all 23 source fields. Store the source file URI/checksum in CONTROL. Avoid a volatile ingestion timestamp in source content identity.

## Release selection

Marts retain snapshot_id. Serving views select the snapshot mapped by release_id for each year. Reject multiple active mappings for the same year. Never sum every historical snapshot. Failed candidates remain inspectable but unavailable to ordinary report consumers.

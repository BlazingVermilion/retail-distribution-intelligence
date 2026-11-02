# Warehouse relations

| Relation | Grain and purpose |
|---|---|
| staging.iowa_sales_exact | One retained source row after global exact-row deduplication |
| dbt_dev.fact_sales | One modeled distribution record, with an audit row ID; invoice ID alone is not its key |
| dbt_dev.dim_store / dim_product / dim_date | Store, product and calendar attributes used to interpret facts |
| dbt_dev.bi_sales_monthly | Monthly candidate for validation |
| publication.monthly_snapshots | Monthly observations belonging to a retained snapshot |
| marts.bi_sales_monthly | Published monthly view for Power BI |
| RDI_PILOT_DB.DBT_PILOT.MONTHLY_KPI_SNAPSHOTS | Cloud mirror, one row per snapshot and month |

The [models](../dbt/models), [publication migration](../warehouse/postgres/010_publication.sql) and [cloud sync implementation](../scripts/sync_snowflake_kpis.py) define the physical contracts.

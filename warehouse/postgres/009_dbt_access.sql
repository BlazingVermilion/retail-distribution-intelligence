-- Run once as administrator. Existing accounts/schemas are not modified.
-- Set the password interactively with psql \password after commit.
BEGIN;
CREATE ROLE retail_dbt LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE SCHEMA dbt_dev AUTHORIZATION retail_dbt;
GRANT USAGE ON SCHEMA staging, marts TO retail_dbt;
GRANT SELECT ON staging.iowa_sales_exact TO retail_dbt;
GRANT SELECT ON marts.fact_sales, marts.dim_store, marts.dim_product,
 marts.dim_date, marts.sales_monthly, marts.v_sales_monthly_kpis, marts.bi_sales_monthly TO retail_dbt;
DO $$ BEGIN
 EXECUTE format('GRANT CONNECT ON DATABASE %I TO retail_dbt', current_database());
 IF has_schema_privilege('retail_dbt','marts','CREATE')
 OR has_schema_privilege('retail_dbt','staging','CREATE')
 OR has_table_privilege('retail_dbt','staging.iowa_sales_exact','INSERT')
 OR has_table_privilege('retail_dbt','marts.fact_sales','UPDATE') THEN
  RAISE EXCEPTION 'Unexpected PUBLIC privileges; review permissions before dbt setup';
 END IF;
END $$;
COMMIT;

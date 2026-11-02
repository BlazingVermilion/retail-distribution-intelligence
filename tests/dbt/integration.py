"""Exercise dbt migration against a disposable PostgreSQL 17 CI database.

Requires psql on PATH and TEST_DATABASE_URL. Never point this at user data.
The script refuses a database whose name does not end in _ci or has user tables.
"""
from pathlib import Path
import os
import subprocess
import sys
from urllib.parse import urlparse
import psycopg2

ROOT = Path(__file__).resolve().parents[2]
url = os.environ["TEST_DATABASE_URL"]
parsed = urlparse(url)
if not parsed.path.endswith("_ci"):
    raise SystemExit("Use a disposable database with a name ending in _ci.")
connection = psycopg2.connect(url)
connection.autocommit = True
with connection.cursor() as cur:
    cur.execute("select count(*) from information_schema.tables where table_schema not in ('pg_catalog','information_schema')")
    if cur.fetchone()[0]:
        raise SystemExit("The integration database must be empty.")

def migration(path):
    subprocess.run(["psql", url, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(path)], check=True)

legacy = Path(__file__).parent / "legacy_sql"
for name in ("001_create_schemas.sql", "002_postgres_loader.sql"):
    migration(legacy / name)

# Same invoice and product with different values must remain separate records.
# Gapped months exercise exact-calendar YoY instead of positional LAG(12).
rows = [
    (1, '2024-07-02', '12.34', '24.68', '2', '1.50'),
    (2, '2025-07-02', '12.34', '24.68', '2', '1.50'),
    (3, '2025-07-02', '12.34', '24.69', '2', '1.50'),
    (4, '2025-08-01', '', '8.75', '1', '0.75'),
    (5, '2025-11-01', '8', '17', '2', '1.5'),
    (6, '2026-01-01', '10', '-10', '-1', '-0.75'),
    (7, '2025-02-01', '0', '0', '0', '0'),
    (8, '2026-02-01', '5', '5', '1', '0.75'),
    (9, '2025-03-01', '5', '-5', '-1', '-0.75'),
    (10, '2026-03-01', '5', '5', '1', '0.75'),
    (11, '2026-04-01', 'bad', '', '9223372036854775808', 'bad'),
]
with connection.cursor() as cur:
    cur.execute("select column_name from information_schema.columns where table_schema='staging' and table_name='iowa_sales_exact' order by ordinal_position")
    columns = [x[0] for x in cur.fetchall()]
    for audit_id, date, price, sales, bottles, liters in rows:
        record = dict.fromkeys(columns, '')
        record.update(_audit_row_id=audit_id, invoice_id='SAME-INVOICE', ordered_on=date,
                      store_no='0001', store_name='Observed '+str(audit_id), item_no='0010',
                      im_desc='Fixture', pack='6', bottle_volume_ml='750', state_bottle_retail=price,
                      sales_dollars=sales, sales_bottles=bottles, sales_liters=liters)
        cur.execute('insert into staging.iowa_sales_exact values ('+','.join(['%s']*len(columns))+')',
                    [record[c] for c in columns])
for name in ('003_typed_views.sql','005_reconciliation_views.sql','006_build_marts.sql',
             '007_monthly_kpis.sql','008_powerbi_access.sql'):
    migration(legacy / name)
migration(ROOT / 'warehouse/postgres/009_dbt_access.sql')
password = 'fixture-only-dbt-password'
with connection.cursor() as cur:
    cur.execute('alter role retail_dbt password %s', (password,))
os.environ.update(DBT_ENV_SECRET_PASSWORD=password, DBT_HOST=parsed.hostname or '127.0.0.1',
                  DBT_PORT=str(parsed.port or 5432), DBT_DATABASE=parsed.path.lstrip('/'))

def dbt(*args, expected=0):
    result = subprocess.run([sys.executable, str(ROOT/'scripts/run_dbt.py'), *args])
    if result.returncode != expected:
        raise AssertionError(f'dbt returned {result.returncode}; expected {expected}')

# Repeat the same build to exercise table replacement and dependency handling.
for _ in range(2):
    dbt('build', '--vars', '{compare_legacy: true}')
with connection.cursor() as cur:
    cur.execute("select reported_sales_yoy_pct from dbt_dev.v_sales_monthly_kpis where month_start='2025-07-01'")
    assert cur.fetchone()[0] > 100  # Two retained same-invoice rows, not deduplicated by invoice.
    cur.execute("select count(*) from dbt_dev.v_sales_monthly_kpis where month_start in ('2026-02-01','2026-03-01') and yoy_calculation_status='NONPOSITIVE_BASE' and reported_sales_yoy_pct is null")
    assert cur.fetchone()[0] == 2
    cur.execute("select sales_bottles, state_bottle_retail, _invalid_fields from dbt_dev.fact_sales where _audit_row_id=11")
    bottles, price, flags = cur.fetchone()
    assert bottles is None and price is None and 'sales_bottles' in flags
    # A preservation regression must produce a failing test, not a warning.
    cur.execute("update dbt_dev.sales_monthly set reported_sales_dollars=reported_sales_dollars+1 where month_start='2025-07-01'")
dbt('test', '--select', 'monthly_preservation', expected=1)
dbt('build', '--select', 'sales_monthly+', '--vars', '{compare_legacy: true}')
connection.close()
print('Integration, parity, repeat-build and deliberate-failure checks passed.')

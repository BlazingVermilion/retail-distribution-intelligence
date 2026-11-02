"""Full PostgreSQL 17 publication integration; disposable empty *_ci database only.

Runs the existing dbt migration fixtures first. This test changes only the
isolated fixture database and uses fixed non-production passwords.
"""
from pathlib import Path
import os
import runpy
import subprocess
import sys
from uuid import uuid4
import psycopg2

ROOT = Path(__file__).resolve().parents[2]
# The existing harness checks an empty *_ci database before any mutation.
runpy.run_path(str(ROOT / 'tests/dbt/integration.py'), run_name='__main__')
url = os.environ['TEST_DATABASE_URL']
connection = psycopg2.connect(url)
connection.autocommit = True
with connection.cursor() as cur:
    load_run = str(uuid4())
    cur.execute("""INSERT INTO ops.pg_load_runs
        (run_id,target_table,source_path,source_sha256,expected_rows,loaded_rows,state)
        VALUES(%s,'staging.iowa_sales_exact','synthetic_fixture',%s,11,11,'COMPLETED')""", (load_run, 'a'*64))
    cur.execute("""INSERT INTO ops.pg_loaded_exports
        (target_table,source_sha256,source_path,expected_rows,mode,summary_sha256,audit_summary,run_id)
        VALUES('staging.iowa_sales_exact',%s,'synthetic_fixture',11,'full',%s,'{}',%s)""", ('a'*64,'b'*64,load_run))
subprocess.run(['psql',url,'-X','-v','ON_ERROR_STOP=1','-f',str(ROOT/'warehouse/postgres/010_publication.sql')],check=True)
password = 'fixture-publisher-password'
with connection.cursor() as cur:
    cur.execute('ALTER ROLE retail_publisher PASSWORD %s', (password,))
os.environ['PG_PUBLISHER_PASSWORD'] = password

def scalar(query):
    with connection.cursor() as cur:
        cur.execute(query)
        return cur.fetchone()[0]

def invoke(*args, expected=0):
    result = subprocess.run([sys.executable,str(ROOT/'scripts/publish_snapshot.py'),*args])
    assert result.returncode == expected, (args,result.returncode,expected)

initial = scalar('SELECT snapshot_id::text FROM publication.current_snapshot')
invoke('publish')
published = scalar('SELECT snapshot_id::text FROM publication.current_snapshot')
assert published != initial
count = scalar('SELECT COUNT(*) FROM publication.snapshots')
invoke('publish')
assert scalar('SELECT snapshot_id::text FROM publication.current_snapshot') == published
assert scalar('SELECT COUNT(*) FROM publication.snapshots') == count
assert scalar("SELECT state FROM publication.runs ORDER BY started_at DESC LIMIT 1") == 'UNCHANGED'
# Independent sessions verify serialization and physical table locks.
with connection.cursor() as cur:
    cur.execute('SELECT pg_advisory_lock(690010)')
    invoke('publish', expected=1)
    cur.execute('SELECT pg_advisory_unlock(690010)')
assert scalar('SELECT snapshot_id::text FROM publication.current_snapshot') == published
# A write lock held by another session must prevent publication, not race it.
blocker = psycopg2.connect(url)
with blocker.cursor() as cur:
    cur.execute('UPDATE dbt_dev.sales_monthly SET reported_sales_dollars=reported_sales_dollars')
invoke('publish', expected=1)
blocker.rollback()
blocker.close()
assert scalar('SELECT snapshot_id::text FROM publication.current_snapshot') == published
# Committed bad development data must also leave the published snapshot intact.
with connection.cursor() as cur:
    cur.execute("UPDATE dbt_dev.sales_monthly SET reported_sales_dollars=reported_sales_dollars+1 WHERE month_start='2025-07-01'")
invoke('publish', expected=1)
assert scalar('SELECT snapshot_id::text FROM publication.current_snapshot') == published
assert scalar('SELECT COUNT(*) FROM publication.snapshots') == count
# Restore candidate data before testing future dbt object grants.
subprocess.run([sys.executable,str(ROOT/'scripts/run_dbt.py'),'build','--select','sales_monthly+'],check=True)
invoke('publish')
assert scalar('SELECT COUNT(*) FROM publication.snapshots') == count
invoke('rollback','--snapshot',initial,'--reason','Integration recovery check')
assert scalar('SELECT snapshot_id::text FROM publication.current_snapshot') == initial
invoke('rollback','--snapshot',published,'--reason','Restore validated fixture publication')
assert scalar('SELECT snapshot_id::text FROM publication.current_snapshot') == published
connection.close()
print('PostgreSQL publication, idempotence, concurrency, failed-test preservation and rollback checks passed.')

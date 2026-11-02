"""End-to-end replacement/recovery test on an empty disposable *_ci database.

The inherited publication harness checks the database name and emptiness before
creating fixtures. Never run against the user's retail_analytics database.
"""
import csv
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import psycopg2

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from snapshot_ingestion import prepare,load,COLUMNS

runpy.run_path(str(ROOT/'tests/publication/integration.py'),run_name='__main__')
url=os.environ['TEST_DATABASE_URL']
connection=psycopg2.connect(url);connection.autocommit=True
subprocess.run(['psql',url,'-X','-v','ON_ERROR_STOP=1','-f',str(ROOT/'warehouse/postgres/011_snapshot_ingestion.sql')],check=True)
with connection.cursor() as cur:
    cur.execute('ALTER ROLE retail_snapshot_loader PASSWORD %s',('fixture-snapshot-password',))
os.environ['PG_SNAPSHOT_PASSWORD']='fixture-snapshot-password'

def scalar(query):
    with connection.cursor() as cur:
        cur.execute(query);return cur.fetchone()[0]

def command(script,*args,expected=0):
    result=subprocess.run([sys.executable,str(ROOT/'scripts'/script),*args])
    assert result.returncode==expected,(script,args,result.returncode)

def published():return scalar('SELECT snapshot_id::text FROM publication.current_snapshot')
def identity():return scalar("SELECT source_sha256 FROM ops.pg_loaded_exports WHERE target_table='staging.iowa_sales_exact'")

with tempfile.TemporaryDirectory() as directory:
    raw=Path(directory)/'raw';cache=Path(directory)/'cache'
    with connection.cursor() as cur:
        cur.execute('SELECT '+','.join(COLUMNS)+' FROM staging.iowa_sales_exact ORDER BY _audit_row_id')
        rows=cur.fetchall()
    def write_inputs(data):
        years=sorted({row[1][:4] for row in data})
        for year in years:
            path=raw/year/'fixture.csv';path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('w',newline='',encoding='utf-8') as stream:
                writer=csv.writer(stream);writer.writerow(COLUMNS)
                writer.writerows(row for row in data if row[1].startswith(year))
    write_inputs(rows)
    first=prepare(raw,cache)
    prior_publication=published()
    assert load(Path(first['bundle']))['state']=='COMPLETED'
    first_hash=identity()
    first_registry_run=scalar("SELECT run_id::text FROM ops.pg_loaded_exports WHERE target_table='staging.iowa_sales_exact'")
    assert load(Path(first['bundle']))['state']=='SKIPPED'
    assert scalar("SELECT run_id::text FROM ops.pg_loaded_exports WHERE target_table='staging.iowa_sales_exact'")==first_registry_run
    command('publish_snapshot.py','publish',expected=1)  # No build for the new identity.
    assert published()==prior_publication
    command('run_dbt.py','build')
    command('publish_snapshot.py','publish')
    first_publication=published()
    assert first_publication!=prior_publication
    changed=[list(row) for row in rows];changed[0][20]='999.99'
    write_inputs(changed)
    second=prepare(raw,cache)
    assert second['rows']==first['rows']  # Same row count, different business data.
    with connection.cursor() as cur:
        cur.execute('SELECT pg_advisory_lock_shared(690011)')
        try:
            try:load(Path(second['bundle']));raise AssertionError('Expected lock refusal')
            except ValueError as exc:assert 'busy' in str(exc).lower()
        finally:cur.execute('SELECT pg_advisory_unlock_shared(690011)')
    # Fail the active insert AFTER TRUNCATE to verify transactional source recovery.
    with connection.cursor() as cur:
        cur.execute("""CREATE FUNCTION ops.reject_fixture_insert() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Deliberate post-truncate failure'; END $$""")
        cur.execute('CREATE TRIGGER reject_fixture BEFORE INSERT ON staging.iowa_sales_exact FOR EACH STATEMENT EXECUTE FUNCTION ops.reject_fixture_insert()')
    try:
        try:load(Path(second['bundle']));raise AssertionError('Expected injected insertion failure')
        except Exception as exc:assert 'Deliberate post-truncate failure' in str(exc)
    finally:
        with connection.cursor() as cur:
            cur.execute('DROP TRIGGER reject_fixture ON staging.iowa_sales_exact')
            cur.execute('DROP FUNCTION ops.reject_fixture_insert()')
    assert identity()==first_hash
    assert scalar('SELECT COUNT(*) FROM staging.iowa_sales_exact')==11
    assert published()==first_publication
    assert load(Path(second['bundle']))['state']=='COMPLETED'
    assert identity()!=first_hash
    command('publish_snapshot.py','publish',expected=1)
    assert published()==first_publication
    command('run_dbt.py','build')
    command('publish_snapshot.py','publish')
    assert published()!=first_publication
    assert load(Path(second['bundle']))['state']=='SKIPPED'
    command('publish_snapshot.py','publish')
    assert scalar('SELECT state FROM publication.runs ORDER BY started_at DESC LIMIT 1')=='UNCHANGED'
connection.close()
print('PASS: actual snapshot ingestion, replay, source rollback after TRUNCATE, equal-count stale-build fence and end-to-end publication.')

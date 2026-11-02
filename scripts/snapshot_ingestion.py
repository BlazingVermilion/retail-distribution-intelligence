"""Prepare and load complete source snapshots without changing published BI data.

Prepare discovers CSVs in YYYY folders, fingerprints them, and reuses the existing
23-field exact-deduplication audit. Load stages a complete export before atomically
replacing the active landing table and registry. dbt build/publication are explicit
separate tasks, ready to become Airflow task dependencies.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

import audit_duplicates
from load_postgres import COLUMNS, HEADER, csv_records, file_digest, read_summary
from warehouse_state import WAREHOUSE_LOCK

ROOT = Path(__file__).resolve().parents[1]
POLICY = 'complete_source_snapshot_v1'
LOG = logging.getLogger('retail.snapshots')


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')


def atomic_json(path, value):
    temporary = path.with_name(path.name+'.'+str(uuid4())+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    temporary.replace(path)


def discover(root):
    """Discover every CSV under explicit year folders; reject ambiguous placement."""
    root = root.resolve(strict=True)
    candidates = sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower()=='.csv')
    if not candidates:
        raise ValueError('No CSV files under the input root.')
    inventory = []
    for path in candidates:
        relative = path.relative_to(root)
        if len(relative.parts)<2 or not re.fullmatch(r'[0-9]{4}',relative.parts[0]):
            raise ValueError(f'CSV must be under a YYYY directory: {relative}')
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f'Symlinked/external source is not allowed: {relative}')
        before=path.stat()
        digest=file_digest(path)
        after=path.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
            raise ValueError(f'Source changed while fingerprinting: {relative}')
        inventory.append({'path':relative.as_posix(),'year':int(relative.parts[0]),
                          'bytes':after.st_size,'sha256':digest})
    return sorted(inventory,key=lambda x:x['path'])


def identity_payload(inputs, audit_hash):
    return {'policy':POLICY,'audit_sha256':audit_hash,'inputs':inputs}


def inventory_diff(old, new):
    previous={x['path']:x['sha256'] for x in old}
    current={x['path']:x['sha256'] for x in new}
    return {'added':sorted(current.keys()-previous.keys()),
            'removed':sorted(previous.keys()-current.keys()),
            'changed':sorted(k for k in current.keys() & previous.keys() if current[k]!=previous[k])}


def validate_bundle(path):
    """Validate prepared bytes independently of the mutable original CSV directory."""
    path=Path(path).resolve(strict=True)
    if path.is_file():
        pointer=json.loads(path.read_text(encoding='utf-8'))
        identifier=pointer.get('bundle_id','')
        if not re.fullmatch('[0-9a-f]{64}',identifier):
            raise ValueError('Invalid latest.json bundle identifier.')
        path=path.parent/identifier
    manifest=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('state')!='PREPARED' or manifest.get('policy')!=POLICY:
        raise ValueError('Only complete prepared snapshot bundles may be loaded.')
    expected_id=hashlib.sha256(canonical(identity_payload(manifest['inputs'],manifest['audit_sha256']))).hexdigest()
    if manifest['bundle_id']!=expected_id or path.name!=expected_id:
        raise ValueError('Bundle identity does not match its inventory and audit policy.')
    report, summary_hash=read_summary(path/'summary.json')
    if summary_hash!=manifest['summary_sha256'] or report['exported_rows']!=manifest['rows']:
        raise ValueError('Audit summary changed after snapshot preparation.')
    if file_digest(path/'exact_deduplicated.csv')!=manifest['export_sha256']:
        raise ValueError('Prepared export changed after snapshot preparation.')
    if next(csv_records(path/'exact_deduplicated.csv',1),None) is None:
        raise ValueError('Prepared export is empty.')
    return path,manifest,report


def prepare(root,cache):
    root=root.resolve(strict=True)
    cache=cache.resolve()
    if cache==root or cache.is_relative_to(root):
        raise ValueError('Snapshot output must be outside the source input root.')
    cache.mkdir(parents=True,exist_ok=True)
    lock=cache/'prepare.lock'
    # A lock file serializes preparation on Windows and Linux. Hard-kill recovery
    # requires checking the recorded PID before manually removing a stale lock.
    with lock.open('x',encoding='utf-8') as handle:
        handle.write(json.dumps({'pid':os.getpid(),'started_at':datetime.now(timezone.utc).isoformat()}))
    try:
        LOG.info('Fingerprinting all source CSV files.')
        inputs=discover(root)
        audit_hash=file_digest(Path(audit_duplicates.__file__))
        payload=identity_payload(inputs,audit_hash)
        identifier=hashlib.sha256(canonical(payload)).hexdigest()
        final=cache/identifier
        if final.exists():
            _,manifest,_=validate_bundle(final)
            atomic_json(cache/'latest.json',{'bundle_id':identifier})
            return {'state':'REUSED','bundle':str(final),'files':len(inputs),'rows':manifest['rows']}
        work=cache/('.preparing-'+str(uuid4()))
        LOG.info('Auditing %s files across all discovered years.',len(inputs))
        report=audit_duplicates.run(work,inputs=[(f['year'],root/f['path']) for f in inputs])
        if discover(root)!=inputs or file_digest(Path(audit_duplicates.__file__))!=audit_hash:
            raise ValueError('Source inventory or audit implementation changed during preparation. Bundle not published.')
        # The auditor recorded its temporary location; bind the final retained path
        # before hashing the summary. Do not edit audited business values.
        report['audit_database']=str(final/'audit.sqlite')
        atomic_json(work/'summary.json',report)
        report,summary_hash=read_summary(work/'summary.json')
        manifest={**payload,'bundle_id':identifier,'state':'PREPARED',
                  'prepared_at':datetime.now(timezone.utc).isoformat(),'source_root':str(root),
                  'rows':report['exported_rows'],'summary_sha256':summary_hash,
                  'export_sha256':file_digest(work/'exact_deduplicated.csv')}
        atomic_json(work/'manifest.json',manifest)
        work.rename(final)
        atomic_json(cache/'latest.json',{'bundle_id':identifier})
        return {'state':'PREPARED','bundle':str(final),'files':len(inputs),'rows':manifest['rows'],
                'exact_duplicates_removed':report['exact_excess_occurrences']}
    finally:
        lock.unlink(missing_ok=True)


def settings():
    password=os.getenv('PG_SNAPSHOT_PASSWORD')
    if not password:
        raise ValueError('Set PG_SNAPSHOT_PASSWORD for retail_snapshot_loader in .env.')
    return {'host':os.getenv('DBT_HOST','127.0.0.1'),
            'port':int(os.getenv('DBT_PORT',os.getenv('POSTGRES_PORT','5433'))),
            'dbname':os.getenv('DBT_DATABASE',os.getenv('POSTGRES_DB','retail_analytics')),
            'user':'retail_snapshot_loader','password':password,'connect_timeout':15}


def replacement_policy(old_rows,new_rows,changes,allow_decrease,accept_removals,reason):
    if (allow_decrease or accept_removals) and not reason.strip():
        raise ValueError('A non-empty --reason is required for an input-removal or row-decrease exception.')
    if new_rows<old_rows and not allow_decrease:
        raise ValueError(f'Row count would decrease from {old_rows} to {new_rows}. Review scope; use --allow-row-decrease with --reason only if intentional.')
    if changes['removed'] and not accept_removals:
        raise ValueError('Previously loaded source files are absent. Review --accept-source-removals and --reason; do not replace with a partial extract.')


def load(path,allow_decrease=False,accept_removals=False,reason=''):
    import psycopg
    from psycopg import sql
    from psycopg.types.json import Jsonb
    bundle,manifest,report=validate_bundle(path)
    identifier=manifest['bundle_id']
    run_id=str(uuid4())
    connection=psycopg.connect(**settings(),autocommit=True)
    try:
        if not connection.execute('SELECT pg_try_advisory_lock(%s)',(WAREHOUSE_LOCK,)).fetchone()[0]:
            raise ValueError('Warehouse busy. Wait for dbt/publication/ingestion to finish.')
        if connection.execute("SELECT to_regclass('ops.snapshot_state')").fetchone()[0] is None:
            raise ValueError('Install migration 011 before loading a new snapshot.')
        connection.execute('''INSERT INTO ops.snapshot_bundles(bundle_id,manifest,bundle_path)
            VALUES(%s,%s,%s) ON CONFLICT(bundle_id) DO NOTHING''',(identifier,Jsonb(manifest),str(bundle)))
        stored=connection.execute('SELECT manifest FROM ops.snapshot_bundles WHERE bundle_id=%s',(identifier,)).fetchone()[0]
        # Rebuilding a deleted local cache can change audit summary path metadata.
        # Never silently rewrite the identity of a previously registered bundle.
        if stored['export_sha256']!=manifest['export_sha256'] or stored['summary_sha256']!=manifest['summary_sha256']:
            raise ValueError('Registered bundle bytes differ. Retain original bundles; investigate before retrying.')
        connection.execute('''INSERT INTO ops.pg_load_runs
            (run_id,target_table,source_path,source_sha256,expected_rows,state)
            VALUES(%s,'staging.iowa_sales_exact',%s,%s,%s,'RUNNING')''',
            (run_id,str(bundle/'exact_deduplicated.csv'),manifest['export_sha256'],manifest['rows']))
        try:
            with connection.transaction():
                connection.execute("SET LOCAL lock_timeout='5s'")
                connection.execute('SELECT pg_advisory_xact_lock(782902)')
                previous=connection.execute('''SELECT source_sha256,summary_sha256,expected_rows
                    FROM ops.pg_loaded_exports WHERE target_table='staging.iowa_sales_exact' AND mode='full' FOR UPDATE''').fetchone()
                if previous is None:
                    raise ValueError('Initial full load must exist before snapshot replacement.')
                active=connection.execute('''SELECT b.manifest FROM ops.snapshot_state s
                    LEFT JOIN ops.snapshot_bundles b USING(bundle_id) WHERE s.singleton''').fetchone()[0]
                changes=inventory_diff(active['inputs'] if active else [],manifest['inputs'])
                replacement_policy(previous[2],manifest['rows'],changes,allow_decrease,accept_removals,reason)
                connection.execute('''INSERT INTO ops.snapshot_load_attempts
                    VALUES(%s,%s,%s,%s,%s,%s)''',(run_id,identifier,previous[0],reason,accept_removals,allow_decrease))
                same=(previous[0]==manifest['export_sha256'] and previous[1]==manifest['summary_sha256'])
                if same:
                    actual=connection.execute('SELECT COUNT(*) FROM staging.iowa_sales_exact').fetchone()[0]
                    if actual!=manifest['rows']:
                        raise ValueError('Existing table count differs from the unchanged export registry.')
                    state='SKIPPED'
                else:
                    # Stage and validate before touching the active table. LIKE keeps
                    # field types, positive audit IDs and the primary-key constraint.
                    connection.execute('''CREATE TEMP TABLE snapshot_candidate
                        (LIKE staging.iowa_sales_exact INCLUDING ALL) ON COMMIT DROP''')
                    copy_sql=sql.SQL('COPY snapshot_candidate ({}) FROM STDIN').format(
                        sql.SQL(',').join(map(sql.Identifier,HEADER)))
                    sent=0
                    with connection.cursor().copy(copy_sql) as copy:
                        for record in csv_records(bundle/'exact_deduplicated.csv'):
                            copy.write_row(record)
                            sent+=1
                            if sent%250000==0: LOG.info('Staged %s rows; active source unchanged.',sent)
                    if sent!=manifest['rows']:
                        raise ValueError('Staged CSV count differs from the audit summary.')
                    validate_bundle(bundle)  # Recheck bytes before the source switch.
                    connection.execute('LOCK TABLE staging.iowa_sales_exact IN ACCESS EXCLUSIVE MODE')
                    # TRUNCATE is transactional in PostgreSQL. The global cooperative
                    # lock excludes project dbt readers; BI reads independent storage.
                    connection.execute('TRUNCATE staging.iowa_sales_exact')
                    connection.execute('INSERT INTO staging.iowa_sales_exact SELECT * FROM snapshot_candidate')
                    actual=connection.execute('SELECT COUNT(*) FROM staging.iowa_sales_exact').fetchone()[0]
                    if actual!=sent:
                        raise ValueError('Active source count differs after replacement; rolling back.')
                    connection.execute('''UPDATE ops.pg_loaded_exports SET source_sha256=%s,source_path=%s,
                        expected_rows=%s,summary_sha256=%s,audit_summary=%s,run_id=%s,loaded_at=clock_timestamp()
                        WHERE target_table='staging.iowa_sales_exact' ''',
                        (manifest['export_sha256'],str(bundle/'exact_deduplicated.csv'),actual,
                         manifest['summary_sha256'],Jsonb(report),run_id))
                    connection.execute('UPDATE ops.source_build_state SET valid=FALSE WHERE singleton')
                    connection.execute('ANALYZE staging.iowa_sales_exact')
                    state='COMPLETED'
                connection.execute('UPDATE ops.snapshot_state SET bundle_id=%s WHERE singleton',(identifier,))
                connection.execute('''UPDATE ops.pg_load_runs SET state=%s,loaded_rows=%s,
                    finished_at=clock_timestamp() WHERE run_id=%s''',(state,actual,run_id))
            return {'state':state,'run_id':run_id,'bundle_id':identifier,'rows':actual,'input_changes':changes,
                    'next':'Run a full dbt build, then publish. Power BI still uses the previous publication.'}
        except BaseException as exc:
            try:
                connection.execute('''UPDATE ops.pg_load_runs SET state='FAILED',finished_at=clock_timestamp(),
                    error_message=%s WHERE run_id=%s AND state='RUNNING' ''',(redact(str(exc)),run_id))
            except Exception:
                LOG.error('Could not record failure. Inspect registry and run history before retrying.')
            raise
    finally:
        connection.close()


def redact(message):
    for key in ('PG_SNAPSHOT_PASSWORD','PG_LOADER_PASSWORD','DBT_ENV_SECRET_PASSWORD','PG_PUBLISHER_PASSWORD','POSTGRES_PASSWORD'):
        value=os.getenv(key)
        if value: message=message.replace(value,'[REDACTED]')
    return message[:2000]


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=False)
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('plan','prepare'):
        p=sub.add_parser(name)
        p.add_argument('--input-root',type=Path,default=ROOT/'data/raw')
        if name=='prepare': p.add_argument('--cache-root',type=Path,default=ROOT/'artifacts/snapshots')
    p=sub.add_parser('load')
    p.add_argument('--bundle',type=Path,default=ROOT/'artifacts/snapshots/latest.json')
    p.add_argument('--allow-row-decrease',action='store_true')
    p.add_argument('--accept-source-removals',action='store_true')
    p.add_argument('--reason',default='')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        if args.command=='plan':
            files=discover(args.input_root)
            result={'state':'PLANNED','files':len(files),'years':sorted({f['year'] for f in files}),'inputs':files}
        elif args.command=='prepare': result=prepare(args.input_root,args.cache_root)
        else: result=load(args.bundle,args.allow_row_decrease,args.accept_source_removals,args.reason)
        print(json.dumps(result,indent=2))
        return 0
    except BaseException as exc:
        LOG.error('%s',redact(f'{type(exc).__name__}: {exc}'))
        return 130 if isinstance(exc,KeyboardInterrupt) else 1


if __name__=='__main__':
    raise SystemExit(main())

"""Manually replicate one immutable, dbt-validated monthly publication to Snowflake."""
import argparse
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from contextlib import contextmanager
import getpass
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
TABLE = 'RDI_PILOT_DB.DBT_PILOT.MONTHLY_KPI_SNAPSHOTS'
COLUMNS = 'snapshot_id,month_start,source_records,reported_sales_dollars,sales_bottles'
KEY = Path.home()/'.snowflake'/'rdi_pilot_key.p8'


def load_source(sid):
    # A typed UUID is the only interpolated input. This single statement sees a consistent snapshot.
    sql = f"""COPY (
      SELECT s.month_count,m.month_start,m.source_records,m.reported_sales_dollars,m.sales_bottles
      FROM publication.snapshots s JOIN publication.monthly_snapshots m ON m._snapshot_id=s.snapshot_id
      WHERE s.kind='DBT_VALIDATED' AND s.snapshot_id='{sid}'::uuid ORDER BY m.month_start
    ) TO STDOUT WITH CSV HEADER"""
    result = subprocess.run(['docker','compose','exec','-T','postgres','psql','-X','-q',
                             '-v','ON_ERROR_STOP=1','-U','postgres','-d','retail_analytics','-c',sql],
                            cwd=ROOT,capture_output=True,text=True)
    if result.returncode: raise ValueError(result.stderr.strip())
    data = list(csv.DictReader(io.StringIO(result.stdout)))
    return normalize(data)


def normalize(data):
    if not data or any(int(r['month_count']) != len(data) for r in data):
        raise ValueError('Snapshot missing, not dbt-validated, or inconsistent with its month count.')
    rows = []
    for r in data:
        m=date.fromisoformat(r['month_start'])
        if m.day!=1 or (rows and (m.year*12+m.month)-(rows[-1][0].year*12+rows[-1][0].month)!=1):
            raise ValueError(f'Duplicate, unordered, or missing month at {m}.')
        # Preserve NULL separately from zero. Refuse values that would be rounded by the target.
        dollars=Decimal(r['reported_sales_dollars']) if r['reported_sales_dollars'] else None
        if dollars is not None and (not dollars.is_finite() or dollars!=dollars.quantize(Decimal('.000000000001'))):
            raise ValueError(f'Unsupported money precision in {m}.')
        bottles=Decimal(r['sales_bottles']) if r['sales_bottles'] else None
        if bottles is not None and bottles!=bottles.to_integral_value():
            raise ValueError(f'Fractional bottle count in {m}.')
        rows.append((m,int(r['source_records']),dollars,int(bottles) if bottles is not None else None))
    return rows


def compare(source, target):
    if list(source)!=list(target):
        raise ValueError('Cloud rows differ in month keys, row count, source records, dollars or bottles. No overwrite.')


@contextmanager
def writer_lock():
    # All local writers use the same bind-mounted directory. mkdir is exclusive
    # across processes; a stale lock deliberately fails closed after a hard kill.
    lock = ROOT / 'artifacts' / 'snowflake' / 'monthly_kpis' / 'writer.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise RuntimeError('Monthly KPI writer lock exists. Check active writers before recovery.') from exc
    try:
        yield
    finally:
        lock.rmdir()


def connect(key_path=KEY, passphrase_file=None):
    from cryptography.hazmat.primitives import serialization as ser
    import snowflake.connector
    if not os.getenv('RDI_SF_ACCOUNT') or not key_path.is_file():
        raise ValueError('Set RDI_SF_ACCOUNT and use the existing step 12B private key.')
    password = passphrase_file.read_bytes() if passphrase_file else getpass.getpass('Local private key passphrase: ').encode()
    key=ser.load_pem_private_key(key_path.read_bytes(),password=password)
    return snowflake.connector.connect(account=os.environ['RDI_SF_ACCOUNT'],user='RDI_DBT_PILOT_SVC',
        role='RDI_DBT_PILOT_ROLE',warehouse='RDI_PILOT_WH',database='RDI_PILOT_DB',schema='DBT_PILOT',
        private_key=key.private_bytes(ser.Encoding.DER,ser.PrivateFormat.PKCS8,ser.NoEncryption()),
        session_parameters={'QUERY_TAG':'RDI_MONTHLY_SYNC'})


def replicate(cur,sid,rows,verify):
    def read():
        cur.execute(f'SELECT month_start,source_records,reported_sales_dollars,sales_bottles FROM {TABLE} WHERE snapshot_id=%s ORDER BY month_start',(sid,))
        return cur.fetchall()
    if not verify:
        # Snowflake DDL commits independently. Keep it outside the data transaction.
        cur.execute(f'CREATE TABLE IF NOT EXISTS {TABLE} (snapshot_id VARCHAR(36) NOT NULL,month_start DATE NOT NULL,source_records NUMBER(38,0) NOT NULL,reported_sales_dollars NUMBER(38,12),sales_bottles NUMBER(38,0),PRIMARY KEY(snapshot_id,month_start))')
    cur.execute('BEGIN')
    try:
        old=read()
        if old or verify:
            compare(rows,old)
            state='VERIFIED' if verify else 'UNCHANGED'
        else:
            # One atomic insert for this small publication; values are bound, never interpolated.
            params=[v for row in rows for v in (sid,*row)]
            placeholders=','.join(['(%s,%s,%s,%s,%s)']*len(rows))
            cur.execute(f'INSERT INTO {TABLE} ({COLUMNS}) VALUES {placeholders}',tuple(params))
            compare(rows,read())
            state='INSERTED'
        cur.execute('COMMIT')
        return state
    except Exception:
        cur.execute('ROLLBACK')
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('preview','sync','verify'))
    p.add_argument('--snapshot-id',required=True,type=UUID)
    args=p.parse_args();sid=str(args.snapshot_id);rows=load_source(args.snapshot_id)
    summary=dict(snapshot_id=sid,months=len(rows),first_month=rows[0][0].isoformat(),last_month=rows[-1][0].isoformat(),
                 last_month_kpis=dict(zip(('month','records','dollars','bottles'),rows[-1])),
                 source_sha256=hashlib.sha256(json.dumps(rows,default=str).encode()).hexdigest(),table=TABLE)
    if args.action=='preview':state='PREVIEW'
    else:
        conn=connect()
        try:
            with writer_lock(), conn.cursor() as cur:
                state=replicate(cur,sid,rows,args.action=='verify')
        finally: conn.close()
    summary.update(state=state,created_at=datetime.now(timezone.utc).isoformat())
    out=ROOT/'artifacts'/'snowflake'/'monthly_kpis'/sid;out.mkdir(parents=True,exist_ok=True)
    receipt=out/(str(uuid4())+'.json');receipt.write_text(json.dumps(summary,indent=2,default=str),encoding='utf8')
    print(receipt);print(json.dumps(summary,indent=2,default=str))

if __name__=='__main__':main()

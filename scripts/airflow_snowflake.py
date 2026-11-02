"""Mirror the publication produced by this DAG run; never select the latest snapshot."""
import json
import os
from contextlib import closing
from pathlib import Path
from uuid import UUID

from sync_snowflake_kpis import TABLE, connect, normalize, replicate, writer_lock


def run():
    # Return Airflow's skip code before loading cloud dependencies or credentials.
    if os.environ.get('RDI_SF_SYNC_ENABLED', '0') != '1':
        print('Monthly cloud sync disabled.')
        return 99

    import psycopg2
    from airflow_task import run_directory
    from airflow_reporting import save
    from publish_snapshot import settings

    run_id, directory = run_directory()
    pin = json.loads((directory / 'publication.json').read_text())
    if pin['airflow_run_id'] != run_id or pin['state'] not in ('PUBLISHED', 'UNCHANGED'):
        raise ValueError('Unexpected publication receipt for this run.')
    sid = str(UUID(pin['snapshot_id']))
    pub = str(UUID(pin['publication_run_id']))
    with closing(psycopg2.connect(**settings())) as pg:
        pg.set_session(readonly=True, autocommit=True)
        with pg.cursor() as cur:
            # Check the receipt and read immutable rows in one consistent statement.
            cur.execute("""SELECT s.month_count, m.month_start::text, m.source_records,
                           m.reported_sales_dollars::text, m.sales_bottles::text
                FROM publication.runs r JOIN publication.snapshots s ON s.snapshot_id=r.snapshot_id
                JOIN publication.monthly_snapshots m ON m._snapshot_id=s.snapshot_id
                WHERE r.run_id=%s AND r.action='PUBLISH' AND r.state=%s
                  AND s.kind='DBT_VALIDATED' AND s.snapshot_id=%s ORDER BY m.month_start""",
                (pub, pin['state'], sid))
            fields = ('month_count','month_start','source_records','reported_sales_dollars','sales_bottles')
            rows = normalize([dict(zip(fields, row)) for row in cur.fetchall()])

    with writer_lock(), closing(connect(Path('/run/secrets/rdi_key'), Path('/run/secrets/rdi_pass'))) as sf:
        with sf.cursor() as cur:
            state = replicate(cur, sid, rows, False)
            replicate(cur, sid, rows, True)  # Independent read after the write transaction commits.
    receipt = dict(**pin, sync_state=state, verification='VERIFIED', months=len(rows),
                   first_month=str(rows[0][0]), last_month=str(rows[-1][0]), table=TABLE)
    save(directory / 'snowflake.json', receipt)
    print(json.dumps(receipt))
    return 0


if __name__ == '__main__':
    raise SystemExit(run())

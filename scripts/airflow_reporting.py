"""Transfer the committed publisher result and index verified monthly briefs."""
import hashlib
import io
import json
import os
import sys
from contextlib import closing, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

ROOT=Path(__file__).resolve().parents[1]
FILES=('run.json','brief.md','checks.json','response.json','request.json','forecast.json','evidence.json','claim_sources.json')


def save(path,obj):
    tmp=path.with_name(uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(obj,indent=2),encoding='utf8')
    os.replace(tmp,path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publish(run,directory,bundle):
    import publish_snapshot as cli
    # Capture the CLI's final JSON after commit. dbt subprocess logs still go to Airflow.
    buf=io.StringIO();old=sys.argv
    try:
        sys.argv=[old[0],'publish']
        with redirect_stdout(buf):status=cli.main()
    finally:sys.argv=old
    if status!=0: raise RuntimeError("Publication failed; inspect publisher logs.")
    obj=json.loads(buf.getvalue())
    if obj['state'] not in ('PUBLISHED','UNCHANGED'):raise ValueError("Unexpected publication state.")
    pin=dict(airflow_run_id=run,bundle_id=bundle,state=obj['state'],snapshot_id=str(UUID(obj['snapshot_id'])),
             publication_run_id=str(UUID(obj['run_id'])))
    save(directory/'publication.json',pin);print(json.dumps(pin),flush=True)


def verified(entry,key):
    if entry.get('key')!=key:return False
    folder=ROOT/entry['folder']
    return all((folder/n).is_file() and sha(folder/n)==entry.get('hashes',{}).get(n) for n in FILES)


def report(run,directory):
    import psycopg2
    from publish_snapshot import settings
    from monthly_brief import read_month,render
    pin=json.loads((directory/'publication.json').read_text())
    if pin['airflow_run_id']!=run:raise ValueError("Wrong DAG run receipt.")
    model=os.getenv('RDI_REPORT_MODEL','qwen2.5:3b')
    with closing(psycopg2.connect(**settings())) as db:
        db.set_session(readonly=True,autocommit=True)
        with db.cursor() as cur:
            cur.execute("""SELECT max(m.month_start) FROM publication.runs r
                JOIN publication.snapshots s ON s.snapshot_id=r.snapshot_id
                JOIN publication.monthly_snapshots m ON m._snapshot_id=s.snapshot_id
                WHERE r.run_id=%s AND r.action='PUBLISH' AND r.state=%s
                AND s.kind='DBT_VALIDATED' AND s.snapshot_id=%s""",
                (pin['publication_run_id'],pin['state'],pin['snapshot_id']))
            latest=cur.fetchone()[0]
            if not latest:raise ValueError("Publication receipt did not match a validated snapshot.")
            month=latest.strftime('%Y-%m')
            identity=dict(snapshot=pin['snapshot_id'],month=month,engine='ollama',model=model,
                          policy='grounded_narrative_v3_1',code=[sha(ROOT/'scripts'/f) for f in
                          ('monthly_brief.py','narrative_checks.py','statistical_outlook.py')])
            key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
            # Session lock is released when this connection closes, even on a failed draft.
            cur.execute('SELECT pg_advisory_lock(%s)',(int.from_bytes(bytes.fromhex(key[:16]),'big',signed=True),))
        idx=ROOT/'artifacts'/'ai_reporting'/'index'/(key+'.json');idx.parent.mkdir(parents=True,exist_ok=True)
        entry=json.loads(idx.read_text()) if idx.exists() else {}
        if verified(entry,key):
            state='REUSED'
        else:
            row=read_month(month,pin['snapshot_id'],db)
            folder=render(SimpleNamespace(month=month,model=model,engine='ollama'),row)
            audit=json.loads((folder/'run.json').read_text())
            if not audit['all_checks_pass'] or audit['state']!='RENDERED' or audit['snapshot_id']!=pin['snapshot_id']:
                raise ValueError("Report did not pass validation.")
            entry=dict(key=key,identity=identity,folder=folder.relative_to(ROOT).as_posix(),hashes={n:sha(folder/n) for n in FILES})
            save(idx,entry);state='RENDERED'
        result=dict(**pin,report_state=state,month=month,model=model,report_folder=entry['folder'])
        save(directory/'report.json',result);print(json.dumps(result),flush=True)

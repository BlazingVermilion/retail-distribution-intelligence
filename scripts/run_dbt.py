"""Run dbt with warehouse coordination and evidence for full successful builds."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from dotenv import load_dotenv
from warehouse_state import warehouse_connection, has_build_state, source_identity
from publish_snapshot import project_digest

ROOT = Path(__file__).resolve().parents[1]
MUTATING = {'build','run','seed','snapshot','run-operation'}
EXPECTED_MODELS = {'stg_iowa_sales','int_sales_reconciled','fact_sales','dim_store',
                   'dim_product','dim_date','sales_monthly','v_sales_monthly_kpis','bi_sales_monthly'}


def full_build_evidence(target, started):
    manifest = json.loads((target/'manifest.json').read_text(encoding='utf-8'))
    results = json.loads((target/'run_results.json').read_text(encoding='utf-8'))
    metadata = results['metadata']
    if metadata['invocation_id'] != manifest['metadata']['invocation_id']:
        raise ValueError('Build artifacts belong to different invocations.')
    if datetime.fromisoformat(metadata['generated_at'].replace('Z','+00:00')) < started:
        raise ValueError('Build result is stale.')
    model_results = {manifest['nodes'][r['unique_id']]['name']: r['status']
                     for r in results['results'] if r['unique_id'].startswith('model.')}
    if not EXPECTED_MODELS.issubset(model_results) or any(model_results[n] != 'success' for n in EXPECTED_MODELS):
        raise ValueError('A full successful build of all nine models is required.')
    return metadata['invocation_id']


def main():
    load_dotenv(ROOT/'.env',override=False)
    os.environ.setdefault('DBT_PORT',os.getenv('POSTGRES_PORT','5433'))
    os.environ.setdefault('DBT_DATABASE',os.getenv('POSTGRES_DB','retail_analytics'))
    password = os.getenv('DBT_ENV_SECRET_PASSWORD')
    if not password:
        raise ValueError('Set DBT_ENV_SECRET_PASSWORD in .env or the current shell.')
    args = sys.argv[1:]
    if not args or args[0].startswith('-'):
        raise ValueError('Usage: python scripts/run_dbt.py COMMAND [options]; place the command first.')
    command = args[0]
    executable = Path(sys.executable).parent / ('dbt.exe' if os.name=='nt' else 'dbt')
    invocation = [str(executable),*args,'--project-dir',str(ROOT/'dbt'),'--profiles-dir',str(ROOT/'dbt')]
    # Parse/debug/docs serve do not execute warehouse transformations or data tests.
    guarded = command in MUTATING or command=='test' or (command=='docs' and 'generate' in args)
    if not guarded:
        return subprocess.call(invocation,cwd=ROOT)
    settings = dict(host=os.getenv('DBT_HOST','127.0.0.1'),port=int(os.environ['DBT_PORT']),
                    dbname=os.environ['DBT_DATABASE'],user='retail_dbt',password=password,connect_timeout=15)
    with warehouse_connection(settings,shared=command not in MUTATING) as connection:
        with connection.cursor() as cur:
            tracked = has_build_state(cur)
            identity = source_identity(cur) if tracked else None
            if tracked and command in MUTATING:
                cur.execute('UPDATE ops.source_build_state SET valid=FALSE WHERE singleton')
        before = project_digest(ROOT/'dbt')
        started = datetime.now(timezone.utc)
        result = subprocess.call(invocation,cwd=ROOT)
        selectors = ('--select','-s','--models','-m','--exclude','--selector')
        partial = any(a in selectors or any(a.startswith(k+'=') for k in selectors) for a in args)
        if result or not tracked or command!='build' or partial:
            return result
        after = project_digest(ROOT/'dbt')
        if after != before:
            raise ValueError('dbt code changed during the build; source build state remains invalid.')
        # dbt resolves relative target paths against its project directory.
        target_arg = os.getenv('DBT_TARGET_PATH','target')
        for index, arg in enumerate(args):
            if arg=='--target-path': target_arg=args[index+1]
            elif arg.startswith('--target-path='): target_arg=arg.split('=',1)[1]
        target = Path(target_arg)
        if not target.is_absolute(): target=ROOT/'dbt'/target
        build_id = full_build_evidence(target,started)
        from psycopg2.extras import Json
        with connection.cursor() as cur:
            if source_identity(cur) != identity:
                raise ValueError('Registered source changed during build; refusing to certify it.')
            cur.execute('''UPDATE ops.source_build_state SET valid=TRUE,source_identity=%s,
                code_sha256=%s,dbt_invocation_id=%s,completed_at=clock_timestamp() WHERE singleton''',
                (Json(identity),after,build_id))
        print(json.dumps({'state':'BUILD_VALIDATED','dbt_invocation_id':build_id,'source_identity':identity}))
        return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        message=f'{type(exc).__name__}: {exc}'
        secret=os.getenv('DBT_ENV_SECRET_PASSWORD')
        if secret: message=message.replace(secret,'[REDACTED]')
        print(message,file=sys.stderr)
        raise SystemExit(1)

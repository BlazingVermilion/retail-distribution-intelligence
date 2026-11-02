"""Run three contrasting published months and retain every result, including failures."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from uuid import uuid4

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',default='qwen2.5:3b'); args=p.parse_args()
    root=Path(__file__).resolve().parents[1]; rows=[]
    for month,status,lead in [('2025-03','NOT_EVALUABLE','quality'),('2025-11','REVIEW_REQUIRED','quality'),
                              ('2026-09','DISCREPANCIES_PRESENT','yoy')]:
        for engine in ('baseline','ollama'):
            proc=subprocess.run([sys.executable,str(root/'scripts/monthly_brief.py'),'--month',month,
                                 '--engine',engine,'--model',args.model],capture_output=True,text=True,cwd=root)
            folder=Path(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else None
            row=dict(month=month,engine=engine,passed=False)
            if folder and (folder/'run.json').is_file():
                audit=json.loads((folder/'run.json').read_text(encoding='utf8'))
                facts=json.loads((folder/'evidence.json').read_text(encoding='utf8'))
                row.update(audit,path=str(folder),observed_status=facts['status'])
                row['passed']=proc.returncode==0 and audit.get('all_checks_pass') and facts['status']==status and audit.get('lead')==lead
            if proc.returncode: row['error_tail']=proc.stderr[-700:]
            rows.append(row); print(month,engine,'PASS' if row['passed'] else 'FAIL',flush=True)
    out=root/'artifacts/ai_reporting/evaluation'/str(uuid4());out.mkdir(parents=True)
    result=dict(created_at=datetime.now(timezone.utc).isoformat(),runs=rows,
                passed_by_engine={e:sum(bool(r['passed']) for r in rows if r['engine']==e) for e in ('baseline','ollama')})
    (out/'evaluation.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(out/'evaluation.json')
    if not all(r['passed'] for r in rows):sys.exit(1)

if __name__=='__main__':main()

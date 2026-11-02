"""Render a monthly distribution brief from one validated PostgreSQL publication."""
from statistical_outlook import outlook, section
from narrative_checks import contract, checks
import argparse
import os
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import time
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
PROMPT = "Choose the one available evidence ID most useful as the lead of a monthly Iowa distribution brief. Prioritize quality when money is not evaluable or requires review; otherwise prioritize year-over-year performance when available. Return only the requested JSON."


def read_month(month, pinned=None, db=None):
    # Parsing the date before interpolation restricts the only SQL input to an ISO date.
    day = date.fromisoformat(month + "-01")
    sql = f"""SELECT row_to_json(r) FROM (
      SELECT s.snapshot_id, m.month_start,
        (SELECT json_agg(json_build_object('month', h.month_start, 'bottles',
          coalesce(to_jsonb(h)->>'sales_bottles',to_jsonb(h)->>'reported_bottles',to_jsonb(h)->>'reported_sales_bottles')) ORDER BY h.month_start)
         FROM publication.monthly_snapshots h WHERE h._snapshot_id=s.snapshot_id
         AND h.month_start<=m.month_start) AS bottle_history, m.reported_sales_dollars::text AS sales,
        m.active_stores, m.reported_sales_yoy_pct::text AS yoy,
        m.money_reconciliation_status AS status, m.money_check_coverage_pct::text AS coverage,
        m.money_absolute_difference_pct::text AS difference, m.precision_review_period,
        m.period_completeness_status, m.yoy_caveats
      FROM publication.current_snapshot c JOIN publication.snapshots s USING(snapshot_id)
      JOIN publication.monthly_snapshots m ON m._snapshot_id=s.snapshot_id
      WHERE c.singleton AND s.kind='DBT_VALIDATED' AND m.month_start=DATE '{day.isoformat()}') r"""
    if pinned is not None:
        # Never resolve the mutable current pointer when processing a publication receipt.
        sql=sql.replace("publication.current_snapshot c JOIN publication.snapshots s USING(snapshot_id)",
                        "publication.snapshots s").replace("c.singleton","s.snapshot_id=%s")
        with db.cursor() as cur:
            cur.execute(sql,(pinned,))
            row=cur.fetchone()
        if row is None: raise ValueError("Pinned validated snapshot or month missing.")
        return row[0]
    proc = subprocess.run(["docker","compose","exec","-T","postgres","psql","-X","-qAt",
                           "-v","ON_ERROR_STOP=1","-U","postgres","-d","retail_analytics","-c",sql],
                          check=True,capture_output=True,text=True,cwd=ROOT)
    if not proc.stdout.strip():
        raise ValueError("Month missing or current snapshot is not dbt-validated.")
    return json.loads(proc.stdout)


def facts(r):
    out = {"quality": "Monetary reconciliation status: " + r["status"] + "."}
    if r["sales"] is not None:
        out["sales"] = f"Source-reported distribution sales totaled ${Decimal(r['sales']):,.2f}."
    if r["active_stores"] is not None:
        out["stores"] = f"{r['active_stores']:,} distinct stores had activity this month."
    if r["yoy"] is not None:
        out["yoy"] = f"Reported sales changed by {Decimal(r['yoy']):+.2f}% versus the same calendar month last year."
    if r["coverage"] is not None:
        out["quality"] += f" The money check covered {Decimal(r['coverage']):.2f}% of records."
    if r["difference"] is not None:
        out["quality"] += f" Absolute differences were {Decimal(r['difference']):.4f}% of absolute reported value on evaluable records."
    else:
        out["quality"] += " The absolute difference rate is unavailable."
    return out


def expected_lead(r, evidence):
    if r["status"] in ("NOT_EVALUABLE", "REVIEW_REQUIRED"):
        return "quality"
    return "yoy" if "yoy" in evidence else next(iter(evidence))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--month", required=True, help="YYYY-MM")
    p.add_argument("--engine", choices=("baseline","ollama"), default="baseline")
    p.add_argument("--model", default="qwen2.5:3b")
    args = p.parse_args()
    r = read_month(args.month)
    return render(args,r)


def render(args,r):
    forecast = outlook(r["bottle_history"])
    evidence = facts(r)
    target = expected_lead(r,evidence)
    run = ROOT/"artifacts"/"ai_reporting"/args.month/str(uuid4())
    run.mkdir(parents=True)
    def save(name, obj):
        (run/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding="utf-8")
    save("evidence.json",r)
    save("forecast.json",forecast)
    audit = dict(engine=args.engine, snapshot_id=r["snapshot_id"], policy="grounded_narrative_v3_1",
                 expected_lead=target, model=None, direct_api_charge_usd=0)
    references = contract(r,evidence,forecast,target)
    save("claim_sources.json",references)
    draft = dict(references)
    writable = {k:v for k,v in references.items() if k != "quality"}
    audit["source_rendered_fields"] = ["quality"]
    audit.update(report_id=run.name, airflow_run_id=os.getenv("RDI_RUN_ID"))
    lead = target
    started = time.monotonic()
    try:
        if args.engine == "ollama":
            audit["model"] = args.model
            schema = dict(type="object",properties={k:{"type":"string"} for k in writable},
                          required=list(writable),additionalProperties=False)
            instruction = ("Write a concise English executive summary, one short passage per supplied evidence key. "
                           "Paraphrase for a distribution manager. Keep every number, sign, currency, percent, "
                           "method name and status literal exactly, within its original field. "
                           "Keep unavailable values explicitly unavailable. Place each forecast method before its value. "
                           "Do not add figures, causes, recommendations or comparisons not given. "
                           "Return the JSON object; Python controls which passage leads.")
            payload = dict(model=args.model, stream=False, format=schema, options={"temperature":0},
                           messages=[{"role":"system","content":instruction},
                                     {"role":"user","content":json.dumps(writable)}])
            save("request.json",payload)
            req = Request(os.environ.get("RDI_OLLAMA_URL","http://127.0.0.1:11434").rstrip("/")+"/api/chat",data=json.dumps(payload).encode(),
                          headers={"Content-Type":"application/json"})
            with urlopen(req,timeout=180) as response:
                reply = json.load(response)
            save("response.json",reply)
            audit.update(input_tokens=reply.get("prompt_eval_count"),output_tokens=reply.get("eval_count"))
            authored = json.loads(reply["message"]["content"])
            # Reject unexpected fields; never publish model-authored reconciliation claims.
            if not isinstance(authored, dict) or set(authored) != set(writable):
                raise ValueError("Unexpected model-authored fields; see response.json.")
            draft.update(authored)
        validation = checks(references,draft)
        save("checks.json",validation)
        audit.update(lead=lead, lead_matches_policy=True, checks_passed=sum(validation.values()),
                     checks_total=len(validation), all_checks_pass=all(validation.values()))
        if not all(validation.values()):
            raise ValueError("Narrative rejected; inspect checks.json and response.json. No brief was rendered.")
        # Fixed references, priority and caveats are independent of model wording.
        lines = [f"# Iowa distribution brief | {args.month}", "", "## Executive summary", ""]
        lines.extend(f"{draft[k]} [{k}]" for k in references)
        lines.extend(["","## Reported indicators",""])
        lines.extend("- "+v for v in evidence.values())
        lines.extend(["", "Period completeness: "+str(r["period_completeness_status"])+".",
                      "Precision review period: "+str(r["precision_review_period"])+".",
                      "YoY caveats: "+("; ".join(r["yoy_caveats"]) if isinstance(r["yoy_caveats"],list) else str(r["yoy_caveats"] or "None recorded"))+".",
                      "", "Published snapshot: "+r["snapshot_id"]])
        lines.extend(["", *section(forecast)])
        lines.extend(["", f"Engine: {args.engine} | Model: {audit['model'] or 'template'} | Report ID: {run.name}",
                      f"Airflow origin: {audit['airflow_run_id'] or 'standalone'}"])
        (run/"brief.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
        audit["state"]="RENDERED"
    except Exception as exc:
        audit.update(state="FAILED", error=str(exc))
        raise
    finally:
        audit["seconds"]=round(time.monotonic()-started,3)
        save("run.json",audit)
        print(run)
    return run


if __name__ == "__main__":
    main()

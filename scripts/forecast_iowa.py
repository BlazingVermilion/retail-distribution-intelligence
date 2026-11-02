"""Versioned Iowa forecasting experiment. Run from Windows with Python 3.12."""
import argparse
import calendar
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import subprocess
import tempfile
import warnings
from importlib.metadata import version

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tools.sm_exceptions import ConvergenceWarning

ROOT = Path(__file__).resolve().parents[1]
SPECS = ("seasonal_naive", "last_month", "ets_level", "ets_damped", "ridge_0.1", "ridge_1", "ridge_10")
FIELDS = ["snapshot_id","month_start","bottles","source_records","completeness"]
REF_ACTUAL = (2163052,2192141,2414717,2483580,2576531,2582939,2593396,2461391,2558986)
REF_SEASON = (2309799,2206814,2416496,2595432,2571012,2642511,2542822,2550030,2550832)
SQL = """COPY (SELECT s.snapshot_id, m.month_start, m.sales_bottles AS bottles,
m.source_records, m.period_completeness_status AS completeness
FROM publication.current_snapshot c JOIN publication.snapshots s USING(snapshot_id)
JOIN publication.monthly_snapshots m ON m._snapshot_id=s.snapshot_id
WHERE c.singleton AND s.kind='DBT_VALIDATED' AND m.month_start >= DATE '2020-01-01'
ORDER BY m.month_start) TO STDOUT WITH (FORMAT CSV, HEADER TRUE)"""


def month(i):
    return date(2020+i//12, i%12+1, 1)


def load_series(blob):
    reader = csv.DictReader(io.StringIO(blob.decode("utf-8-sig")))
    if reader.fieldnames != FIELDS:
        raise ValueError(f"Expected these input columns in order: {FIELDS}")
    rows = list(reader)
    if len(rows)<81 or len({r["snapshot_id"] for r in rows})!=1 or not rows[0]["snapshot_id"]:
        raise ValueError("Need one identified snapshot spanning Jan 2020 through at least Sep 2026.")
    for i,r in enumerate(rows):
        if r["month_start"] != month(i).isoformat() or not r["bottles"] or int(r["source_records"])<=0:
            raise ValueError(f"Missing, duplicated or invalid monthly observation at {month(i)}.")
        int(r["bottles"])
        if not r["completeness"]:
            raise ValueError("Missing completeness status: do not assume complete.")
    return rows


def features(y,i):
    # i is the first unknown month: no observed value from i or later is permitted.
    d=month(i)
    weekdays=sum(date(d.year,d.month,k).weekday()<5 for k in range(1,calendar.monthrange(d.year,d.month)[1]+1))
    return [y[i-k] for k in (1,2,3,12)] + [np.mean(y[i-3:i]),math.sin(2*math.pi*d.month/12),
                                               math.cos(2*math.pi*d.month/12),weekdays]


def predict(spec, history, horizon=1):
    y=list(map(float,history))
    if spec.startswith("ets"):
        # Scale levels for optimizer conditioning; return results in original bottles.
        scale=max(1.,float(np.mean(np.abs(y))))
        damp=spec=="ets_damped"
        with warnings.catch_warnings():
            warnings.simplefilter("error",ConvergenceWarning)
            fit=ExponentialSmoothing(np.array(y)/scale,trend="add" if damp else None,damped_trend=damp,
                                     seasonal="add",seasonal_periods=12,initialization_method="estimated").fit()
        out=np.asarray(fit.forecast(horizon))*scale
    else:
        if spec.startswith("ridge_"):
            model=make_pipeline(StandardScaler(),Ridge(alpha=float(spec.split("_")[1])))
            model.fit([features(y,i) for i in range(12,len(y))],y[12:])
        for _ in range(horizon):
            if spec=="seasonal_naive": p=y[-12]
            elif spec=="last_month": p=y[-1]
            else: p=float(model.predict([features(y,len(y))])[0])
            y.append(p)
        out=y[-horizon:]
    if not np.all(np.isfinite(out)): raise ValueError("Nonfinite forecast: "+spec)
    return list(map(float,out))


def metrics(pred,actual):
    e=np.asarray(pred)-np.asarray(actual)
    den=sum(abs(v) for v in actual)
    return dict(n=len(e),mae=float(np.mean(abs(e))),wape_pct=float(100*sum(abs(e))/den) if den else None,
                bias=float(np.mean(e)),rmse=float(np.sqrt(np.mean(e**2))))


def choose(scores):
    base=scores["seasonal_naive"]
    eligible=[s for s in SPECS if s in scores and s!="seasonal_naive" and base["mae"]>0 and
              scores[s]["mae"]<=0.95*base["mae"] and abs(scores[s]["bias"])<=abs(base["bias"])]
    return min(eligible,key=lambda s:scores[s]["mae"]) if eligible else "seasonal_naive"


def write_csv(path,rows):
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def experiment(rows,out,reference_required=True):
    y=[int(r["bottles"]) for r in rows]
    match=tuple(y[60:69])==REF_SEASON and tuple(y[72:81])==REF_ACTUAL
    if reference_required and not match:
        raise ValueError("The published 2025/2026 slice differs from the reference. Inspect series.csv; pass --accept-revision only after review.")
    val={}; rejected={}; trace=[]; errs={}; summary=[]
    def score(spec,phase,pred,actual):
        result=metrics(pred,actual)
        summary.append(dict(phase=phase,model=spec,**result))
        return result
    def record(spec,i,p,phase,origin,h,prior):
        # Calibration excludes the current target. No h=1 errors are recycled for h>1.
        width=float(np.quantile(prior,.8,method="higher")) if len(prior)>=24 else None
        a=y[i] if i<len(y) else None
        trace.append(dict(phase=phase,model=spec,origin_through=month(origin).isoformat(),target=month(i).isoformat(),
                          h=h,forecast=p,actual=a,error=p-a if a is not None else None,
                          lower80=p-width if width is not None else None,upper80=p+width if width is not None else None,
                          completeness=rows[i]["completeness"] if a is not None else "UNKNOWN"))
    for s in SPECS:
        try: ps=[predict(s,y[:i])[0] for i in range(36,72)]
        except (ConvergenceWarning,ValueError,ArithmeticError) as exc:
            rejected[s]=str(exc); continue  # Reject the whole specification, never cherry-pick easy folds.
        val[s]=score(s,"validation_2023_25",ps,y[36:72]); errs[s]=[]
        for k,year in enumerate((2023,2024,2025)):
            score(s,f"validation_{year}",ps[k*12:k*12+12],y[36+k*12:48+k*12])
        for i,p in enumerate(ps,36):
            record(s,i,p,"validation",i-1,1,errs[s]); errs[s].append(abs(p-y[i]))
    selected=choose(val)  # Freeze the model specification before accessing test scores.
    for s in val:
        ps=[]
        for i in range(72,81):
            p=predict(s,y[:i])[0]; ps.append(p)
            record(s,i,p,"rolling_test",i-1,1,errs[s]); errs[s].append(abs(p-y[i]))
        score(s,"rolling_test_2026_01_09",ps,y[72:81])
    for s in dict.fromkeys(("seasonal_naive",selected)):
        for h,p in enumerate(predict(s,y[:72],12),1):
            record(s,71+h,p,"fixed_dec_2025",71,h,[])
    # Use any additional closed months only after the frozen nine-month evaluation.
    n=len(y)
    for i in range(81,n):
        p=predict(selected,y[:i])[0]; errs[selected].append(abs(p-y[i]))
    record(selected,n,predict(selected,y)[0],"next_after_data",n-1,1,errs[selected])
    tested=[r for r in trace if r["phase"]=="rolling_test" and r["model"]==selected]
    cov=sum(r["lower80"]<=r["actual"]<=r["upper80"] for r in tested)/len(tested)
    sres=next(r for r in summary if r["phase"].startswith("rolling_test") and r["model"]==selected)
    bref=metrics(y[60:69],y[72:81])
    report=dict(snapshot_id=rows[0]["snapshot_id"],chosen=selected,reference_matches=match,
                baseline=bref,test=sres,skill_vs_seasonal=1-sres["mae"]/bref["mae"] if bref["mae"] else None,
                coverage80=cov,mean_width80=float(np.mean([r["upper80"]-r["lower80"] for r in tested])),
                rejected_in_validation=rejected,next_forecast=trace[-1],
                test_completeness_labels=sorted({r["completeness"] for r in rows[72:81]}),
                note="Retrospective, latest available vintage; completeness is not independently certified here.")
    write_csv(out/"predictions.csv",trace); write_csv(out/"metrics.csv",summary)
    (out/"result.json").write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    (out/"forecast_brief.md").write_text(
        f"# Iowa distribution forecast | {month(n):%Y-%m}\n\nSelected on 2023–2025 validation: {selected}. "
        f"On the nine 2026 retrospective targets, MAE was {sres['mae']:,.0f} bottles/month, "
        f"compared with {bref['mae']:,.0f} for seasonal naive. Average signed error was {sres['bias']:+,.0f} bottles. "
        f"The nominal 80% interval covered {round(cov*9)}/9 observations.\n\n"
        f"Next month after the data: {trace[-1]['forecast']:,.0f} net bottles "
        f"(empirical 80% interval {trace[-1]['lower80']:,.0f} to {trace[-1]['upper80']:,.0f}). "
        f"This is a scenario, not a live issued forecast. Source completeness remains subject to review.\n\n"
        f"Snapshot: {rows[0]['snapshot_id']}\n", encoding="utf-8")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,help="Replay a previously exported series.csv instead of querying PostgreSQL.")
    parser.add_argument("--accept-revision",action="store_true")
    args=parser.parse_args()
    blob=args.input.read_bytes() if args.input else subprocess.run(
        ["docker","compose","exec","-T","postgres","psql","-X","-qAt","-v","ON_ERROR_STOP=1","-U","postgres","-d","retail_analytics","-c",SQL],
        cwd=ROOT,stdout=subprocess.PIPE,check=True).stdout
    rows=load_series(blob)
    now=datetime.now(timezone.utc)
    # Exclude the open calendar month and any future rows before fitting or scoring.
    rows=[r for r in rows if date.fromisoformat(r["month_start"])<now.date().replace(day=1)]
    if len(rows)<81: raise ValueError("The nine September YTD evaluation targets must be closed.")
    folder=ROOT/"artifacts"/"forecasting"; folder.mkdir(parents=True,exist_ok=True)
    out=Path(tempfile.mkdtemp(prefix=now.strftime("%Y%m%dT%H%M%SZ-"),dir=folder))
    (out/"series.csv").write_bytes(blob); print("Output:",out,flush=True)
    manifest=dict(created_at=now.isoformat(),snapshot_id=rows[0]["snapshot_id"],sha256=hashlib.sha256(blob).hexdigest(),
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),python=platform.python_version(),
                  dependencies={k:version(k) for k in ("numpy","scipy","pandas","statsmodels","scikit-learn")},
                  latest_used=rows[-1]["month_start"],n_used=len(rows),state="RUNNING")
    try:
        result=experiment(rows,out,not args.accept_revision)
        manifest["state"]="COMPLETED"; print(json.dumps(result,indent=2))
    except Exception as exc:
        manifest.update(state="FAILED",error=str(exc)); raise
    finally:
        (out/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")


if __name__=="__main__": main()

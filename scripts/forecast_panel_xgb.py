"""One-month-ahead experiments on reported net bottles. No production writes."""
import argparse
import calendar
import csv
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import xgboost as xgb

# Fixed before validation. Zero correction starts the learner at the seasonal baseline.
PARAMS = dict(objective="reg:squarederror", max_depth=2, eta=0.04, min_child_weight=12,
              reg_lambda=5, base_score=0.0, tree_method="hist", nthread=1, seed=17)
ROUNDS = 80


def read_panel(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    months = sorted({r["month"] for r in rows})
    dates = [date.fromisoformat(m) for m in months]
    serial = [d.year * 12 + d.month for d in dates]
    if not dates or months[0] != "2020-01-01" or any(b-a != 1 for a,b in zip(serial,serial[1:])):
        raise ValueError("Expected consecutive calendar months beginning January 2020.")
    if "2025-12-01" not in months:
        raise ValueError("The validation period must be complete.")
    totals, ranking, seen = {}, {}, set()
    for r in rows:
        m,g = r["month"],r["category"]
        if not g or (m,g) in seen or not r["control_bottles"] or not r["control_records"]:
            raise ValueError(f"Missing control, missing category, or duplicate group: {m}, {g}")
        seen.add((m,g))
        n,y = int(r["records"]),int(r["bottles"] or 0)
        if n != int(r["observed"]):
            raise ValueError(f"Missing bottle counts: {m}, {g}. Review before forecasting.")
        a,b = totals.get(m,(0,0))
        totals[m] = a+n,b+y
        if m < "2023":
            ranking[g] = ranking.get(g,0)+abs(y)
    for r in rows:
        if totals[r["month"]] != (int(r["control_records"]),int(r["control_bottles"])):
            raise ValueError("Monthly reconciliation failed: "+r["month"])
    # Freeze the group dictionary before the first validation origin. New codes go to OTHER.
    groups = sorted(ranking,key=lambda g:(-ranking[g],g))[:12]+["OTHER"]
    Y = np.zeros((len(months),len(groups)))
    for r in rows:
        g = r["category"]
        Y[months.index(r["month"]),groups.index(g) if g in groups else -1] += int(r["bottles"])
    return dates,groups,Y


def weekdays(d):
    return np.bincount([date(d.year,d.month,i).weekday() for i in
                        range(1,calendar.monthrange(d.year,d.month)[1]+1)],minlength=7)


def design(Y, dates, t):
    # Only dates and bottle counts released before target month t enter predictors.
    scale = np.maximum(1,np.abs(Y[t-12:t]).mean(axis=0))
    changes = (Y[t-3:t]-Y[t-15:t-12])/scale
    calendar_delta = weekdays(dates[t])-weekdays(dates[t-12])
    X = np.column_stack([changes.T, np.tile(calendar_delta,(Y.shape[1],1))])
    return X,scale


def training_data(Y, dates, t):
    xs,ys = [],[]
    for i in range(15,t):
        x,s = design(Y,dates,i)
        xs.append(x); ys.append((Y[i]-Y[i-12])/s)
    return np.vstack(xs),np.concatenate(ys)


def tree_predict(Y, dates, t):
    # Use the same supervised rows and target scaling as panel Ridge.
    X, y = training_data(Y, dates, t)
    booster = xgb.train(PARAMS, xgb.DMatrix(X, label=y, nthread=1), num_boost_round=ROUNDS)
    x, scale = design(Y, dates, t)
    correction = booster.predict(xgb.DMatrix(x, nthread=1))
    return Y[t-12] + scale * correction, booster


def predict(Y, dates, t):
    X,y = training_data(Y, dates, t)
    # Fit scaling and ridge only on this origin's history. Share coefficients across groups.
    center,spread = X.mean(0),X.std(0)
    spread[spread < 1e-8] = 1
    Z = (X-center)/spread
    weights = np.linalg.solve(Z.T@Z+len(y)*0.2*np.eye(Z.shape[1]),Z.T@(y-y.mean()))
    x,s = design(Y,dates,t)
    return Y[t-12]+s*(y.mean()+((x-center)/spread)@weights)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input",type=Path)
    parser.add_argument("--out",type=Path,default=Path("artifacts/forecast_panel_xgb"))
    args=parser.parse_args()
    dates,groups,Y = read_panel(args.input)
    args.out.mkdir(parents=True,exist_ok=True)
    rows=[]; details=[]
    for t in range(36,len(dates)):
        state=Y.sum(axis=1,keepdims=True)
        pred=predict(Y,dates,t)
        tree,_ = tree_predict(Y,dates,t)
        for name,fc in [("seasonal_naive",state[t-12,0]),("state_residual",predict(state,dates,t)[0]),("panel_residual",pred.sum()),("panel_xgboost",tree.sum())]:
            rows.append((dates[t].isoformat(),name,float(state[t,0]),float(fc)))
        details.extend((dates[t].isoformat(),g,Y[t,j],Y[t-12,j],pred[j],tree[j]) for j,g in enumerate(groups))
    def write(name,header,data):
        with (args.out/name).open("w",newline="",encoding="utf8") as f:
            w=csv.writer(f);w.writerow(header);w.writerows(data)
    write("predictions.csv",["month","model","actual","forecast"],rows)
    write("category_errors.csv",["month","category","actual","seasonal_naive","panel_residual","panel_xgboost"],details)
    metrics={}
    for period in ["validation_2023_25"]+sorted({r[0][:4] for r in rows}):
        metrics[period]={}
        for name in ("seasonal_naive","state_residual","panel_residual","panel_xgboost"):
            a,p=np.array([(a,p) for m,n,a,p in rows if n==name and
                          (m[:4]==period or (period.startswith("validation") and m[:4]<"2026"))]).T
            err=p-a
            metrics[period][name]=dict(months=len(a),mae=float(abs(err).mean()),bias=float(err.mean()),
                                       wape_pct=float(100*abs(err).sum()/abs(a).sum()))
    v=metrics["validation_2023_25"]; b=v["seasonal_naive"]
    passed=[n for n in ("state_residual","panel_residual","panel_xgboost") if v[n]["mae"]<=0.95*b["mae"] and abs(v[n]["bias"])<=abs(b["bias"])]
    # Refit on observed history only. Keep this challenger forecast separate from publication.
    last=dates[-1]
    next_date=date(last.year + (last.month==12),last.month%12+1,1)
    forward,booster=tree_predict(Y,dates+[next_date],len(dates))
    booster.save_model(args.out/"panel_xgboost.json")
    result=dict(next_month=next_date.isoformat(), trained_through=last.isoformat(),
                next_xgboost_bottles=float(forward.sum()),next_baseline_bottles=float(Y[-12].sum()),
                xgboost_version=xgb.__version__,parameters=PARAMS,boosting_rounds=ROUNDS,target="reported net bottles",horizon_months=1,input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
                groups=groups,metrics=metrics,validation_candidate=min(passed,key=lambda n:v[n]["mae"]) if passed else "seasonal_naive",
                status="research only; latest-vintage retrospective; completeness unverified")
    (args.out/"result.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()

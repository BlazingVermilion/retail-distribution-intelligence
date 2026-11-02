"""One-month-ahead net bottle forecasts. All cutoffs are exclusive."""
import argparse
import csv
import hashlib
import json
import sys
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

SEED, EPOCHS, WINDOW = 23, 4, 8


def add_month(d, n=1):
    k = d.year * 12 + d.month - 1 + n
    return date(k // 12, k % 12 + 1, 1)


def load(path):
    cells, checks, stores = {}, {}, set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            m, w = (date.fromisoformat(r[k]) for k in ('month','week'))
            s = r['store']
            key = (m,w,s)
            if (not s or key in cells or w.weekday() or m.day != 1 or
                    w >= add_month(m) or w+timedelta(days=6)<m):
                raise ValueError(f"Invalid store/week/month key: {key}")
            n,y = int(r['records']),int(r['bottles'])
            if not n or n != int(r['observed']):
                raise ValueError(f"Incomplete bottle data: {key}")
            c=(int(r['control_records']),int(r['control_bottles']))
            if m in checks and checks[m][2]!=c:
                raise ValueError(f"Inconsistent control: {m}")
            a,b,_=checks.get(m,(0,0,c)); checks[m]=(a+n,b+y,c)
            cells[key]=y; stores.add(s)
    dates=sorted(checks)
    if not dates or dates[0]!=date(2020,1,1) or dates[-1]<date(2025,12,1):
        raise ValueError("Expected January 2020 through at least December 2025.")
    stores=sorted(stores); ix={s:i for i,s in enumerate(stores)}
    mi={m:i for i,m in enumerate(dates)}
    monthly=np.zeros((len(dates),len(stores)),np.int64)
    first=np.full(len(stores),len(dates)); weeks={}
    for i,m in enumerate(dates):
        a,b,c=checks[m]
        if (a,b)!=c or m!=add_month(dates[0],i):
            raise ValueError(f"Monthly source reconciliation failed: {m}")
    for (m,w,s),y in cells.items():
        i,j=mi[m],ix[s]; monthly[i,j]+=y;first[j]=min(first[j],i)
        if (i,w) not in weeks: weeks[i,w]=np.zeros(len(stores),np.int64)
        weeks[i,w][j]=y
    return dates,stores,monthly,first,weeks


def examples(data):
    dates,stores,Y,first,weeks=data
    samples={}
    for t in range(12,len(dates)+1):
        m=add_month(dates[0],t); known=first<t
        anchor=Y[t-12,known].astype(float)
        scale=np.maximum(30,np.abs(Y[t-12:t,known]).mean(0))
        # Model store openings collectively; future store identifiers are never input features.
        entrants=np.mean([Y[k,first==k].sum() for k in range(t-3,t)])
        end=m-timedelta(days=1); monday=end-timedelta(days=end.weekday())
        inputs=[]
        for j in reversed(range(WINDOW)):
            w=monday-timedelta(weeks=j)
            # A partial week can straddle two months. Never read the target-month slice.
            bottles=sum((weeks[k,w][known] for k in range(t-3,t) if (k,w) in weeks),
                        np.zeros(known.sum()))
            inputs.append(np.stack([bottles/scale,
                np.full(len(scale),min(7,(m-w).days)/7),
                anchor/scale,np.full(len(scale),monthrange(m.year,m.month)[1]/31)]))
        x=np.stack(inputs,axis=-1).transpose(1,0,2).copy()
        observed=t<len(dates)
        def tensor(a): return torch.as_tensor(a,dtype=torch.float32)
        samples[t]=SimpleNamespace(x=tensor(x),scale=tensor(scale),base=anchor,
            cold=float(entrants),actual=Y[t,known] if observed else None,
            total=int(Y[t].sum()) if observed else None,
            y=tensor((Y[t,known]-anchor)/scale) if observed else None,
            state_scale=max(1.,scale.sum()),month=m,ids=np.asarray(stores)[known])
    return samples


class TCN(nn.Module):
    """Causal convolutions: the final state covers all eight weekly inputs."""
    def __init__(self):
        super().__init__()
        self.layers=nn.ModuleList([nn.Conv1d(a,8,2,dilation=d)
                                   for a,d in [(4,1),(8,2),(8,4)]])
        self.head=nn.Linear(8,1)
        nn.init.zeros_(self.head.weight);nn.init.zeros_(self.head.bias)

    def forward(self,x):
        for layer in self.layers:
            x=F.relu(layer(F.pad(x,(layer.dilation[0],0))))
        return self.head(x[:,:,-1]).flatten()


def fit(history):
    # Same normalized store residuals and statewide squared-error term for both learners.
    # Ridge statistics accumulate in float64; each training month gets equal weight.
    torch.manual_seed(SEED); model=TCN()
    opt=torch.optim.Adam(model.parameters(),lr=0.003)
    stats=[]
    for e in history:
        x=e.x.flatten(1).numpy().astype(float)
        x=np.column_stack((x,np.ones(len(x)))); y=e.y.numpy()
        agg=e.scale.numpy()@x/e.state_scale
        target=(e.total-e.cold-e.base.sum())/e.state_scale
        stats.append((x.T@x/len(x)+np.outer(agg,agg),x.T@y/len(x)+agg*target))
    gram,rhs=(np.mean([a for a,b in stats],0),np.mean([b for a,b in stats],0))
    penalty=np.eye(len(rhs))*0.02;penalty[-1,-1]=1e-8
    ridge=np.linalg.solve(gram+penalty,rhs)
    rng=np.random.default_rng(SEED)
    for _ in range(EPOCHS):
        for i in rng.permutation(len(history)):
            e=history[i]; pred=model(e.x)
            state=(torch.dot(pred,e.scale)+(e.base.sum()+e.cold-e.total))/e.state_scale
            loss=F.mse_loss(pred,e.y)+state.square()
            opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),2.)
            opt.step()
    return model.eval(),ridge


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path);p.add_argument('--out',type=Path,default=Path('artifacts/store_tcn/run'))
    args=p.parse_args(); torch.set_num_threads(2); data=load(args.input); ex=examples(data)
    out=args.out;out.mkdir(parents=True,exist_ok=False)
    rows=[]; future={}
    names=['seasonal_naive','store_ridge','store_tcn']
    with (out/'predictions.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['month','model','forecast','actual','known_store_mae','new_store_forecast'])
        for t in range(36,len(data[0])+1):
            e=ex[t]; print(f"Training through {add_month(e.month,-1)} for {e.month}",flush=True)
            net,ridge=fit([ex[k] for k in range(12,t)])
            with torch.no_grad(): dl=net(e.x).numpy()
            lin=e.x.flatten(1).numpy()@ridge[:-1]+ridge[-1]
            for name,delta,cold in zip(names,[0,lin,dl],[0,e.cold,e.cold]):
                group=e.base+delta*e.scale.numpy(); pred=float(group.sum()+cold)
                store_mae=float(np.abs(group-e.actual).mean()) if e.actual is not None else None
                writer.writerow((e.month,name,pred,e.total,store_mae,cold))
                if e.total is None: future[name]=pred
                else: rows.append((e.month.year,name,e.total,pred))
            f.flush()
    metrics={}
    for period in ['validation']+sorted({r[0] for r in rows}):
        metrics[str(period)]={}
        for name in names:
            actual,pred=np.array([(a,p) for year,n,a,p in rows if n==name and
                                 (year==period or (period=='validation' and year<=2025))]).T
            err=pred-actual
            metrics[str(period)][name]=dict(months=len(err),mae=float(np.abs(err).mean()),
                bias=float(err.mean()),wape_pct=float(100*np.abs(err).sum()/np.abs(actual).sum()))
    v=metrics['validation'];base=v[names[0]]
    eligible=[n for n in names[1:] if v[n]['mae']<=.95*base['mae'] and abs(v[n]['bias'])<=abs(base['bias'])]
    torch.save(net.state_dict(),out/'tcn_weights.pt'); np.save(out/'ridge.npy',ridge)
    sha=hashlib.sha256()
    with args.input.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''): sha.update(block)
    digest=sha.hexdigest()
    result=dict(metrics=metrics,validation_candidate=min(eligible,key=lambda n:v[n]['mae']) if eligible else names[0],
                next_month=str(e.month),next_forecasts=future,input_sha256=digest,torch=str(torch.__version__),
                seed=SEED,epochs=EPOCHS,status="Retrospective; source completeness and original release times unverified.")
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()

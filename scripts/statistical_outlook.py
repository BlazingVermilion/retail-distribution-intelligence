"""Statewide forecasts; all numbers are reported net bottles, not retail sell-through."""
from datetime import date
import numpy as np
from scipy.optimize import least_squares

def shift(d, n):
    i = d.year * 12 + d.month - 1 + n
    return date(i // 12, i % 12 + 1, 1)


def ets(y):
    # Additive Holt-Winters with a damped trend, initialized from the first two cycles.
    scale = y[:24].mean()
    z = y/scale
    def simulate(p, forecast=False):
        alpha,beta,gamma,phi=p
        l=z[12:24].mean(); trend=(l-z[:12].mean())/12
        season=(z[:12]-z[:12].mean()+z[12:24]-l)/2
        errors=[]
        for t in range(24,len(z)):
            k=t%12; prior=l+phi*trend
            err=z[t]-prior-season[k]; errors.append(err)
            l=prior+alpha*err; trend=phi*trend+alpha*beta*err
            season[k]+=gamma*(1-alpha)*err
        if not forecast: return errors
        return scale*(l+trend*np.cumsum(phi**np.arange(1,13))+season[(len(z)+np.arange(12))%12])
    params=least_squares(simulate,[.3,.1,.2,.9],bounds=([.001,0,0,.8],[.999,1,1,.995])).x
    return simulate(params,True)


def outlook(history):
    dates=[date.fromisoformat(r['month']) for r in history]
    y=np.array([float(r['bottles']) for r in history])
    if len(y)<36 or not np.isfinite(y).all() or any(d!=shift(dates[0],i) for i,d in enumerate(dates)):
        raise ValueError("Expected at least 36 consecutive months with finite bottle totals.")
    def path(series,origin):
        return [dict(target=str(shift(origin,h)),seasonal_naive=float(b),holt_winters=float(c))
                for h,(b,c) in enumerate(zip(series[-12:],ets(series)),1)]
    last=dates[-1]; forward=path(y,last)
    # A calendar-year plan uses only the prior December vintage cutoff.
    # Historical values may still have been revised in the current snapshot.
    yr=forward[0]['target'][:4]; cutoff=date(int(yr)-1,12,1)
    i=dates.index(cutoff)+1 if cutoff in dates else 0
    annual=path(y[:i],cutoff) if i>=36 else []
    return dict(origin=str(last),next_month=forward[0],rolling_path=forward,
                annual_year=yr,annual_cutoff=str(cutoff),
                annual_totals={k:sum(r[k] for r in annual) for k in ('seasonal_naive','holt_winters')} if annual else None,
                reconstructed=True,unit='reported net bottles')


def section(o):
    m=o['next_month']
    lines=['## Statewide distribution outlook','',
           f"For {m['target'][:7]}, the primary plan is {m['seasonal_naive']:,.0f} net bottles (seasonal naive). "
           f"The Holt-Winters comparison is {m['holt_winters']:,.0f}.",
           '', 'The difference is a model comparison, not a prediction interval.']
    a=o['annual_totals']
    if a:
        lines+=['',f"Calendar {o['annual_year']} plan reconstructed through {o['annual_cutoff'][:7]}: "
                f"{a['seasonal_naive']:,.0f} bottles (primary); {a['holt_winters']:,.0f} (comparison)."]
    return lines+['','These are forecasts from the current data vintage. Period completeness and original release dates are unverified.']

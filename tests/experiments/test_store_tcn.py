"""Guard the temporal cutoff and run the actual training code on synthetic transactions."""
import csv
from datetime import date,timedelta
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import store_tcn as mod


def fixture(path):
    with path.open('w',newline='') as f:
        w=csv.writer(f);w.writerow('month week store records observed bottles control_records control_bottles'.split())
        for t in range(81):
            m=mod.add_month(date(2020,1,1),t);d=m; cells={}
            while d<mod.add_month(m):
                monday=d-timedelta(days=d.weekday())
                for s in range(3+(t>=39)):
                    k=(monday,s);n,y=cells.get(k,(0,0))
                    cells[k]=(n+1,y+(1+s)*(1+d.weekday()))
                d+=timedelta(days=1)
            N=sum(n for n,y in cells.values());Y=sum(y for n,y in cells.values())
            for (week,s),(n,y) in cells.items(): w.writerow([m,week,f's{s}',n,n,y,N,Y])


class Contract(unittest.TestCase):
    def test_split_week_and_opening(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'weekly.csv';fixture(path)
            data=mod.load(path);ex=mod.examples(data)
            # April 2023 starts on Saturday. The last bin contains Monday-Friday only.
            e=ex[39];self.assertEqual(len(e.ids),3)
            self.assertAlmostEqual(float(e.x[0,1,-1]),5/7,places=6)
            self.assertAlmostEqual(float(e.x[0,0,-1]*e.scale[0]),15.,places=4)
            for (k,_),v in data[4].items():
                if k>=39:v[:]+=12345
            data[2][39:]+=567
            e2=mod.examples(data)[39]
            self.assertTrue(torch.equal(e.x,e2.x));self.assertEqual(e.cold,e2.cold)
            self.assertLess(e.actual.sum(),e.total)
            torch.set_num_threads(1)
            model,ridge=mod.fit([ex[k] for k in range(12,39)])
            self.assertTrue(torch.isfinite(model(e.x)).all())
            self.assertTrue(np.isfinite(ridge).all())


if __name__=='__main__': unittest.main()

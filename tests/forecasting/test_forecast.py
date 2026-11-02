"""Regression checks for the published benchmark and chronological evaluation."""
import csv
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
import forecast_iowa as fc


def fixture():
    # Synthetic warm-up portion only: never report candidate scores on this as Iowa results.
    vals=[round(2400000 + i*1500 + 190000*math.sin(i*math.pi/6) + 10000*math.sin(i)) for i in range(81)]
    vals[60:69]=fc.REF_SEASON; vals[72:81]=fc.REF_ACTUAL
    return [dict(snapshot_id="fixture",month_start=fc.month(i).isoformat(),bottles=str(v),
                 source_records="1",completeness="UNVERIFIED") for i,v in enumerate(vals)]


class ForecastTests(unittest.TestCase):
    def test_measured_reference(self):
        m=fc.metrics(fc.REF_SEASON,fc.REF_ACTUAL)
        self.assertAlmostEqual(m["mae"],54167.66666667,5)
        self.assertAlmostEqual(m["wape_pct"],2.2132605866)
        self.assertGreater(m["bias"],0)

    def test_missing_month_fails(self):
        rows=fixture();rows[31]["month_start"]=rows[32]["month_start"]
        buf=io.StringIO(); w=csv.DictWriter(buf,fieldnames=fc.FIELDS);w.writeheader();w.writerows(rows)
        with self.assertRaises(ValueError):fc.load_series(buf.getvalue().encode())

    def test_validation_bias_can_block_lower_mae(self):
        self.assertEqual(fc.choose(dict(seasonal_naive=dict(mae=100,bias=1),ridge_1=dict(mae=80,bias=-5))),"seasonal_naive")

    def test_backtest_and_no_test_target_in_training(self):
        rows=fixture()
        with tempfile.TemporaryDirectory() as td:
            out=Path(td); first=fc.experiment(rows,out); original=(out/"predictions.csv").read_text()
            rows[72]["bottles"]="9999999"
            second=fc.experiment(rows,out,False)
            self.assertEqual(first["chosen"],second["chosen"])
            def invariant_predictions(text):
                return [(r["model"],r["target"],r["forecast"]) for r in csv.DictReader(io.StringIO(text))
                        if r["phase"]=="fixed_dec_2025" or (r["phase"]=="rolling_test" and r["target"]=="2026-01-01")]
            self.assertEqual(invariant_predictions(original),invariant_predictions((out/"predictions.csv").read_text()))
            self.assertIn("ridge_1",[r["model"] for r in csv.DictReader(io.StringIO(original))])
            self.assertEqual(first["next_forecast"]["actual"],None)


if __name__=="__main__": unittest.main()

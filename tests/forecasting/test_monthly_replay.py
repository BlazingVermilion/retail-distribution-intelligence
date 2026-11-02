"""Lock the published baseline to its source vintage and nine actual targets."""
import json
from pathlib import Path
import sys
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from backtest_monthly import SOURCE, score


class PublishedReplay(TestCase):
    def test_snapshot_reference(self):
        evidence = json.loads(SOURCE.read_text())
        self.assertEqual(evidence['snapshot_id'], 'bae8dc30-62b6-4d3d-9368-f7d3b57f7163')
        result = score(evidence['bottle_history'])
        self.assertEqual(result['seasonal_naive'], dict(months=9, mae_bottles=54167.67, wape_pct=2.2133))
        self.assertLess(result['seasonal_naive']['wape_pct'], result['holt_winters']['wape_pct'])

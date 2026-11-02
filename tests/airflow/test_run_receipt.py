"""Exercise the real preparer in a temporary project; no warehouse credentials required."""
import csv
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import airflow_task as adapter
from snapshot_ingestion import COLUMNS
from warehouse_state import source_identity


class ReceiptTests(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.cache = self.root / "artifacts/snapshots"
        for attr, value in (("ROOT", self.root), ("CACHE", self.cache)):
            self.enterContext(patch.object(adapter, attr, value))
        self.enterContext(patch.dict(os.environ, {"RDI_RUN_ID": "manual__first"}))
        self.input = self.root / "data/raw/2025/part.csv"
        self.input.parent.mkdir(parents=True)

    def write(self, header, amount):
        row = [""] * len(header)
        row[0] = amount
        with self.input.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerow(row)

    def test_load_uses_own_receipt_after_newest_bundle_changes(self):
        self.write(COLUMNS, "A")
        adapter.execute("prepare")
        receipt = adapter.run_directory()[1] / "bundle.json"
        pin = json.loads(receipt.read_text())
        with patch.dict(os.environ, {"RDI_RUN_ID": "manual__second"}):
            self.write(COLUMNS, "B")
            adapter.execute("prepare")
        self.assertNotEqual(json.loads((self.cache/"latest.json").read_text())["bundle_id"], pin["bundle_id"])
        with patch.object(adapter, "load", return_value=dict(state="SKIPPED", rows=1, run_id="test", bundle_id=pin["bundle_id"])) as loader:
            adapter.execute("load")
            loader.assert_called_once_with(self.cache / pin["bundle_id"])

    def test_bad_header_creates_no_receipt_and_corrected_retry_works(self):
        self.write(["bad_header"], "bad")
        receipt = adapter.run_directory()[1] / "bundle.json"
        with self.assertRaises(ValueError):
            adapter.execute("prepare")
        self.assertFalse(receipt.exists())
        self.write(COLUMNS, "fixed")
        adapter.execute("prepare")
        self.assertEqual(json.loads(receipt.read_text())["rows"], 1)

    def test_same_count_different_source_is_rejected_under_lock(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = ("other", "same-summary", 1, "run")
        with patch.dict(os.environ, {"RDI_EXPECTED_EXPORT_SHA256": "original"}):
            with self.assertRaisesRegex(ValueError, "active source differs"):
                source_identity(cursor)


if __name__ == "__main__":
    main()

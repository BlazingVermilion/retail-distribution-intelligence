import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from retail_platform.ingestion.manifest import inspect_snapshot, write_manifest


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.schema = json.loads((ROOT / 'configs/source_schema.json').read_text())
        self.fixture = ROOT / 'data/fixtures/transactions.csv'
        with self.fixture.open(newline='') as stream:
            self.rows = list(csv.reader(stream))

    def make_csv(self, name, rows):
        path = self.directory / name
        with path.open('w', newline='') as stream:
            csv.writer(stream).writerows(rows)
        return path

    def inspect(self, paths):
        return inspect_snapshot(paths, 2026, self.schema)

    def test_preserves_duplicate_rows_and_counts_missing_prices(self):
        result = self.inspect([self.fixture])
        self.assertEqual(result['row_count'], 4)
        self.assertEqual(result['files'][0]['missing_by_column']['state_bottle_retail'], 1)
        self.assertEqual(result['publication_status'], 'not_evaluated')

    def test_identity_independent_of_file_order_and_name(self):
        a = self.make_csv('a.csv', self.rows[:2])
        b = self.make_csv('b.csv', [self.rows[0], self.rows[-1]])
        renamed = self.directory / 'renamed.csv'
        shutil.copyfile(a, renamed)
        self.assertEqual(self.inspect([a,b])['snapshot_id'], self.inspect([b,renamed])['snapshot_id'])

    def test_rejects_identical_file_content(self):
        copy = self.directory / 'copy.csv'
        shutil.copyfile(self.fixture, copy)
        with self.assertRaisesRegex(ValueError, 'Duplicate file content'):
            self.inspect([self.fixture, copy])

    def test_rejects_invalid_present_values(self):
        for name, value in [('ordered_on','2025-01-01'), ('ordered_on','2026-02-30'),
                            ('sales_dollars','NaN'), ('sales_bottles','2.5')]:
            with self.subTest(name=name,value=value):
                rows = [self.rows[0][:], self.rows[1][:]]
                rows[1][rows[0].index(name)] = value
                with self.assertRaises(ValueError):
                    self.inspect([self.make_csv('bad.csv', rows)])

    def test_rejects_header_and_field_count(self):
        for rows in [[['wrong'], ['1']], [self.rows[0], self.rows[1][:-1]]]:
            with self.assertRaises(ValueError):
                self.inspect([self.make_csv('bad.csv', rows)])

    def test_protects_input_from_overwrite(self):
        with self.assertRaises(ValueError):
            write_manifest({}, self.fixture, [self.fixture])

    def test_atomic_output_is_valid_json(self):
        path = self.directory / 'output/manifest.json'
        manifest = self.inspect([self.fixture])
        write_manifest(manifest, path, [self.fixture])
        self.assertEqual(json.loads(path.read_text()), manifest)

    def test_empty_input_selection_rejected(self):
        with self.assertRaises(ValueError):
            self.inspect([])


if __name__ == '__main__':
    unittest.main()

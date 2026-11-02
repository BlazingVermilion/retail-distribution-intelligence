"""Offline publication-gate regressions; no database or credentials required."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from publish_snapshot import REQUIRED_TESTS, snapshot_fingerprint, validate_evidence


def fixture():
    names = sorted(REQUIRED_TESTS) + ['quality_observations'] + [f'constraint_{i}' for i in range(22)]
    manifest = {'metadata': {'invocation_id': 'fresh-run'}, 'nodes': {
        'test.'+name: {'name': name, 'resource_type': 'test', 'config': {'enabled': True}, 'tags': []}
        for name in names}}
    results = {'metadata': {'invocation_id': 'fresh-run'}, 'results': [
        {'unique_id': uid, 'status': 'pass'} for uid in manifest['nodes']]}
    return manifest, results


class EvidenceGateTests(unittest.TestCase):
    def test_complete_run_passes(self):
        self.assertEqual(validate_evidence(*fixture())['tests'], 27)

    def test_known_quality_warning_remains_visible(self):
        m, r = fixture()
        result = next(x for x in r['results'] if x['unique_id'] == 'test.quality_observations')
        result.update(status='warn', failures=3)
        self.assertEqual(validate_evidence(m, r)['warnings'][0]['failing_months'], 3)

    def test_structural_failures_and_warnings_block(self):
        for status in ('fail', 'error', 'skipped', 'warn'):
            with self.subTest(status=status):
                m, r = fixture()
                r['results'][0]['status'] = status
                with self.assertRaises(ValueError): validate_evidence(m, r)

    def test_missing_or_duplicate_results_block(self):
        for change in ('missing', 'duplicate'):
            m, r = fixture()
            if change == 'missing': r['results'].pop()
            else: r['results'].append(copy.deepcopy(r['results'][0]))
            with self.assertRaises(ValueError): validate_evidence(m, r)

    def test_stale_results_block(self):
        m, r = fixture()
        r['metadata']['invocation_id'] = 'old-run'
        with self.assertRaises(ValueError): validate_evidence(m, r)

    def test_missing_required_test_blocks(self):
        m, r = fixture()
        del m['nodes']['test.monthly_preservation']
        with self.assertRaises(ValueError): validate_evidence(m, r)

    def test_legacy_parity_is_not_a_publication_gate(self):
        m, r = fixture()
        m['nodes']['test.monthly_preservation']['tags'] = ['parity']
        with self.assertRaises(ValueError): validate_evidence(m, r)

    def test_fingerprint_is_repeatable(self):
        self.assertEqual(snapshot_fingerprint({'b': 2, 'a': 1}, 'code', ['row']),
                         snapshot_fingerprint({'a': 1, 'b': 2}, 'code', ['row']))

    def test_changed_input_policy_or_rows_changes_identity(self):
        original = snapshot_fingerprint({'export': 'a'}, 'code1', ['row1'])
        for source, code, rows in [({'export': 'b'}, 'code1', ['row1']),
                                    ({'export': 'a'}, 'code2', ['row1']),
                                    ({'export': 'a'}, 'code1', ['row2'])]:
            self.assertNotEqual(original, snapshot_fingerprint(source, code, rows))


if __name__ == '__main__':
    unittest.main()

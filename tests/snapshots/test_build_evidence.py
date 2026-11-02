"""Full-build certification rejects partial or stale dbt artifacts."""
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from run_dbt import EXPECTED_MODELS,full_build_evidence


class BuildEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.target=Path(self.temp.name)
        self.started=datetime.now(timezone.utc)-timedelta(seconds=1)
        self.manifest={'metadata':{'invocation_id':'current'},'nodes':{
            'model.project.'+n:{'name':n} for n in EXPECTED_MODELS}}
        self.results={'metadata':{'invocation_id':'current','generated_at':datetime.now(timezone.utc).isoformat()},
                      'results':[{'unique_id':u,'status':'success'} for u in self.manifest['nodes']]}

    def save(self):
        (self.target/'manifest.json').write_text(json.dumps(self.manifest))
        (self.target/'run_results.json').write_text(json.dumps(self.results))

    def test_complete_fresh_build_passes(self):
        self.save();self.assertEqual(full_build_evidence(self.target,self.started),'current')

    def test_partial_build_is_rejected(self):
        self.results['results'].pop();self.save()
        with self.assertRaises(ValueError):full_build_evidence(self.target,self.started)

    def test_old_artifacts_are_rejected(self):
        self.results['metadata']['generated_at']=(self.started-timedelta(days=1)).isoformat();self.save()
        with self.assertRaises(ValueError):full_build_evidence(self.target,self.started)

    def test_mixed_invocations_are_rejected(self):
        self.results['metadata']['invocation_id']='other';self.save()
        with self.assertRaises(ValueError):full_build_evidence(self.target,self.started)


if __name__=='__main__':unittest.main()

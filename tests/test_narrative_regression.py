import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from narrative_checks import checks

class Regression(unittest.TestCase):
    def test_september_signed_yoy(self):
        ref={'yoy':'Reported sales changed by +1.72% versus the same calendar month last year.'}
        sentence='Sales have increased by 1.72% compared to the same period last year.'
        for text,valid in [(sentence,True),(ref['yoy'],True),(sentence.replace('increased','decreased'),False),
                           (sentence.replace('have','have not'),False),(sentence.replace('1.72','1.27'),False),
                           (sentence.replace('same period last year','previous month'),False)]:
            self.assertEqual(all(checks(ref,{'yoy':text}).values()),valid)
        neg={'yoy':ref['yoy'].replace('+','-')}
        self.assertTrue(all(checks(neg,{'yoy':sentence.replace('increased','decreased')}).values()))
        self.assertFalse(all(checks(neg,{'yoy':sentence}).values()))

    def test_march_status_remains_protected(self):
        ref={'quality':'Monetary reconciliation status: NOT_EVALUABLE. The money check covered 0.00% of records. The absolute difference rate is unavailable.'}
        old={'quality':'The monetary reconciliation process was unable to evaluate the coverage of records, as the percentage of records covered was 0.00% and the absolute difference rate is unavailable.'}
        self.assertFalse(checks(ref,old)['quality.status'])
        self.assertTrue(all(checks(ref,ref).values()))

if __name__=='__main__': unittest.main()

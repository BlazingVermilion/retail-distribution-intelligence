import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase,main
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import airflow_reporting as ar
from monthly_brief import read_month


class Contract(TestCase):
    def test_pinned_query(self):
        db=MagicMock()
        read_month('2026-09','pinned',db)
        sql,params=db.cursor.return_value.__enter__.return_value.execute.call_args.args
        self.assertNotIn('current_snapshot',sql)
        self.assertIn('s.snapshot_id=%s',sql)
        self.assertEqual(params,('pinned',))

    def test_reuse_rejects_changed_output(self):
        with TemporaryDirectory() as temp,patch.object(ar,'ROOT',Path(temp)):
            for n in ar.FILES:(ar.ROOT/n).write_text(n)
            entry=dict(key='a',folder='.',hashes={n:ar.sha(ar.ROOT/n) for n in ar.FILES})
            self.assertTrue(ar.verified(entry,'a'))
            self.assertFalse(ar.verified(entry,'b'))
            (ar.ROOT/'brief.md').write_text('changed')
            self.assertFalse(ar.verified(entry,'a'))

if __name__=='__main__':main()

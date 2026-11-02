"""Test the DAG adapter with a run receipt and simulated database clients."""
import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import airflow_snowflake as task
import sync_snowflake_kpis as sync


class Adapter(unittest.TestCase):
    def test_pinned_retry(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as st:
            folder = Path(tmp)
            sid, pub = str(uuid4()), str(uuid4())
            pin = dict(snapshot_id=sid, publication_run_id=pub, state='UNCHANGED', airflow_run_id='r')
            (folder/'publication.json').write_text(json.dumps(pin))
            mods = {k: MagicMock() for k in ('airflow_task','airflow_reporting','publish_snapshot','psycopg2')}
            mods['airflow_task'].run_directory.return_value = ('r', folder)
            cur = mods['psycopg2'].connect.return_value.cursor.return_value.__enter__.return_value
            cur.fetchall.return_value = [(1,'2026-09-01',210648,'35755891.95','2558986')]
            st.enter_context(patch.dict(sys.modules, mods))
            st.enter_context(patch.dict(task.os.environ, RDI_SF_SYNC_ENABLED='1'))
            st.enter_context(patch.object(sync,'ROOT',folder))
            sf = st.enter_context(patch.object(task,'connect'))
            cloud = sf.return_value.cursor.return_value.__enter__.return_value
            cloud.fetchall.return_value = sync.normalize([dict(month_count=1,month_start='2026-09-01',
                source_records=210648,reported_sales_dollars='35755891.95',sales_bottles='2558986')])
            self.assertEqual(task.run(), 0)
            self.assertEqual(cur.execute.call_args.args[1], (pub,'UNCHANGED',sid))
            receipt = mods['airflow_reporting'].save.call_args.args[1]
            self.assertEqual((receipt['sync_state'],receipt['verification']),('UNCHANGED','VERIFIED'))
            with sync.writer_lock(), self.assertRaises(RuntimeError), sync.writer_lock():
                pass
            mods['airflow_task'].run_directory.return_value = ('other-run',folder)
            with self.assertRaises(ValueError):
                task.run()
            sf.assert_called_once()


if __name__ == '__main__':
    unittest.main()

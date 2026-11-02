"""Exercise insert, rerun and drift against a simulated Snowflake cursor."""
import sys
from pathlib import Path
from datetime import date
from decimal import Decimal
from unittest import TestCase,main
from unittest.mock import MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from sync_snowflake_kpis import replicate


class Sync(TestCase):
    rows=[(date(2026,9,1),210648,Decimal('35755891.95'),2558986)]

    def test_insert_then_rerun(self):
        c=MagicMock();c.fetchall.side_effect=[[],self.rows,self.rows,self.rows]
        for verify,state in [(False,'INSERTED'),(False,'UNCHANGED'),(True,'VERIFIED')]:
            self.assertEqual(replicate(c,'sid',self.rows,verify),state)
        self.assertEqual(sum(a.args[0].startswith('INSERT') for a in c.execute.call_args_list),1)

    def test_rollback_on_rounding_or_duplicates(self):
        for bad in ([(*self.rows[0][:2],Decimal('35755892'),2558986)],self.rows*2):
            c=MagicMock();c.fetchall.side_effect=[[],bad]
            with self.assertRaises(ValueError):replicate(c,'sid',self.rows,False)
            c.execute.assert_called_with('ROLLBACK')

if __name__=='__main__':main()

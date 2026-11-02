"""Snapshot preparation, change detection and recovery-policy regression tests."""
import contextlib
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from snapshot_ingestion import (COLUMNS,discover,inventory_diff,load,prepare,
                                replacement_policy,validate_bundle)
from warehouse_state import require_current_build


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'raw'
        self.cache=Path(self.temp.name)/'cache'
        self.row=['']*23
        self.row[0]='SAME-INVOICE'
        self.row[1]='2025-07-01'
        self.row[2]='0001'
        self.row[18]='12.345'
        self.row[19]='2'
        self.row[20]='24.69'

    def write(self,name,rows):
        path=self.root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('w',encoding='utf-8',newline='') as file:
            writer=csv.writer(file);writer.writerow(COLUMNS);writer.writerows(rows)
        return path

    def quiet_prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return prepare(self.root,self.cache)

    def test_cross_file_year_dedup_preserves_variants_and_strings(self):
        variant=self.row.copy();variant[20]='24.70'
        self.write('2025/part1.csv',[self.row,self.row])
        self.write('2026/part2.csv',[self.row,variant])
        result=self.quiet_prepare()
        self.assertEqual(result['rows'],2)
        self.assertEqual(result['exact_duplicates_removed'],2)
        path,manifest,report=validate_bundle(Path(result['bundle']))
        with (path/'exact_deduplicated.csv').open(newline='',encoding='utf-8') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual({r['store_no'] for r in rows},{'0001'})
        self.assertEqual({r['state_bottle_retail'] for r in rows},{'12.345'})
        self.assertEqual({r['sales_dollars'] for r in rows},{'24.69','24.70'})
        self.assertEqual(len({r['_audit_row_id'] for r in rows}),2)
        self.assertTrue(Path(report['audit_database']).exists())
        self.assertEqual(self.quiet_prepare()['state'],'REUSED')

    def test_same_count_same_name_changed_content_creates_new_bundle(self):
        self.write('2025/data.csv',[self.row]);first=self.quiet_prepare()
        changed=self.row.copy();changed[20]='99.99'
        self.write('2025/data.csv',[changed]);second=self.quiet_prepare()
        self.assertEqual(first['rows'],second['rows'])
        self.assertNotEqual(first['bundle'],second['bundle'])
        validate_bundle(Path(first['bundle']))  # Old export remains recoverable.
        self.assertEqual(validate_bundle(self.cache/'latest.json')[0],Path(second['bundle']))

    def test_tampered_export_is_rejected(self):
        self.write('2025/data.csv',[self.row]);result=self.quiet_prepare()
        path=Path(result['bundle']);(path/'exact_deduplicated.csv').write_text('corrupt')
        with self.assertRaises(ValueError):validate_bundle(path)

    def test_failed_prepare_keeps_previous_pointer(self):
        self.write('2025/data.csv',[self.row]);self.quiet_prepare()
        previous=(self.cache/'latest.json').read_bytes()
        self.write('2025/bad.csv',[['wrong','shape']])
        with self.assertRaises(ValueError):self.quiet_prepare()
        self.assertEqual((self.cache/'latest.json').read_bytes(),previous)
        self.assertFalse((self.cache/'prepare.lock').exists())

    def test_rejects_csv_outside_year_folder(self):
        self.write('data.csv',[self.row])
        with self.assertRaises(ValueError):discover(self.root)

    def test_nested_year_csv_is_discovered(self):
        self.write('2025/parts/a.CSV',[self.row])
        self.assertEqual(discover(self.root)[0]['path'],'2025/parts/a.CSV')

    def test_future_year_is_automatically_discovered(self):
        self.write('2027/new.csv',[self.row])
        self.assertEqual(discover(self.root)[0]['year'],2027)

    def test_removal_and_change_are_distinct(self):
        old=[{'path':'a','sha256':'1'},{'path':'b','sha256':'2'}]
        new=[{'path':'b','sha256':'3'},{'path':'c','sha256':'4'}]
        self.assertEqual(inventory_diff(old,new),{'added':['c'],'removed':['a'],'changed':['b']})

    def test_partial_export_requires_explicit_reasoned_exception(self):
        changes={'added':[],'changed':[],'removed':['2020/a.csv']}
        with self.assertRaises(ValueError):replacement_policy(100,10,changes,False,False,'')
        with self.assertRaises(ValueError):replacement_policy(100,10,changes,True,True,'')
        replacement_policy(100,10,changes,True,True,'Approved correction to the complete input set')


class FakeCursor:
    """Return sequential database results to exercise the publication decision."""
    def __init__(self,rows):self.rows=iter(rows)
    def execute(self,*args):pass
    def fetchone(self):return next(self.rows)


class BuildFenceTests(unittest.TestCase):
    def test_new_export_with_same_row_count_blocks_stale_build(self):
        current=('new','summary',10,'run-new')
        old={'export_sha256':'old','summary_sha256':'summary','expected_rows':10,'load_run_id':'run-old'}
        cursor=FakeCursor([(True,),current,(True,old,'code')])
        with self.assertRaises(ValueError):require_current_build(cursor,'code')

    def test_valid_current_source_and_code_pass(self):
        current=('new','summary',10,'run-new')
        identity=dict(zip(('export_sha256','summary_sha256','expected_rows','load_run_id'),current))
        require_current_build(FakeCursor([(True,),current,(True,identity,'code')]),'code')

    def test_changed_code_blocks_publish(self):
        current=('new','summary',10,'run-new')
        identity=dict(zip(('export_sha256','summary_sha256','expected_rows','load_run_id'),current))
        with self.assertRaises(ValueError):
            require_current_build(FakeCursor([(True,),current,(True,identity,'old-code')]),'new-code')


if __name__=='__main__':unittest.main()

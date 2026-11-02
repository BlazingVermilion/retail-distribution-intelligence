"""Offline tests for the input contract; these do not simulate a PostgreSQL server."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from load_postgres import HEADER,csv_records,file_digest,read_summary,target_for

class LoaderInputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def write_csv(self,rows,header=HEADER):
        path=self.root/'export.csv'
        with path.open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(header);writer.writerows(rows)
        return path
    def record(self,identifier='1'):
        row=['']*24;row[0]='REPEATED-INVOICE';row[2]='0012';row[14]='Quoted, product\nsecond line';row[-1]=identifier
        return row
    def test_strings_and_multiline_fields_are_preserved(self):
        row=self.record(); actual=list(csv_records(self.write_csv([row])))[0]
        self.assertEqual(actual[:-1],tuple(row[:-1]));self.assertEqual(actual[-1],1)
    def test_sample_limit_counts_csv_records_not_physical_lines(self):
        path=self.write_csv([self.record('1'),self.record('2')])
        self.assertEqual(len(list(csv_records(path,1))),1)
        self.assertEqual(len(list(csv_records(path))),2)
    def test_invalid_shape_and_id_are_rejected(self):
        for row in [self.record()[:-1],self.record('0'),self.record('abc'),self.record(str(2**63))]:
            with self.subTest(row=row[-1]):
                with self.assertRaises(ValueError):list(csv_records(self.write_csv([row])))
    def test_raw_23_column_header_is_rejected(self):
        with self.assertRaises(ValueError):list(csv_records(self.write_csv([],HEADER[:-1])))
    def test_report_count_reconciliation(self):
        path=self.root/'summary.json'
        report={'status':'completed','version':2,'distinct_export_created':True,
                'source_row_count':3,'exported_rows':2,'distinct_exact_records':2,'exact_excess_occurrences':1}
        path.write_text(json.dumps(report));self.assertEqual(read_summary(path)[0],report)
        report['exact_excess_occurrences']=2;path.write_text(json.dumps(report))
        with self.assertRaises(ValueError):read_summary(path)
    def test_sample_and_full_have_separate_targets_and_locks(self):
        self.assertNotEqual(target_for(10000)[0],target_for(None)[0])
        self.assertNotEqual(target_for(10000)[2],target_for(None)[2])
        with self.assertRaises(ValueError):target_for(0)
    def test_digest_is_content_based(self):
        a=self.root/'a';b=self.root/'b';a.write_bytes(b'one');b.write_bytes(b'one')
        self.assertEqual(file_digest(a),file_digest(b));b.write_bytes(b'two')
        self.assertNotEqual(file_digest(a),file_digest(b))

if __name__=='__main__':unittest.main()

"""Disk-backed exact-record audit. Source CSVs are never modified."""
import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

COLUMNS = ['invoice_id','ordered_on','store_no','store_name','store_address',
           'store_city','store_zip_code','county_fips_code','county_name',
           'category_code','category_name','vendor_number','vendor_name',
           'item_no','im_desc','pack','bottle_volume_ml','state_bottle_cost',
           'state_bottle_retail','sales_bottles','sales_dollars','sales_liters',
           'sales_gallons']


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def flush(connection, batch):
    connection.executemany('INSERT INTO stage VALUES (?,?,?,?)', batch)
    connection.execute('''INSERT OR IGNORE INTO variants(payload,invoice_id)
                          SELECT payload,invoice_id FROM stage''')
    connection.execute('''INSERT INTO occurrences(row_id,file_id,n,first_record)
        SELECT v.row_id,s.file_id,COUNT(*),MIN(s.record_no)
        FROM stage s JOIN variants v ON v.payload=s.payload
        GROUP BY v.row_id,s.file_id
        ON CONFLICT(row_id,file_id) DO UPDATE SET n=n+excluded.n,
        first_record=MIN(first_record,excluded.first_record)''')
    connection.execute('DELETE FROM stage')
    connection.commit()
    batch.clear()


def connect_existing(database):
    database = Path(database).resolve()
    if not database.is_file():
        raise ValueError(f'Database not found: {database}')
    if (database.parent / 'FAILED.txt').exists():
        raise ValueError('Database belongs to a failed audit.')
    summary = database.parent / 'summary.json'
    if not summary.exists() or json.loads(summary.read_text())['status'] != 'completed':
        raise ValueError('A completed summary.json must accompany the audit database.')
    conn = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    required = {'files', 'variants', 'occurrences', 'totals'}
    found = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not required <= found:
        conn.close()
        raise ValueError('Database schema is not compatible with this utility.')
    return conn


def ingest(inputs, output):
    conn = sqlite3.connect(output / 'audit.sqlite')
    conn.execute('PRAGMA temp_store=FILE')
    conn.execute('PRAGMA cache_size=-65536')
    conn.executescript('''
    CREATE TABLE files(file_id INTEGER PRIMARY KEY, year INTEGER, path TEXT,
                       sha256 TEXT, row_count INTEGER);
    CREATE TABLE variants(row_id INTEGER PRIMARY KEY, payload TEXT NOT NULL UNIQUE,
                          invoice_id TEXT NOT NULL);
    CREATE TABLE occurrences(row_id INTEGER, file_id INTEGER, n INTEGER,
                             first_record INTEGER, PRIMARY KEY(row_id,file_id));
    CREATE TABLE date_issues(file_id INTEGER, record_no INTEGER, declared_year INTEGER,
                             ordered_on TEXT, issue TEXT);
    CREATE TEMP TABLE stage(payload TEXT, invoice_id TEXT, file_id INTEGER, record_no INTEGER);
    ''')
    try:
        for file_id, (year, path) in enumerate(inputs, 1):
            path = Path(path)
            checksum = sha256(path)
            print(f'Reading {year}: {path.name}', flush=True)
            conn.execute('INSERT INTO files VALUES (?,?,?,?,0)',
                         (file_id, year, str(path.resolve()), checksum))
            batch, count = [], 0
            with path.open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.reader(stream, strict=True)
                if next(reader, None) != COLUMNS:
                    raise ValueError(f'Header mismatch: {path}')
                for count, row in enumerate(reader, 1):
                    if len(row) != len(COLUMNS):
                        raise ValueError(f'Wrong field count: {path}, record {count}')
                    issue = None
                    if not row[1].strip():
                        issue = 'missing_date'
                    else:
                        try:
                            parsed = date.fromisoformat(row[1])
                            if parsed.isoformat() != row[1]:
                                issue = 'invalid_date_format'
                            elif parsed.year != year:
                                issue = 'folder_year_mismatch'
                        except ValueError:
                            issue = 'invalid_date'
                    if issue:
                        conn.execute('INSERT INTO date_issues VALUES (?,?,?,?,?)',
                                     (file_id, count, year, row[1], issue))
                    payload = json.dumps(row, ensure_ascii=False, separators=(',', ':'))
                    batch.append((payload, row[0], file_id, count))
                    if len(batch) == 10000:
                        flush(conn, batch)
                if batch:
                    flush(conn, batch)
            if sha256(path) != checksum:
                raise ValueError(f'Input changed during audit: {path}')
            conn.execute('UPDATE files SET row_count=? WHERE file_id=?', (count, file_id))
            conn.commit()
            print(f'  {count:,} records', flush=True)
        conn.executescript('''
        CREATE INDEX invoice_lookup ON variants(invoice_id);
        CREATE INDEX occurrence_file ON occurrences(file_id);
        CREATE TABLE totals AS
          SELECT row_id,SUM(n) total_n,COUNT(*) file_count,MAX(n) max_file_n
          FROM occurrences GROUP BY row_id;
        CREATE UNIQUE INDEX totals_row ON totals(row_id);
        ''')
        return conn
    except BaseException:
        conn.close()
        raise


def generate_outputs(conn, output, database_path, export_distinct):
    def report(name, sql):
        print(f'Writing {name}', flush=True)
        count = 0
        with (output / name).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            cursor = conn.execute(sql)
            writer.writerow([c[0] for c in cursor.description])
            for row in cursor:
                writer.writerow(row)
                count += 1
        return count

    report('files.csv', 'SELECT * FROM files ORDER BY year,path')
    report('exact_duplicate_groups.csv', '''SELECT v.row_id,v.invoice_id,t.total_n,
        t.file_count,t.total_n-1 exact_excess_occurrences,t.max_file_n max_occurrences_in_one_file
        FROM totals t JOIN variants v USING(row_id) WHERE t.total_n>1 ORDER BY v.row_id''')
    report('duplicate_locations.csv', '''SELECT o.row_id,o.file_id,f.path,o.n,o.first_record
        FROM occurrences o JOIN totals t USING(row_id) JOIN files f USING(file_id)
        WHERE t.total_n>1 ORDER BY o.row_id,o.file_id''')
    # Reference occurrence selection only; identical values do not have a "better" version.
    conn.execute('''CREATE TEMP TABLE representatives AS
        SELECT o.row_id,MIN(o.file_id) retained_file_id
        FROM occurrences o JOIN totals t USING(row_id)
        WHERE t.total_n>1 GROUP BY o.row_id''')
    report('deduplication_lineage.csv', '''SELECT o.row_id,o.file_id,f.path source_path,
        o.first_record first_record_in_file,o.n source_occurrences,
        CASE WHEN o.file_id=r.retained_file_id THEN 1 ELSE 0 END retained_occurrences,
        o.n-CASE WHEN o.file_id=r.retained_file_id THEN 1 ELSE 0 END removed_occurrences,
        r.retained_file_id,keep.first_record retained_record
        FROM representatives r JOIN occurrences o USING(row_id)
        JOIN files f ON f.file_id=o.file_id
        JOIN occurrences keep ON keep.row_id=r.row_id AND keep.file_id=r.retained_file_id
        ORDER BY o.row_id,o.file_id''')
    report('file_overlap.csv', '''SELECT f.file_id,f.year,f.path,f.row_count,
        COALESCE(SUM(MIN(o.n,t.total_n-o.n)),0) occurrences_matched_in_other_files,
        COALESCE(SUM(MAX(0,o.n-(t.total_n-o.n))),0) occurrences_unmatched_in_other_files,
        COALESCE(SUM(o.n-1),0) within_file_exact_excess
        FROM files f LEFT JOIN occurrences o USING(file_id)
        LEFT JOIN totals t USING(row_id) GROUP BY f.file_id ORDER BY f.year,f.path''')
    report('year_summary.csv', '''SELECT f.year,SUM(o.n) source_rows,
        COUNT(DISTINCT o.row_id) distinct_exact_records
        FROM files f JOIN occurrences o USING(file_id) GROUP BY f.year ORDER BY f.year''')
    conn.execute('''CREATE TEMP TABLE conflicts AS
        SELECT v.invoice_id,COUNT(*) distinct_record_variants,SUM(t.total_n) source_occurrences
        FROM variants v JOIN totals t USING(row_id) WHERE TRIM(v.invoice_id)<>''
        GROUP BY v.invoice_id HAVING COUNT(*)>1''')
    conflicts = report('invoice_id_conflicts.csv', 'SELECT * FROM conflicts ORDER BY invoice_id')
    conn.execute('''CREATE TEMP TABLE cross_year AS
        SELECT v.invoice_id,COUNT(DISTINCT f.year) source_year_count,
        GROUP_CONCAT(DISTINCT f.year) source_years,
        COUNT(DISTINCT v.row_id) distinct_record_variants,SUM(o.n) source_occurrences
        FROM variants v JOIN occurrences o USING(row_id) JOIN files f USING(file_id)
        WHERE TRIM(v.invoice_id)<>'' GROUP BY v.invoice_id HAVING COUNT(DISTINCT f.year)>1''')
    cross_year = report('cross_year_invoice_ids.csv', 'SELECT * FROM cross_year ORDER BY invoice_id')
    # Full records for all within-file repeats, plus targeted conflicting/cross-year ID examples.
    def expanded_report(name, where):
        print(f'Writing {name}', flush=True)
        sql = '''SELECT v.row_id,f.year,f.path,o.n,o.first_record,v.payload
                 FROM variants v JOIN occurrences o USING(row_id) JOIN files f USING(file_id)
                 WHERE ''' + where + ' ORDER BY v.row_id,o.file_id'
        with (output / name).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['row_id','source_year','source_path','source_occurrences','first_record'] + COLUMNS)
            for row in conn.execute(sql):
                writer.writerow(list(row[:-1]) + json.loads(row[-1]))
    expanded_report('within_file_duplicate_details.csv',
                    'v.row_id IN (SELECT row_id FROM occurrences WHERE n>1)')
    expanded_report('conflict_examples.csv', '''v.invoice_id IN
        (SELECT invoice_id FROM conflicts ORDER BY distinct_record_variants DESC,invoice_id LIMIT 10)''')
    expanded_report('cross_year_examples.csv', '''v.invoice_id IN
        (SELECT invoice_id FROM cross_year ORDER BY invoice_id LIMIT 10)''')
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'date_issues' in tables:
        date_count = report('date_issues.csv', '''SELECT d.*,f.path FROM date_issues d
                            JOIN files f USING(file_id) ORDER BY d.file_id,d.record_no''')
        date_status = 'evaluated'
    else:
        date_count, date_status = None, 'not_available_in_legacy_database'
    row_count = conn.execute('SELECT COALESCE(SUM(row_count),0) FROM files').fetchone()[0]
    occurrence_count = conn.execute('SELECT COALESCE(SUM(n),0) FROM occurrences').fetchone()[0]
    distinct = conn.execute('SELECT COUNT(*) FROM variants').fetchone()[0]
    if row_count != occurrence_count:
        raise ValueError('Database row counts do not reconcile.')
    exported = 0
    if export_distinct:
        print('Writing exact_deduplicated.csv (this can take time)', flush=True)
        with (output / 'exact_deduplicated.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(COLUMNS + ['_audit_row_id'])
            for row_id, payload in conn.execute('SELECT row_id,payload FROM variants ORDER BY row_id'):
                writer.writerow(json.loads(payload) + [row_id])
                exported += 1
        if exported != distinct:
            raise ValueError('Export count does not reconcile.')
    result = {'status':'completed','version':2,'audit_database':str(database_path.resolve()),
              'source_file_count':conn.execute('SELECT COUNT(*) FROM files').fetchone()[0],
              'source_row_count':row_count,'distinct_exact_records':distinct,
              'exact_excess_occurrences':row_count-distinct,
              'invoice_ids_with_different_records':conflicts,'cross_year_invoice_ids':cross_year,
              'date_issue_count':date_count,'date_audit_status':date_status,
              'comparison':'All 23 parsed CSV strings; no numeric or whitespace normalization',
              'source_files_modified':False,'distinct_export_created':export_distinct,
              'exported_rows':exported if export_distinct else None,
              'deduplication_lineage_status':'applied_to_export' if export_distinct else 'proposed_only',
              'publication_status':'not_evaluated'}
    (output / 'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


def run(output, inputs=None, database=None, export_distinct=True):
    output = Path(output).resolve()
    if (inputs is None) == (database is None):
        raise ValueError('Choose exactly one of CSV inputs or an existing database.')
    if inputs is not None:
        if not inputs:
            raise ValueError('No CSV files selected.')
        for _, path in inputs:
            parent = Path(path).resolve().parent
            if output == parent or parent in output.parents:
                raise ValueError('Output must be outside source CSV directories.')
    conn = connect_existing(database) if database is not None else None
    try:
        output.mkdir(parents=True, exist_ok=False)
    except BaseException:
        if conn is not None:
            conn.close()
        raise
    try:
        if conn is None:
            conn = ingest(inputs, output)
        db_path = Path(database) if database is not None else output / 'audit.sqlite'
        return generate_outputs(conn, output, db_path, export_distinct)
    except BaseException as exc:
        (output / 'FAILED.txt').write_text(
            f'Incomplete run. Do not use partial reports or CSV exports.\n{type(exc).__name__}: {exc}\n',
            encoding='utf-8')
        raise
    finally:
        if conn is not None:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--input-root',type=Path)
    source.add_argument('--database',type=Path,help='Reuse a completed audit.sqlite without rereading CSVs.')
    parser.add_argument('--years',type=int,nargs='+',default=list(range(2020,2027)))
    parser.add_argument('--output-dir',type=Path,required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--audit-only',action='store_true',help='Write reports without exporting deduplicated CSV.')
    mode.add_argument('--export-exact-distinct',action='store_true',help='Compatibility flag; export is now the default.')
    args = parser.parse_args()
    try:
        inputs = None
        if args.input_root:
            inputs = []
            for year in sorted(set(args.years)):
                directory = args.input_root / str(year)
                paths = sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower()=='.csv')
                if not paths:
                    raise ValueError(f'No CSV files: {directory}')
                inputs.extend((year,p) for p in paths)
        elif args.years != list(range(2020,2027)):
            raise ValueError('--years applies only to --input-root; database mode processes all stored inputs.')
        result = run(args.output_dir,inputs,args.database,not args.audit_only)
    except (ValueError,OSError,KeyError,sqlite3.Error,csv.Error) as exc:
        parser.exit(2,f'Audit failed: {exc}\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()

"""Load an audited exact-distinct export into local PostgreSQL.

Usage:
    python scripts/load_postgres.py --file PATH --summary PATH --sample-rows 10000
    python scripts/load_postgres.py --file PATH --summary PATH

Contract:
    Accept the 24-column export produced by audit_duplicates.py version 2.
    Preserve all 23 source strings and the audit-local record identifier.
    Never treat invoice_id as a unique key. Never modify the source file.

A single transaction covers COPY, row-count reconciliation and the completed-load
registry. Failed loads roll back. A target-wide advisory lock serializes loaders.
The sample and full tables each accept one export; changed inputs are refused
instead of silently appending a new snapshot or deleting existing data.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

LOGGER = logging.getLogger("retail.postgres_loader")
ROOT = Path(__file__).resolve().parents[1]
COLUMNS = ['invoice_id', 'ordered_on', 'store_no', 'store_name', 'store_address', 'store_city', 'store_zip_code', 'county_fips_code', 'county_name', 'category_code', 'category_name', 'vendor_number', 'vendor_name', 'item_no', 'im_desc', 'pack', 'bottle_volume_ml', 'state_bottle_cost', 'state_bottle_retail', 'sales_bottles', 'sales_dollars', 'sales_liters', 'sales_gallons']
HEADER = COLUMNS + ["_audit_row_id"]


def file_digest(path: Path) -> str:
    """Hash bytes in bounded memory to identify the input independently of its name."""
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_summary(path: Path) -> tuple[dict[str, Any], str]:
    """Validate that the report describes a completed version-2 distinct export.

    This report contains counts but no export-file checksum. The loader computes
    its own checksum for replay protection; it cannot prove the report's origin.
    """
    contents = path.read_bytes()
    report = json.loads(contents)
    if (report.get('status') != 'completed' or report.get('version') != 2
            or report.get('distinct_export_created') is not True):
        raise ValueError('Use summary.json from a completed version-2 export.')
    count = report.get('exported_rows')
    if type(count) is not int or count <= 0 or count != report.get('distinct_exact_records'):
        raise ValueError('Export count must be positive and match distinct_exact_records.')
    if report.get('source_row_count', 0) - count != report.get('exact_excess_occurrences'):
        raise ValueError('Audit counts do not reconcile.')
    return report, hashlib.sha256(contents).hexdigest()


def csv_records(path: Path, limit: int | None = None) -> Iterator[tuple[str | int, ...]]:
    """Yield records without numeric coercion of the 23 source fields.

    Preserve empty strings as empty strings. Validate the audit ID as positive
    BIGINT; PostgreSQL enforces uniqueness for this one accepted audit export.
    CSV parsing, rather than line slicing, handles quoted multiline fields.
    """
    with path.open(encoding='utf-8-sig', newline='') as source:
        reader = csv.reader(source, strict=True)
        if next(reader, None) != HEADER:
            raise ValueError('Expected the 24-column exact_deduplicated.csv header.')
        records = reader if limit is None else itertools.islice(reader, limit)
        for position, row in enumerate(records, 1):
            if len(row) != len(HEADER):
                raise ValueError(f'CSV record {position}: expected {len(HEADER)} fields.')
            if not row[-1].isascii() or not row[-1].isdigit():
                raise ValueError(f'CSV record {position}: invalid _audit_row_id.')
            identifier = int(row[-1])
            if not 0 < identifier <= 9223372036854775807:
                raise ValueError(f'CSV record {position}: _audit_row_id outside positive BIGINT range.')
            yield (*row[:-1], identifier)


def target_for(sample_rows: int | None) -> tuple[str, str, int]:
    """Return only hard-coded SQL targets and lock keys, never user-supplied SQL."""
    if sample_rows is not None:
        if sample_rows <= 0:
            raise ValueError('--sample-rows must be positive.')
        return 'staging.iowa_sales_sample', 'sample', 782901
    return 'staging.iowa_sales_exact', 'full', 782902


def connection_settings() -> dict[str, str | int]:
    """Read dedicated loader credentials; do not fall back to the admin password."""
    required = ['PG_LOADER_PASSWORD']
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise ValueError('Missing configuration: ' + ', '.join(missing))
    return {'host': os.getenv('PGHOST', '127.0.0.1'),
            'port': int(os.getenv('POSTGRES_PORT', '5433')),
            'dbname': os.getenv('POSTGRES_DB', 'retail_analytics'),
            'user': 'retail_loader', 'password': os.environ['PG_LOADER_PASSWORD'],
            'connect_timeout': 10, 'application_name': 'retail_export_loader'}


def load_export(path: Path, summary_path: Path, sample_rows: int | None) -> dict[str, Any]:
    """Load or skip one export and return its authoritative database result.

    Errors inside COPY or reconciliation roll back the data transaction. A RUNNING
    history entry is written beforehand. A hard process/network failure may leave
    that history entry RUNNING; pg_loaded_exports is the completed-load authority.
    """
    import psycopg
    from psycopg import sql
    from psycopg.types.json import Jsonb

    report, summary_hash = read_summary(summary_path)
    target, mode, lock_key = target_for(sample_rows)
    expected = min(sample_rows, report['exported_rows']) if sample_rows else report['exported_rows']
    # Validate the header before opening a database connection or hashing a large file.
    if next(csv_records(path, 1), None) is None:
        raise ValueError('The input export has no records.')
    LOGGER.info('Hashing export before load: %s', path.name)
    checksum = file_digest(path)
    run_id = uuid4()
    target_sql = sql.Identifier(*target.split('.'))
    settings = connection_settings()
    with psycopg.connect(**settings, autocommit=True) as connection:
        connection.execute('''INSERT INTO ops.pg_load_runs
            (run_id,target_table,source_path,source_sha256,expected_rows,state)
            VALUES (%s,%s,%s,%s,%s,'RUNNING')''',
            (run_id, target, str(path), checksum, expected))
        try:
            with connection.transaction():
                # Only one loader may decide whether this target is empty at a time.
                LOGGER.info('Acquiring load lock for %s', target)
                connection.execute('SELECT pg_advisory_xact_lock(%s)', (lock_key,))
                previous = connection.execute('''SELECT source_sha256,expected_rows,mode,summary_sha256
                    FROM ops.pg_loaded_exports WHERE target_table=%s''', (target,)).fetchone()
                if previous is not None:
                    if previous != (checksum, expected, mode, summary_hash):
                        raise ValueError('Target already contains another export or sample configuration. '
                                         'No append or replacement was performed.')
                    actual = connection.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(target_sql)).fetchone()[0]
                    if actual != expected:
                        raise ValueError('Previously loaded table count no longer matches the registry.')
                    state = 'SKIPPED'
                    LOGGER.info('Same export already loaded: %s rows. Skipping COPY.', actual)
                else:
                    if connection.execute(sql.SQL('SELECT EXISTS (SELECT 1 FROM {} LIMIT 1)').format(target_sql)).fetchone()[0]:
                        raise ValueError('Target contains unregistered data; refusing to append.')
                    copy_sql = sql.SQL('COPY {} ({}) FROM STDIN').format(
                        target_sql, sql.SQL(',').join(map(sql.Identifier, HEADER)))
                    sent = 0
                    LOGGER.info('Starting COPY into %s; expected rows: %s', target, expected)
                    with connection.cursor() as cursor:
                        # write_row uses PostgreSQL's text COPY adaptation. Do not add
                        # FORMAT CSV here: Python's CSV reader already parsed each field.
                        with cursor.copy(copy_sql) as copy:
                            for row in csv_records(path, sample_rows):
                                copy.write_row(row)
                                sent += 1
                                if sent % 250000 == 0:
                                    LOGGER.info('Sent %s rows; transaction not committed yet.', sent)
                    if sent != expected:
                        raise ValueError(f'CSV count mismatch: expected {expected}, read {sent}.')
                    LOGGER.info('Checking that the export did not change during COPY.')
                    if file_digest(path) != checksum:
                        raise ValueError('Input changed during load; rolling back.')
                    actual = connection.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(target_sql)).fetchone()[0]
                    if actual != expected:
                        raise ValueError(f'Database count mismatch: expected {expected}, got {actual}.')
                    connection.execute('''INSERT INTO ops.pg_loaded_exports
                        (target_table,source_sha256,source_path,expected_rows,mode,
                         summary_sha256,audit_summary,run_id)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (target,checksum,str(path),actual,mode,summary_hash,Jsonb(report),run_id))
                    state = 'COMPLETED'
                # Registry, table contents and completed run state commit together.
                connection.execute('''UPDATE ops.pg_load_runs SET state=%s,loaded_rows=%s,
                    finished_at=CURRENT_TIMESTAMP WHERE run_id=%s''', (state,actual,run_id))
            LOGGER.info('%s: %s rows in %s', state, actual, target)
            return {'state':state,'target':target,'rows':actual,'run_id':str(run_id)}
        except BaseException as exc:
            # Preserve the original failure even if the connection cannot record it.
            message = f'{type(exc).__name__}: {exc}'[:2000]
            if settings['password']:
                message = message.replace(str(settings['password']), '[REDACTED]')
            try:
                connection.execute('''UPDATE ops.pg_load_runs SET state='FAILED',error_message=%s,
                    finished_at=CURRENT_TIMESTAMP WHERE run_id=%s''', (message,run_id))
            except Exception:
                LOGGER.error('Could not update run history; inspect the completed-load registry before retrying.')
            raise


def main() -> None:
    """CLI entry point; read .env locally and keep credentials out of logs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--summary', type=Path, required=True)
    parser.add_argument('--sample-rows', type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env', override=False)
        result = load_export(args.file.resolve(), args.summary.resolve(), args.sample_rows)
        print(json.dumps(result, indent=2))
    except KeyboardInterrupt:
        LOGGER.error('Interrupted. Check ops.pg_loaded_exports before retrying.')
        sys.exit(130)
    except Exception as exc:
        message = f'{type(exc).__name__}: {exc}'
        for key in ('PG_LOADER_PASSWORD', 'POSTGRES_PASSWORD'):
            if os.getenv(key):
                message = message.replace(os.environ[key], '[REDACTED]')
        LOGGER.error('%s', message)
        sys.exit(1)


if __name__ == '__main__':
    main()

"""Shared coordination and build evidence for ingestion, dbt and publication.

Advisory lock 690011 is a cooperative warehouse lock. Exclusive holders change
source/models; shared holders validate or publish. Direct administrative SQL and
raw dbt.exe commands bypass this contract and must not run concurrently.
"""
from contextlib import contextmanager
import os

WAREHOUSE_LOCK = 690011


def acquire_lock(cursor, shared=False):
    function = 'pg_try_advisory_lock_shared' if shared else 'pg_try_advisory_lock'
    cursor.execute(f'SELECT {function}(%s)', (WAREHOUSE_LOCK,))
    if not cursor.fetchone()[0]:
        raise RuntimeError('Warehouse is busy with ingestion, dbt or publication. Retry after it finishes.')


@contextmanager
def warehouse_connection(settings, shared=False):
    import psycopg2
    connection = psycopg2.connect(**settings)
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            acquire_lock(cursor, shared)
        yield connection
    finally:
        # Closing the session releases its lock even after a failed transaction.
        connection.close()


def has_build_state(cursor):
    cursor.execute("""SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n
        ON n.oid=c.relnamespace WHERE n.nspname='ops' AND c.relname='source_build_state')""")
    return cursor.fetchone()[0]


def source_identity(cursor):
    cursor.execute("""SELECT source_sha256,summary_sha256,expected_rows,run_id::text
        FROM ops.pg_loaded_exports WHERE target_table='staging.iowa_sales_exact' AND mode='full'""")
    row = cursor.fetchone()
    if row is None:
        raise ValueError('No registered full source export. Load the audited export first.')
    identity = dict(zip(('export_sha256','summary_sha256','expected_rows','load_run_id'),row))
    # A manual loader could replace the source between two Airflow tasks. Check
    # the run's two pinned hashes while the caller holds the warehouse lock.
    for field in ('export_sha256', 'summary_sha256'):
        expected = os.getenv('RDI_EXPECTED_' + field.upper())
        if expected is not None and identity[field] != expected:
            raise ValueError('The active source differs from the bundle pinned to this Airflow run.')
    return identity


def require_current_build(cursor, code_hash):
    """Reject stale models even when old and new source exports have equal counts."""
    if not has_build_state(cursor):
        return  # Compatibility with pre-011 installation and its CI fixtures.
    current_source = source_identity(cursor)
    cursor.execute('SELECT valid,source_identity,code_sha256 FROM ops.source_build_state WHERE singleton')
    row = cursor.fetchone()
    if not row or not row[0] or row[1] != current_source or row[2] != code_hash:
        raise ValueError('No successful full dbt build for the current source and code. Run scripts/run_dbt.py build before publishing.')

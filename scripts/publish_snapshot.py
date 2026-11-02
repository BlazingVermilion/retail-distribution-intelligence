"""Validate and publish the current dbt monthly snapshot, or restore an older one.

This CLI is a single publication task for future Airflow integration. It does not
load CSVs, rebuild dbt models, correct source values or coordinate ingestion.
The publication transaction holds source/model locks while fresh dbt tests run.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID, uuid4
from warehouse_state import acquire_lock, require_current_build

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger("retail.publication")
LOCK_KEY = 690010
POLICY = "monthly_publication_v1"
REQUIRED_TESTS = {"source_row_count", "monthly_preservation", "monthly_count_bounds", "conversion_contract"}
MODEL_NAMES = ["stg_iowa_sales", "int_sales_reconciled", "fact_sales", "dim_store",
               "dim_product", "dim_date", "sales_monthly", "v_sales_monthly_kpis", "bi_sales_monthly"]


def project_digest(project: Path) -> str:
    """Identify executable model/test configuration, excluding generated artifacts."""
    paths = [project / "dbt_project.yml"]
    for directory in ("models", "macros", "tests"):
        paths.extend(p for p in (project / directory).rglob("*")
                     if p.is_file() and p.suffix in {".sql", ".yml", ".yaml"})
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(project).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def validate_evidence(manifest: dict, results: dict) -> dict:
    """Reject stale, incomplete, skipped or failed test evidence; allow one known warning."""
    invocation = manifest.get("metadata", {}).get("invocation_id")
    if not invocation or invocation != results.get("metadata", {}).get("invocation_id"):
        raise ValueError("Manifest and test results do not belong to the same invocation.")
    tests = {uid: node for uid, node in manifest["nodes"].items()
             if node.get("resource_type") == "test" and node.get("config", {}).get("enabled", True)}
    if any("parity" in node.get("tags", []) for node in tests.values()):
        raise ValueError("Publication tests must disable legacy parity; it is a migration-only gate.")
    if len(tests) < 27 or not REQUIRED_TESTS.issubset({node["name"] for node in tests.values()}):
        raise ValueError("Required publication tests are missing from the manifest.")
    seen, warnings = set(), []
    for item in results.get("results", []):
        uid, status = item.get("unique_id"), item.get("status")
        if uid not in tests:
            if status not in {"success", "pass"}:
                raise ValueError("A dbt hook or unexpected result did not succeed.")
            continue
        if uid in seen:
            raise ValueError("Duplicate test result in evidence.")
        seen.add(uid)
        if status == "warn" and tests[uid]["name"] == "quality_observations":
            warnings.append({"test": uid, "failing_months": item.get("failures")})
        elif status != "pass":
            raise ValueError(f"Publication blocked by {uid}: {status}")
    if seen != set(tests):
        raise ValueError("Not every enabled test produced a result.")
    return {"invocation_id": invocation, "tests": len(tests), "warnings": warnings}


def snapshot_fingerprint(source: dict, code_hash: str, rows: list[str]) -> str:
    """Hash ordered JSONB business rows; validation timestamps do not change identity."""
    digest = hashlib.sha256()
    for value in [POLICY, code_hash, json.dumps(source, sort_keys=True), *rows]:
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def test_candidate(run_id: UUID, timeout: int) -> tuple[dict, str]:
    """Run dbt in a fresh artifact directory; never reuse a previous run_results file."""
    code_hash = project_digest(ROOT / "dbt")
    target = ROOT / "artifacts" / "publication" / str(run_id)
    target.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, str(ROOT / "scripts/run_dbt.py"), "test",
               "--vars", "{compare_legacy: false}", "--no-partial-parse",
               "--target-path", str(target / "target"), "--log-path", str(target / "logs")]
    LOGGER.info("Running fresh dbt tests; source and candidate relations are locked against writes.")
    subprocess.run(command, check=True, timeout=timeout, cwd=ROOT)
    manifest = json.loads((target / "target/manifest.json").read_text(encoding="utf-8"))
    results_bytes = (target / "target/run_results.json").read_bytes()
    evidence = validate_evidence(manifest, json.loads(results_bytes))
    if project_digest(ROOT / "dbt") != code_hash:
        raise ValueError("dbt code changed while tests were running.")
    evidence.update(policy=POLICY, code_sha256=code_hash,
                    run_results_sha256=hashlib.sha256(results_bytes).hexdigest(),
                    artifact_directory=str(target.relative_to(ROOT)))
    return evidence, code_hash


def settings() -> dict:
    """Use a dedicated publication role, never the administrative password."""
    password = os.getenv("PG_PUBLISHER_PASSWORD")
    if not password:
        raise ValueError("Set PG_PUBLISHER_PASSWORD in the project .env.")
    return dict(host=os.getenv("DBT_HOST", "127.0.0.1"),
                port=int(os.getenv("DBT_PORT", os.getenv("POSTGRES_PORT", "5433"))),
                dbname=os.getenv("DBT_DATABASE", os.getenv("POSTGRES_DB", "retail_analytics")),
                user="retail_publisher", password=password, connect_timeout=15,
                application_name="retail_publication")


def lock_candidate(cur) -> None:
    """Freeze both data and view definitions while a separate dbt session reads them.

    SHARE locks block writes and rebuilds but permit SELECT. READ COMMITTED is
    intentional: reads occur after locks are acquired, including any writer that
    committed before the locks became available. One transaction retains the locks.
    """
    from psycopg2 import sql
    cur.execute("LOCK TABLE staging.iowa_sales_exact, ops.pg_loaded_exports IN SHARE MODE")
    # ACCESS SHARE locks protect view definitions; their owners only need SELECT
    # on underlying relations. Strong data locks are acquired on physical tables.
    for name in MODEL_NAMES:
        cur.execute(sql.SQL("LOCK TABLE {} IN ACCESS SHARE MODE").format(sql.Identifier("dbt_dev", name)))
    for name in ("fact_sales", "dim_store", "dim_product", "dim_date", "sales_monthly"):
        cur.execute(sql.SQL("LOCK TABLE {} IN SHARE MODE").format(sql.Identifier("dbt_dev", name)))


def contract_columns(cur) -> list[str]:
    """Require the exact public column names, order and PostgreSQL types before copying."""
    def columns(schema, relation):
        cur.execute("""SELECT a.attname, format_type(a.atttypid,a.atttypmod)
            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=%s AND c.relname=%s AND a.attnum>0 AND NOT a.attisdropped
            ORDER BY a.attnum""", (schema, relation))
        return cur.fetchall()
    expected = columns("publication", "monthly_snapshots")[1:]
    actual = columns("dbt_dev", "bi_sales_monthly")
    if len(expected) != 41 or actual != expected:
        raise ValueError("The candidate no longer matches the 41-column BI contract.")
    return [name for name, _ in expected]


def publish(cur, run_id: UUID, timeout: int) -> dict:
    from psycopg2 import sql
    from psycopg2.extras import Json
    lock_candidate(cur)
    require_current_build(cur, project_digest(ROOT / 'dbt'))
    columns = contract_columns(cur)
    evidence, code_hash = test_candidate(run_id, timeout)
    cur.execute("""SELECT source_sha256, summary_sha256, expected_rows, run_id::text
        FROM ops.pg_loaded_exports WHERE target_table='staging.iowa_sales_exact' AND mode='full'""")
    registered = cur.fetchone()
    if registered is None:
        raise ValueError("The source must have a completed full-export load registry entry.")
    source = dict(zip(("export_sha256", "summary_sha256", "expected_rows", "load_run_id"), registered))
    cur.execute("SELECT COUNT(*) FROM dbt_dev.fact_sales")
    if cur.fetchone()[0] != source["expected_rows"]:
        raise ValueError("Fact count differs from the registered source export.")
    cur.execute("""SELECT (to_jsonb(v)-'kpi_snapshot_validated_at')::text
        FROM dbt_dev.bi_sales_monthly v ORDER BY month_start""")
    rows = [row[0] for row in cur.fetchall()]
    if not rows:
        raise ValueError("Cannot publish an empty monthly snapshot.")
    fingerprint = snapshot_fingerprint(source, code_hash, rows)
    cur.execute("""SELECT c.snapshot_id::text, s.fingerprint FROM publication.current_snapshot c
        JOIN publication.snapshots s USING(snapshot_id) WHERE c.singleton""")
    previous, old_hash = cur.fetchone()
    if old_hash == fingerprint:
        return dict(state="UNCHANGED", snapshot_id=previous, previous_snapshot_id=previous, evidence=evidence)
    snapshot_id, validated_at = str(uuid4()), datetime.now(timezone.utc)
    cur.execute("""INSERT INTO publication.snapshots
        (snapshot_id,created_at,kind,fingerprint,source_identity,evidence,month_count)
        VALUES (%s,%s,'DBT_VALIDATED',%s,%s,%s,%s)""",
        (snapshot_id, validated_at, fingerprint, Json(source), Json(evidence), len(rows)))
    # Copy the validated projection into independent storage. Future dbt rebuilds
    # cannot change a report that was already published.
    expressions = [sql.Placeholder() if name == "kpi_snapshot_validated_at"
                   else sql.Identifier("v", name) for name in columns]
    cur.execute(sql.SQL("INSERT INTO publication.monthly_snapshots SELECT %s, {} FROM dbt_dev.bi_sales_monthly v")
                .format(sql.SQL(", ").join(expressions)), (snapshot_id, validated_at))
    if cur.rowcount != len(rows):
        raise ValueError("Copied monthly row count differs from the tested candidate.")
    cur.execute("""UPDATE publication.current_snapshot SET snapshot_id=%s,
        switched_at=clock_timestamp() WHERE singleton""", (snapshot_id,))
    if cur.rowcount != 1:
        raise ValueError("Expected exactly one publication pointer.")
    return dict(state="PUBLISHED", snapshot_id=snapshot_id, previous_snapshot_id=previous, evidence=evidence)


def rollback_snapshot(cur, snapshot_id: UUID, reason: str) -> dict:
    """Switch to an existing retained snapshot; never rebuild or mutate its rows."""
    cur.execute("SELECT snapshot_id::text FROM publication.current_snapshot WHERE singleton")
    previous = cur.fetchone()[0]
    cur.execute("SELECT month_count FROM publication.snapshots WHERE snapshot_id=%s", (str(snapshot_id),))
    row = cur.fetchone()
    if row is None:
        raise ValueError("Unknown retained snapshot ID.")
    cur.execute("SELECT COUNT(*) FROM publication.monthly_snapshots WHERE _snapshot_id=%s", (str(snapshot_id),))
    if cur.fetchone()[0] != row[0]:
        raise ValueError("Retained snapshot row count no longer matches its metadata.")
    cur.execute("""UPDATE publication.current_snapshot SET snapshot_id=%s,
        switched_at=clock_timestamp() WHERE singleton""", (str(snapshot_id),))
    return dict(state="ROLLED_BACK", snapshot_id=str(snapshot_id), previous_snapshot_id=previous,
                evidence={"reason": reason})


def redact(message: str) -> str:
    for key in ("PG_PUBLISHER_PASSWORD", "DBT_ENV_SECRET_PASSWORD", "POSTGRES_PASSWORD", "PG_LOADER_PASSWORD", "PG_SNAPSHOT_PASSWORD"):
        secret = os.getenv(key)
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message[:2000]


def main() -> int:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("publish")
    run.add_argument("--test-timeout", type=int, default=7200, help="Maximum test duration in seconds.")
    commands.add_parser("status")
    restore = commands.add_parser("rollback")
    restore.add_argument("--snapshot", type=UUID, required=True)
    restore.add_argument("--reason", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    connection = None
    run_id = None
    try:
        if args.action == "publish" and args.test_timeout <= 0:
            raise ValueError("--test-timeout must be positive.")
        connection = psycopg2.connect(**settings())
        connection.autocommit = True
        if args.action == "status":
            with connection.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT s.*, (s.snapshot_id=c.snapshot_id) AS is_current
                    FROM publication.snapshots s CROSS JOIN publication.current_snapshot c
                    ORDER BY s.created_at DESC LIMIT 20""")
                snapshots = cur.fetchall()
                cur.execute("SELECT * FROM publication.runs ORDER BY started_at DESC LIMIT 10")
                print(json.dumps({"snapshots": snapshots, "recent_runs": cur.fetchall()}, indent=2, default=str))
            return 0
        run_id = str(uuid4())
        with connection.cursor() as cur:
            cur.execute("INSERT INTO publication.runs(run_id,action,state) VALUES(%s,%s,'RUNNING')",
                        (run_id, args.action.upper()))
        with connection.cursor() as cur:
            acquire_lock(cur, shared=True)
        connection.autocommit = False
        with connection.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='5s'")
            cur.execute("SELECT pg_try_advisory_xact_lock(%s)", (LOCK_KEY,))
            if not cur.fetchone()[0]:
                raise ValueError("Another publication is running; retry after it finishes.")
            cur.execute("SELECT snapshot_id FROM publication.current_snapshot WHERE singleton FOR UPDATE")
            if cur.fetchone() is None:
                raise ValueError("Publication pointer is missing.")
            result = (publish(cur, UUID(run_id), args.test_timeout) if args.action == "publish"
                      else rollback_snapshot(cur, args.snapshot, args.reason))
            cur.execute("""UPDATE publication.runs SET state=%s, finished_at=clock_timestamp(),
                snapshot_id=%s, previous_snapshot_id=%s, details=%s WHERE run_id=%s""",
                (result["state"], result["snapshot_id"], result["previous_snapshot_id"], Json(result["evidence"]), run_id))
        connection.commit()
        print(json.dumps({"run_id": run_id, **result}, indent=2))
        return 0
    except BaseException as exc:
        message = redact(f"{type(exc).__name__}: {exc}")
        if connection is not None:
            try:
                connection.rollback()
                connection.autocommit = True
                if run_id:
                    with connection.cursor() as cur:
                        cur.execute("""UPDATE publication.runs SET state='FAILED',
                            finished_at=clock_timestamp(),error_message=%s WHERE run_id=%s AND state='RUNNING'""",
                            (message, run_id))
            except Exception:
                LOGGER.error("Could not record failure; inspect current_snapshot and runs before retrying.")
        LOGGER.error("%s", message)
        return 130 if isinstance(exc, KeyboardInterrupt) else 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())

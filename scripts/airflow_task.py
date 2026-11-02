"""Adapt the existing CLIs to one durable, run-specific bundle receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys

from snapshot_ingestion import ROOT, atomic_json, load, prepare

CACHE = ROOT / "artifacts" / "snapshots"


def run_directory():
    # Airflow run IDs can contain punctuation. Never use a raw run ID as a path.
    run_id = os.environ["RDI_RUN_ID"]
    directory = ROOT / "artifacts" / "airflow" / hashlib.sha256(run_id.encode()).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    return run_id, directory


def execute(step):
    run_id, directory = run_directory()
    if step == "report":
        from airflow_reporting import report
        return report(run_id,directory)
    receipt = directory / "bundle.json"
    if step == "prepare" and not receipt.exists():
        result = prepare(ROOT / "data" / "raw", CACHE)
        bundle = Path(result["bundle"])
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        atomic_json(receipt, {"run_id": run_id, "bundle_id": bundle.name,
                              "export_sha256": manifest["export_sha256"],
                              "summary_sha256": manifest["summary_sha256"], "rows": manifest["rows"]})
        print(json.dumps(result))
    pin = json.loads(receipt.read_text(encoding="utf-8"))
    if pin["run_id"] != run_id or not re.fullmatch(r"[a-f0-9]{64}", pin["bundle_id"]):
        raise ValueError("Invalid bundle receipt for this DAG run.")
    bundle = CACHE / pin["bundle_id"]
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if any(pin[k] != manifest[k] for k in ("bundle_id", "export_sha256", "summary_sha256", "rows")):
        raise ValueError("Prepared manifest differs from the run receipt.")
    print(f"run={run_id} bundle={bundle.name} rows={pin['rows']}", flush=True)
    if step == "prepare":
        return
    if step == "load":
        # The loader revalidates the export. Never auto-accept removals or row decreases.
        result = load(bundle)
        atomic_json(directory / "load.json", {"state": result["state"], "run_id": str(result["run_id"]),
                                             "bundle_id": result["bundle_id"], "rows": result["rows"]})
        print(json.dumps(result, default=str))
        return
    for field in ("export_sha256", "summary_sha256"):
        os.environ["RDI_EXPECTED_" + field.upper()] = pin[field]
    os.environ["DBT_TARGET_PATH"] = str(directory / "target")
    os.environ["DBT_LOG_PATH"] = str(directory / "logs")
    if step == "publish":
        from airflow_reporting import publish
        return publish(run_id,directory,pin["bundle_id"])
    script, command = ("run_dbt.py", "build") if step == "dbt_build" else ("publish_snapshot.py", "publish")
    # Replace this process so task cancellation and exit status reach the existing CLI.
    os.execv(sys.executable, [sys.executable, str(ROOT / "scripts" / script), command])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("prepare", "load", "dbt_build", "publish", "report"))
    logging.basicConfig(level=logging.INFO)
    execute(parser.parse_args().step)

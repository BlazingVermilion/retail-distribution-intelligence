"""Initialize local-only Airflow settings without changing any existing credentials."""
import base64
import re
import secrets
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    required = ("compose.yaml", "requirements-snapshots.txt", "requirements-dbt.txt",
                "requirements-publication.txt", "scripts/snapshot_ingestion.py",
                "scripts/load_postgres.py", "scripts/audit_duplicates.py", "scripts/run_dbt.py",
                "scripts/publish_snapshot.py", "scripts/warehouse_state.py", "dbt/profiles.yml")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise SystemExit("Missing prerequisites: " + ", ".join(missing))
    env = root / ".env"
    original = env.read_text(encoding="utf-8-sig")
    existing = set(re.findall(r"^\s*(?:export\s+)?([A-Za-z_]\w*)\s*=", original, re.M))
    values = {key: secrets.token_hex(32) for key in ("RDI_AF_DB_PASS", "RDI_AF_API_KEY", "RDI_AF_JWT")}
    values["RDI_AF_FERNET"] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    additions = [f"{k}={v}" for k,v in values.items() if k not in existing]
    if additions:
        # Preserve the original bytes and encoding. Only new ASCII settings are appended.
        with env.open("ab") as handle:
            handle.write(("\n# Local Airflow settings. Do not commit.\n" + "\n".join(additions) + "\n").encode("ascii"))
    (root / "artifacts").mkdir(exist_ok=True)
    print(f"Local Airflow settings ready ({len(additions)} added).")


if __name__ == "__main__":
    main()

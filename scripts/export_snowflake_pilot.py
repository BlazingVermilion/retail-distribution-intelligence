"""Export one PostgreSQL reference slice. No cloud credentials or extra Python packages."""
import csv
from decimal import Decimal
import hashlib
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "snowflake" / "2026-09"
COLS = ["audit_id", "ordered_on", "store_no", "bottles", "dollars", "liters"]
# The reconciled view preserves reported measures. Exclude calculated replacements.
QUERY = """COPY (SELECT _audit_row_id AS audit_id, ordered_on, store_no,
    sales_bottles AS bottles, reported_sales_dollars AS dollars, reported_sales_liters AS liters
    FROM staging.iowa_sales_reconciled WHERE ordered_on >= DATE '2026-09-01'
    AND ordered_on < DATE '2026-10-01' ORDER BY _audit_row_id)
    TO STDOUT WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8')"""


def reference(path):
    ids, stores, totals, counts = set(), set(), [Decimal(0)] * 3, [0] * 3
    with path.open(encoding="utf-8", newline="") as source:
        rows = csv.DictReader(source)
        if rows.fieldnames != COLS:
            raise ValueError("Unexpected PostgreSQL export header.")
        for row in rows:
            ident = int(row["audit_id"])
            if ident in ids or not row["ordered_on"].startswith("2026-09-"):
                raise ValueError("Duplicate audit ID or unexpected month.")
            ids.add(ident)
            if row["store_no"]:
                stores.add(row["store_no"])
            for i, field in enumerate(COLS[3:]):
                if row[field] != "":
                    value = Decimal(row[field])
                    if not value.is_finite() or value.as_tuple().exponent < -12 or abs(value) >= Decimal("1e18"):
                        raise ValueError(f"Value exceeds pilot precision contract: {field}")
                    totals[i] += value
                    counts[i] += 1
    if not ids:
        raise ValueError("The reference month is empty.")
    return [len(ids), len(ids), len(stores), *counts, *(format(v, "f") if n else "NULL" for v,n in zip(totals, counts))]


def main():
    from decimal import getcontext
    getcontext().prec = 50
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=OUT) as tmp:
        export = Path(tmp) / "iowa_2026_09.csv"
        # Stream bytes directly: Windows PowerShell redirection may change CSV encoding.
        with export.open("wb") as f:
            subprocess.run(["docker","compose","exec","-T","postgres","psql","-X","-q",
                            "-U","postgres","-d","retail_analytics","-v","ON_ERROR_STOP=1",
                            "-c",QUERY], cwd=ROOT, stdout=f, check=True)
        expected = reference(export)
        digest = hashlib.sha256(export.read_bytes()).hexdigest()
        # Embed only validated numeric literals; no store names or other source text enters SQL.
        names = ["rows_n","unique_ids","stores","bottles_n","dollars_n","liters_n","bottles_sum","dollars_sum","liters_sum"]
        expressions = ["COUNT(*)","COUNT(DISTINCT audit_id)","COUNT(DISTINCT store_no)",
                       "COUNT(bottles)","COUNT(dollars)","COUNT(liters)","SUM(bottles)","SUM(dollars)","SUM(liters)"]
        actual = ", ".join(f"{expr} AS {name}" for name,expr in zip(names,expressions))
        want = ", ".join(f"{v} AS {name}" for name,v in zip(names,expected))
        checks = " AND ".join(f"EQUAL_NULL(a.{n}, e.{n})" for n in names)
        sql = (f"-- PostgreSQL reference CSV SHA-256: {digest}\nWITH a AS (SELECT {actual} FROM RDI_PILOT_DB.PILOT.IOWA_SEP_2026),\n"
               f"e AS (SELECT {want})\nSELECT IFF({checks}, 'PASS', 'FAIL') AS parity, "
               "OBJECT_CONSTRUCT_KEEP_NULL(a.*) AS actual, OBJECT_CONSTRUCT_KEEP_NULL(e.*) AS expected FROM a CROSS JOIN e;\n")
        (OUT/"003_compare.sql").write_text(sql, encoding="utf-8")
        export.replace(OUT/export.name)
    print("Reference:", dict(zip(names, expected)))
    print("CSV SHA-256:", digest)
    print("Files:", OUT)


if __name__ == "__main__":
    main()

# Getting started

## 1. Open the checkout

Clone the repository or extract its source archive. Open the repository root (the directory containing compose.yaml) in your editor.

## 2. Check Python

```bash
python --version
```

Python 3.11+ is required. On Windows, use `py -3` instead of `python` if that is how Python is installed.

## 3. Run the offline fixture

```bash
python scripts/inspect_snapshot.py --year 2026 --files data/fixtures/transactions.csv --output artifacts/demo-manifest.json
python -m unittest discover -s tests -v
```

The fixture is synthetic. It deliberately includes a repeated row, leading-zero codes, a negative adjustment, and a missing price. Inspection preserves these records; numeric business rules belong to later quality checks.

## 4. Add real exports locally

Create `data/raw/2025` and `data/raw/2026`. These directories are ignored by Git. Extract ZIPs with your operating system. Keep original CSV bytes; do not open and re-save through Excel. Use explicit filenames, not a wildcard that could include duplicate downloads.

For 2025 use parts 1–4. Do not include part 5. Rename local copies to consistent names if convenient; renaming does not change their bytes. Put the complete list of selected paths after `--files`.

```bash
python scripts/inspect_snapshot.py --year 2025 --files data/raw/2025/part_0001.csv data/raw/2025/part_0002.csv data/raw/2025/part_0003.csv data/raw/2025/part_0004.csv --output artifacts/2025-manifest.json
```

This command assumes you assigned those four local names. Outputs contain filenames and checksums, not source rows. The inspector will not infer completeness from part numbers or min/max dates.

## 5. Interpret the result

Exit code 0: file structure and present primitive values passed the implemented checks. Missing cells are counted, not automatically rejected. Repeated content files are rejected. A header mismatch, malformed row, invalid date, non-finite number, or out-of-year date returns exit code 2.

This is not a data-quality pass for all KPIs. Read `docs/quality_policy.md` before presenting any business result.

## 6. Continue to the full pipeline

See the [implemented stack and installation guides](../README.md#explore-or-reproduce). For a fresh local installation, copy .env.example to .env and fill in distinct credentials. Do not overwrite an existing .env.

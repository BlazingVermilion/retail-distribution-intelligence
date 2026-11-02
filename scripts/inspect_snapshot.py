"""Inspect explicitly selected CSV files without uploading or modifying them."""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from retail_platform.ingestion.manifest import inspect_snapshot, write_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, required=True)
    parser.add_argument('--files', nargs='+', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    schema_path = ROOT / 'configs/source_schema.json'
    try:
        schema = json.loads(schema_path.read_text(encoding='utf-8'))
        manifest = inspect_snapshot(args.files, args.year, schema)
        write_manifest(manifest, args.output, [*args.files, schema_path])
    except (ValueError, OSError, csv.Error) as exc:
        parser.exit(2, f'Inspection failed: {exc}\n')
    print(f"Inspected {manifest['row_count']:,} rows; manifest: {args.output}")
    print('Business quality and publication eligibility have not been evaluated.')


if __name__ == '__main__':
    main()

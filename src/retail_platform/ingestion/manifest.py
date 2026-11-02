"""Streaming structural inspection; not a business-metric publication gate."""
import csv
import hashlib
import json
import os
import re
import tempfile
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def inspect_snapshot(paths, year, schema):
    if not paths:
        raise ValueError('At least one input CSV is required.')
    names = [column['name'] for column in schema]
    files, seen = [], set()
    for path in map(Path, paths):
        checksum = digest(path)
        if checksum in seen:
            raise ValueError(f'Duplicate file content: {path.name}')
        seen.add(checksum)
        missing = dict.fromkeys(names, 0)
        count, first, last = 0, None, None
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.reader(stream, strict=True)
            if next(reader, None) != names:
                raise ValueError(f'Header mismatch: {path.name}')
            for count, row in enumerate(reader, 1):
                if len(row) != len(names):
                    raise ValueError(f'{path.name}: record {count}: wrong field count')
                for column, value in zip(schema, row):
                    name, kind = column['name'], column['type']
                    if not value.strip():
                        missing[name] += 1
                        continue
                    try:
                        if kind == 'DATE':
                            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                                raise ValueError('Expected ISO date')
                            day = date.fromisoformat(value)
                            if day.year != year:
                                raise ValueError('Date outside declared year')
                            first = day if first is None else min(first, day)
                            last = day if last is None else max(last, day)
                        elif kind == 'INTEGER':
                            if not re.fullmatch(r'[+-]?\d+', value):
                                raise ValueError('Expected integer')
                        elif kind == 'FLOAT':
                            if not Decimal(value).is_finite():
                                raise ValueError('Expected finite decimal')
                        elif kind != 'STRING':
                            raise ValueError('Unsupported source type')
                    except (ValueError, InvalidOperation) as exc:
                        raise ValueError(f'{path.name}: record {count}: invalid {name}: {exc}') from exc
        if digest(path) != checksum:
            raise ValueError(f'Input changed during inspection: {path.name}')
        files.append({'file_name': path.name, 'file_id': checksum, 'sha256': checksum,
                      'size_bytes': path.stat().st_size, 'row_count': count,
                      'min_date': first.isoformat() if first else None,
                      'max_date': last.isoformat() if last else None,
                      'missing_by_column': missing})
    identity = json.dumps({'source': 'iowa_liquor_sales', 'year': year,
                           'files': sorted(seen)}, sort_keys=True).encode()
    return {'manifest_version': 1, 'source': 'iowa_liquor_sales', 'year': year,
            'snapshot_id': hashlib.sha256(identity).hexdigest(),
            'schema_sha256': hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest(),
            'row_count': sum(f['row_count'] for f in files), 'files': files,
            'structural_status': 'passed', 'publication_status': 'not_evaluated',
            'warnings': ['Missing fields are counted, not rejected.',
                         'Identical records are preserved. Cross-file row overlap is not evaluated.',
                         'Passing structural checks does not authorize metric publication.']}


def write_manifest(manifest, output, protected_paths=()):
    output = Path(output)
    if output.resolve() in {Path(p).resolve() for p in protected_paths}:
        raise ValueError('Output must not overwrite an input or schema.')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(manifest, stream, indent=2)
            stream.write('\n')
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()

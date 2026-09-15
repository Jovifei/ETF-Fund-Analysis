"""Optional DuckDB Parquet adapter; local private files only, fixed SQL projections.

DuckDB is loaded only on an explicit archive command. No extension installation,
URL, user SQL, glob, database connection or production service is accepted.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path

from app.workspace.archive_protocol import FIELDS, canonical, validate_request, validate_rows
from app.workspace.archive_store import bounded_read, private_path

COLUMNS = ('ts_code','date','open','high','low','close','volume','amount','source','adjust')


def connection():
    import duckdb
    return duckdb.connect(':memory:', config={'threads':'1','memory_limit':'128MB',
        'temp_directory':'','autoinstall_known_extensions':'false','autoload_known_extensions':'false'})


def _private_created(path, *, directory=False):
    if os.name == 'nt':
        from app.workspace.bridge_runtime import windows_private_directory
        windows_private_directory(path, created=True, directory=directory)
    else:
        path.chmod(0o700 if directory else 0o600)


def write(root: Path, archive_id: str, request: dict, rows: list, *, now=None):
    import re
    validate_request(request, now=now)
    rows = validate_rows(request, rows)
    root = private_path(root, directory=True)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', archive_id):
        raise ValueError('archive_id_invalid')
    directory = root / archive_id
    directory.mkdir(mode=0o700, exist_ok=False)
    _private_created(directory, directory=True)
    target = directory / 'history.parquet'
    # An interrupted export has no final manifest and is never readable.
    with connection() as conn:
        conn.execute('CREATE TABLE bars(ts_code VARCHAR, date VARCHAR, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE, amount DOUBLE, source VARCHAR, adjust VARCHAR)')
        if rows:
            conn.executemany('INSERT INTO bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                             [[row[key] for key in COLUMNS] for row in rows])
        conn.execute("COPY (SELECT * FROM bars ORDER BY date) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(target)])
    _private_created(target)
    digest = hashlib.sha256(bounded_read(target, 16*1024*1024)).hexdigest()
    meta = {'schema_version':'local-parquet-v1','file':target.name,'sha256':digest,
            'row_count':len(rows),'request':request,'qualification':'not_asserted'}
    path = directory / 'manifest.json'
    with path.open('xb') as stream:
        stream.write(canonical(meta))
    _private_created(path)
    return meta


def read(root: Path, archive_id: str, request: dict, *, now=None):
    import re
    from app.workspace.archive_protocol import decode
    validate_request(request, now=now)
    root = private_path(root, directory=True)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', archive_id):
        raise ValueError('archive_id_invalid')
    directory = private_path(root / archive_id, directory=True)
    meta = decode(bounded_read(directory / 'manifest.json', 128*1024))
    if not isinstance(meta, dict) or meta.get('schema_version') != 'local-parquet-v1' or meta.get('file') != 'history.parquet':
        raise ValueError('unsupported_local_parquet')
    path = private_path(directory / 'history.parquet')
    if hashlib.sha256(bounded_read(path, 16*1024*1024)).hexdigest() != meta.get('sha256'):
        raise ValueError('local_archive_hash_mismatch')
    # Values and file path are bound parameters, never interpolated user SQL.
    with connection() as conn:
        values = conn.execute('SELECT ts_code,date,open,high,low,close,volume,amount,source,adjust '
            'FROM read_parquet(?) WHERE ts_code=? AND date>=? AND date<=? AND adjust=? '
            'ORDER BY date LIMIT ?', [str(path),request['ts_code'],request['start'],request['end'],
                                    request['adjust'],request['max_rows']+1]).fetchall()
    return validate_rows(request, [dict(zip(COLUMNS, row)) for row in values])

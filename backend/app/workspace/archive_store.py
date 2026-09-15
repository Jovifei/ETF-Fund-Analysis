"""Private local archive reader. No network, DB, live-file sync or deletion."""
from __future__ import annotations
import gzip
import hashlib
import io
import os
from pathlib import Path
import re
import stat
import zlib

from app.workspace.archive_protocol import FIELDS, MAX_RAW_BYTES, decode, validate_request, validate_rows


def private_path(path: Path, *, directory=False) -> Path:
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('archive_link_rejected')
    mode = path.stat()
    if (not stat.S_ISDIR(mode.st_mode) if directory else not stat.S_ISREG(mode.st_mode)):
        raise ValueError('archive_regular_private_path_required')
    if os.name == 'nt':
        from app.workspace.bridge_runtime import windows_private_directory
        windows_private_directory(path, created=False, directory=directory)
    elif mode.st_uid != os.getuid() or mode.st_mode & 0o077:
        raise ValueError('archive_permissions_unsafe')
    return path


def bounded_read(path: Path, limit: int) -> bytes:
    private_path(path)
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError('archive_file_limit_exceeded')
    return value


def read_export(root: Path, archive_id: str, request: dict, *, now=None):
    validate_request(request, now=now)
    root = private_path(root, directory=True)
    if not isinstance(archive_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', archive_id):
        raise ValueError('archive_id_invalid')
    directory = private_path(root / archive_id, directory=True)
    manifest = decode(bounded_read(directory / 'manifest.json', 128*1024))
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 'market-history-archive-v1' or manifest.get('file') != 'market-history.jsonl.gz':
        raise ValueError('unsupported_local_export')
    compressed = bounded_read(directory / 'market-history.jsonl.gz', 16*1024*1024)
    if hashlib.sha256(compressed).hexdigest() != manifest.get('sha256'):
        raise ValueError('local_archive_hash_mismatch')
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            raw = stream.read(MAX_RAW_BYTES + 1)
    except (OSError, EOFError, zlib.error):
        raise ValueError('local_archive_compression_invalid') from None
    if len(raw) > MAX_RAW_BYTES:
        raise ValueError('local_archive_uncompressed_limit_exceeded')
    selected = []
    for line in raw.splitlines():
        if len(line) > 2*1024*1024:
            raise ValueError('local_archive_record_limit_exceeded')
        row = decode(line)
        if not isinstance(row, dict):
            raise ValueError('local_archive_record_invalid')
        if row.get('kind') != 'etf_bar':
            continue  # index cache is never confused with the requested ETF
        if set(row) - FIELDS - {'kind','actionable'}:
            raise ValueError('unexpected_local_archive_fields')
        if (row.get('ts_code') == request['ts_code'] and row.get('adjust') == request['adjust']
            and request['start'] <= row.get('date', '') <= request['end']):
            selected.append({key:row.get(key) for key in FIELDS})
        if len(selected) > request['max_rows']:
            raise ValueError('archive_row_limit_exceeded')
    return validate_rows(request, selected)

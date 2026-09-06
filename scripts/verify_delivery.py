#!/usr/bin/env python3
"""Read-only SHA256 verification of the original full-source delivery."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import sys

def verify(root: Path) -> int:
    root = root.resolve()
    manifest = json.loads((root/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    failed = []
    for entry in manifest['files']:
        rel = PurePosixPath(entry['path'])
        if rel.is_absolute() or '..' in rel.parts or '\\' in entry['path']:
            raise ValueError('unsafe manifest path')
        path = root.joinpath(*rel.parts)
        if any(p.is_symlink() for p in (path, *path.parents)):
            failed.append(entry['path']); continue
        if not path.is_file() or path.stat().st_size != entry['bytes']:
            failed.append(entry['path']); continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            failed.append(entry['path'])
    print(f"Verified {len(manifest['files'])} listed files; mismatches: {len(failed)}")
    for name in failed[:30]: print(name)
    print('No database, model, network, installation or repository write was performed.')
    return 1 if failed else 0

if __name__ == '__main__':
    try: raise SystemExit(verify(Path(__file__).resolve().parents[1]))
    except (ValueError, OSError, KeyError):
        print('Missing or invalid delivery manifest.', file=sys.stderr); raise SystemExit(2)

#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SKIP = {'.git', '.venv', 'vendor', 'reports', 'backups', '__pycache__'}
PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|token|password)\s*[:=]\s*["\']?[A-Za-z0-9_\-]{24,}'),
    re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b'),
]
findings = []
for path in ROOT.rglob('*'):
    if not path.is_file() or any(part in SKIP for part in path.parts):
        continue
    if path.name in {'.env', '.env.production'}:
        continue
    try:
        text = path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError):
        continue
    for lineno, line in enumerate(text.splitlines(), 1):
        if 'CHANGE_ME' in line or 'your_' in line.lower() or 'replace_with' in line.lower():
            continue
        if any(pattern.search(line) for pattern in PATTERNS):
            findings.append(f'{path.relative_to(ROOT)}:{lineno}')
if findings:
    print('\n'.join(findings))
    raise SystemExit(2)
print('no obvious committed secrets found')

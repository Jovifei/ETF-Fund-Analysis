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
# These literals are intentionally committed negative-test fixtures.  Keep the
# allowlist narrow and path-scoped so every other token/password/API-key-looking
# value in tests is still scanned normally.
TEST_FIXTURE_LITERALS = (
    'legacy-machine-token-only',
    'legacy-only-machine-token-kept-for-cli-compatibility-1234567890',
    'legacy-market-context-test-token-valid-1234567890',
    'test-only-admin-password',
)


def is_known_test_fixture(path: Path, line: str) -> bool:
    relative = path.relative_to(ROOT)
    return (
        len(relative.parts) >= 2
        and relative.parts[0] == 'backend'
        and relative.parts[1] == 'tests'
        and any(value in line for value in TEST_FIXTURE_LITERALS)
    )


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
        if is_known_test_fixture(path, line):
            continue
        if any(pattern.search(line) for pattern in PATTERNS):
            findings.append(f'{path.relative_to(ROOT)}:{lineno}')
if findings:
    print('\n'.join(findings))
    raise SystemExit(2)
print('no obvious committed secrets found')

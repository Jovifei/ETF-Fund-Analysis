#!/usr/bin/env python3
from __future__ import annotations

import re
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SKIP = {'.git', '.venv', 'vendor', 'reports', 'backups', '__pycache__', 'node_modules', 'workspace_dist', 'test-results', 'playwright-report', 'runner-home', '.codex'}
PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|token|password)\s*[:=]\s*["\']?([A-Za-z0-9_\-]{24,})'),
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
    'test-only-bridge-login-9248',
)


def is_allowed_match(path: Path, line: str, match: re.Match) -> bool:
    # Exempt one candidate value, never an entire line containing other values.
    value = match.group(2) if match.re.groups >= 2 else match.group(0)
    placeholder = value[3:] if value.startswith('sk-') else value
    if re.match(r'(?i)^(?:CHANGE_ME(?:_|$)|your_|replace_with(?:_|$))', placeholder):
        return True
    relative = path.relative_to(ROOT)
    if not (len(relative.parts) >= 2 and relative.parts[:2] == ('backend', 'tests')
            and match.re.groups >= 2 and value in TEST_FIXTURE_LITERALS):
        return False
    start, end = match.span(2)
    quote = line[start - 1:start] if start else ''
    return quote in {"'", '"'} and line[end:end + 1] == quote


def source_files():
    # Prune generated directories before traversal, rather than reading every
    # package file after a frontend install. Runtime credential files stay out.
    for current, dirs, names in os.walk(ROOT):
        dirs[:] = [name for name in dirs if name not in SKIP and not (Path(current).name == 'bridge' and name == 'jobs')]
        for name in names:
            yield Path(current) / name


findings = []
for path in source_files():
    if not path.is_file() or any(part in SKIP for part in path.relative_to(ROOT).parts):
        continue
    if path.name in {'.env', '.env.production', '.env.local', 'workspace.env', 'device.secret'}:
        continue
    try:
        text = path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError):
        continue
    for lineno, line in enumerate(text.splitlines(), 1):
        if any(not is_allowed_match(path, line, match)
               for pattern in PATTERNS for match in pattern.finditer(line)):
            findings.append(f'{path.relative_to(ROOT)}:{lineno}')
if findings:
    print('\n'.join(findings))
    raise SystemExit(2)
print('no obvious committed secrets found')

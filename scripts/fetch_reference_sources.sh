#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p vendor/src

include_personal=false
case "${1:-}" in
  "") ;;
  --include-personal-use) include_personal=true ;;
  *) echo "Usage: $0 [--include-personal-use]" >&2; exit 2 ;;
esac

INCLUDE_PERSONAL_USE="$include_personal" python - <<'PY'
import json
import os
import shutil
import subprocess
from pathlib import Path

manifest = json.loads(Path('vendor/manifest.json').read_text(encoding='utf-8'))
root = Path('vendor/src')
include_personal = os.environ.get('INCLUDE_PERSONAL_USE') == 'true'

for item in manifest['repositories']:
    name = item['name']
    if item.get('credential_history_risk'):
        print(f"BLOCK {name}: {item.get('risk', 'credential-history risk')}")
        continue
    allowed = bool(item.get('auto_fetch')) or (include_personal and item.get('personal_use_fetch'))
    if not allowed:
        reason = item.get('risk') or 'manual review / explicit opt-in required'
        print(f"SKIP {name}: {reason}")
        continue

    target = root / name
    if target.exists():
        print(f"EXISTS {target}; remove it to fetch again")
        continue

    try:
        subprocess.run(
            ['git', 'clone', '--filter=blob:none', '--no-checkout', '--depth', '1', item['repo'], str(target)],
            check=True,
        )
        subprocess.run(['git', '-C', str(target), 'fetch', '--depth', '1', 'origin', item['ref']], check=True)
        subprocess.run(['git', '-C', str(target), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
        resolved = subprocess.check_output(['git', '-C', str(target), 'rev-parse', 'HEAD'], text=True).strip()
        if resolved != item['ref']:
            raise RuntimeError(f"revision mismatch: expected {item['ref']}, got {resolved}")
        print(f"FETCHED {name} @ {resolved} ({item.get('license', 'license unknown')})")
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
PY

echo "Reference sources are isolated under vendor/src, excluded from Git/Docker, and are not imported by the application."

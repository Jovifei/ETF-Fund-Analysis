#!/usr/bin/env python3
"""Export selected native Vibe artifacts. Never calls an agent or sends data."""
from __future__ import annotations
import argparse
from datetime import datetime
from pathlib import Path
import sys

# Use this project's validated contracts, not the Vibe runtime's dependencies.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.workspace.external_research import packet_from_directory
from app.workspace.protocol import canonical_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kind', choices=['etf','daily'], required=True)
    parser.add_argument('--ts-code')
    parser.add_argument('--source-as-of', required=True, help='Explicit ISO timestamp with timezone; never infer from file mtime')
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--producer-version', required=True, help='Verified upstream commit or release')
    parser.add_argument('--model', required=True, help='Actual model reported by the run, or unverified')
    parser.add_argument('--upstream-status', choices=['complete','incomplete','stale'], required=True)
    parser.add_argument('--confirm-public-data', action='store_true')
    args = parser.parse_args()
    if not args.confirm_public_data:
        parser.error('Review the five selected files for credentials and private data; --confirm-public-data is required.')
    try:
        packet = packet_from_directory(args.run_directory, kind=args.kind,ts_code=args.ts_code,
            source_as_of=datetime.fromisoformat(args.source_as_of),run_id=args.run_id,
            producer_version=args.producer_version,model=args.model,upstream_status=args.upstream_status)
        # Exclusive creation: no destructive overwrite or symlink following.
        with args.output.open('xb') as output:
            output.write(canonical_bytes(packet.model_dump(mode='json')))
        print(f'Created external candidate packet; sha256={packet.digest()}; model_called=false')
        return 0
    except (ValueError, OSError) as exc:
        print(f'Export rejected ({type(exc).__name__}). Check file bounds, source time, privacy and output path.',file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())

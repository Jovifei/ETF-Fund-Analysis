#!/usr/bin/env python3
"""Deploy-time gate: the ECS consumer identity must be an approved producer.

Run before switching a release (see docs/BUNDLE_IDENTITY_AND_WEEKEND_RUNBOOK.md):

    python scripts/check_bundle_identity.py \
        --code-sha "$SHADOW_SYNC_CODE_SHA" --config-hash "$SHADOW_SYNC_CONFIG_HASH"

Exit 0 = approved producer; exit 1 = unregistered (do not treat an empty website as a
data problem before fixing the identity expectation).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.workspace.bundle_identity import check_expected_identity  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify an approved local-display producer identity")
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--config-hash", required=True)
    parser.add_argument("--registry", default=None, help="Override registry path")
    args = parser.parse_args(argv)
    result = check_expected_identity(args.code_sha, args.config_hash, path=args.registry)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "approved" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Evaluate sanitized observer captures without SSH, credentials or DB access."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.workspace.local_stability import assess_session, record_stability, summarize_stability


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate observation field")
        value[key] = item
    return value


def _read(path: str) -> dict:
    source = Path(path)
    if source.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("observation input exceeds 16 MiB")
    value = json.loads(source.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite observation")))
    if not isinstance(value, dict):
        raise ValueError("observation object required")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--session")
    for name in ("ledger", "cloud-before", "cloud-after", "runtime-before", "runtime-after",
                 "expected-source-sha", "expected-config-hash", "expected-image-id", "expected-scope-hash"):
        parser.add_argument("--" + name)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve(strict=True)
    if not (root / ".local-live").is_file():
        parser.error("owned .local-live root required")
    if args.summary:
        report = summarize_stability(root)
    else:
        required = ("session", "ledger", "cloud_before", "cloud_after", "runtime_before", "runtime_after",
                    "expected_source_sha", "expected_config_hash", "expected_image_id")
        if any(not getattr(args, key) for key in required):
            parser.error("session, ledger, both cloud/runtime captures and exact expected identities are required")
        report = assess_session(
            session=date.fromisoformat(args.session), ledger_summary=_read(args.ledger),
            cloud_before=_read(args.cloud_before), cloud_after=_read(args.cloud_after),
            runtime_before=_read(args.runtime_before), runtime_after=_read(args.runtime_after),
            expected_source_sha=args.expected_source_sha, expected_config_hash=args.expected_config_hash,
            expected_image_id=args.expected_image_id, expected_scope_hash=args.expected_scope_hash)
        record_stability(root, report)
    print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    return 0 if report["state"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, TypeError, KeyError):
        # Do not echo raw input, paths or nested provider/credential values.
        print(json.dumps({"state": "UNKNOWN", "reason": "invalid_or_unavailable_observation"}))
        raise SystemExit(2)

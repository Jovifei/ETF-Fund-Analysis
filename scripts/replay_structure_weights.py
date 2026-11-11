#!/usr/bin/env python3
"""Read a supplied offline dataset and write an isolated review artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.research.structure_weight_replay import ReplayError, build_report, write_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="New directory only; existing paths are never replaced"
    )
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    args = parser.parse_args()
    try:
        if args.input.stat().st_size > 128 * 1024 * 1024:
            raise ReplayError("input_exceeds_128_MiB")
        data = json.loads(args.input.read_text(encoding="utf-8"))
        config_hash = hashlib.sha256((ROOT / "config" / "strategy.json").read_bytes()).hexdigest()
        report = build_report(
            data, expected_config_hash=config_hash, bootstrap_samples=args.bootstrap_samples
        )
        write_report(report, args.output)
    except (ReplayError, OSError, json.JSONDecodeError) as exc:
        print(
            json.dumps({"status": "blocked", "error": str(exc), "actionable": False}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(args.output),
                "portfolio_blockers": report["integrity"]["portfolio_blockers"],
                "final_oos_validated": False,
                "promotion_allowed": False,
            },
            ensure_ascii=False,
        )
    )
    return 2 if report["status"] == "signal_only" else 0


if __name__ == "__main__":
    raise SystemExit(main())

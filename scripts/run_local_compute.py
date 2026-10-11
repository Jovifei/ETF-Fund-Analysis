#!/usr/bin/env python3
"""CLI for local deterministic compute and export."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.workspace.local_compute import (
    compute_local,
    doctor_check,
    export_local_v2,
    local_settings,
)
from app.workspace.local_schedule import LocalRunLock


def get_current_git_sha() -> str:
    import subprocess
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "0" * 40


def cmd_doctor(args: argparse.Namespace) -> int:
    root = Path(args.root)
    database = Path(args.db) if args.db else root / "db" / "research.sqlite3"
    result = doctor_check(root, database, profile=args.profile)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if (result.get("root_exists") and result.get("disk_sufficient")) else 1


def cmd_run(args: argparse.Namespace) -> int:
    root = Path(args.root)
    database = Path(args.db) if args.db else root / "db" / "research.sqlite3"
    lock = LocalRunLock(root / ".run.lock")
    if not lock.acquire():
        print(json.dumps({"error": "another local compute task is currently running"}, ensure_ascii=False))
        return 2

    try:
        settings = local_settings(root, database, profile=args.profile, market_provider=args.provider)
        universe = None
        if args.config and Path(args.config).is_file():
            with open(args.config, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                universe = cfg.get("universe")

        results = compute_local(settings, universe=universe)
        print(json.dumps({"status": "completed", "tasks": results}, indent=2, ensure_ascii=False))

        # Export v2 bundle
        outbox = root / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        sha = get_current_git_sha()
        bundle = export_local_v2(settings, sequence=int(os.environ.get("RUN_SEQUENCE", "1")), code_sha=sha, universe=universe)

        bundle_path = outbox / f"bundle_{bundle['manifest']['sequence']}.json"
        with open(bundle_path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False)

        print(json.dumps({
            "status": "exported",
            "bundle_file": str(bundle_path),
            "manifest": bundle["manifest"],
        }, indent=2, ensure_ascii=False))

        return 0
    finally:
        lock.release()


def main() -> int:
    parser = argparse.ArgumentParser(description="Local ETF compute and display export CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Doctor
    p_doc = subparsers.add_parser("doctor", help="Check local environment and provider admission")
    p_doc.add_argument("--root", required=True, help="Local root directory")
    p_doc.add_argument("--db", default=None, help="SQLite database path")
    p_doc.add_argument("--profile", default="live", choices=["live", "mock"], help="Execution profile")

    # Run
    p_run = subparsers.add_parser("run", help="Run deterministic compute sequence")
    p_run.add_argument("--root", required=True, help="Local root directory")
    p_run.add_argument("--db", default=None, help="SQLite database path")
    p_run.add_argument("--profile", default="live", choices=["live", "mock"], help="Execution profile")
    p_run.add_argument("--provider", default="akshare", help="Market provider")
    p_run.add_argument("--config", default=None, help="Path to config json (universe, slots)")
    p_run.add_argument("--no-upload", action="store_true", help="Do not upload after export")

    args = parser.parse_args()
    if args.command == "doctor":
        return cmd_doctor(args)
    elif args.command == "run":
        return cmd_run(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())

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
    compute_board_only,
    compute_local,
    doctor_check,
    export_local_v2,
    local_settings,
)
from app.workspace.local_schedule import LocalRunLock


def get_current_git_sha() -> str:
    import subprocess
    # Hard gate: verify that tracked runtime code (backend, scripts, config) has NO uncommitted changes
    status_proc = subprocess.run(
        ["git", "status", "--porcelain", "backend/", "scripts/", "config/"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    if status_proc.stdout.strip():
        raise RuntimeError(f"uncommitted runtime modifications detected in repo:\n{status_proc.stdout.strip()}")

    res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=True)
    sha = res.stdout.strip()
    if not sha or len(sha) < 40 or set(sha) == {"0"}:
        raise RuntimeError("git rev-parse HEAD failed to return a valid non-zero commit SHA")
    return sha


def cmd_doctor(args: argparse.Namespace) -> int:
    root = Path(args.root)
    database = Path(args.db) if args.db else root / "db" / "research.sqlite3"
    result = doctor_check(root, database, profile=args.profile)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if (result.get("root_exists") and result.get("disk_sufficient")) else 1


def cmd_run(args: argparse.Namespace) -> int:
    import time
    from datetime import datetime
    from zoneinfo import ZoneInfo

    root = Path(args.root)
    database = Path(args.db) if args.db else root / "db" / "research.sqlite3"

    # Fix-7: Trading day gate — check verified trade day
    if not args.skip_trade_day_check:
        settings_for_check = local_settings(root, database, profile=args.profile, market_provider=args.provider)
        from app.services.trading_calendar_service import TradingCalendarService
        SHANGHAI = ZoneInfo("Asia/Shanghai")
        today = datetime.now(SHANGHAI).date()
        cal = TradingCalendarService(settings_for_check)
        decision = cal.decision(today)
        if not decision.is_trade_day or not getattr(decision, "verified", True):
            print(json.dumps({
                "status": "skipped",
                "reason": "non_trading_day_or_unverified",
                "date": today.isoformat(),
                "is_trade_day": decision.is_trade_day,
                "verified": getattr(decision, "verified", False),
            }, ensure_ascii=False))
            return 0

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

        if getattr(args, "board_only", False):
            # Local refresh-then-sync: no market fetch, rebuild board from stored rows, then export + upload.
            results = compute_board_only(settings, universe=universe)
        else:
            results = compute_local(settings, universe=universe)

        # Check if any required task failed
        for task_result in results:
            if task_result.get("status") not in {"succeeded", "partial"}:
                print(json.dumps({"status": "compute_failed", "tasks": results}, indent=2, ensure_ascii=False))
                return 1

        print(json.dumps({"status": "completed", "tasks": results}, indent=2, ensure_ascii=False))

        # Export v2 bundle — monotonic sequence: max(current ms, previous max seq + 1)
        outbox = root / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        
        highest_seq = 0
        for bfile in outbox.glob("bundle_*.json"):
            try:
                s_part = bfile.stem.split("_")[1]
                highest_seq = max(highest_seq, int(s_part))
            except (IndexError, ValueError):
                pass

        now_ms = int(time.time() * 1000)
        sequence = max(now_ms, highest_seq + 1)

        sha = get_current_git_sha()
        bundle = export_local_v2(settings, sequence=sequence, code_sha=sha, universe=universe)

        bundle_path = outbox / f"bundle_{bundle['manifest']['sequence']}.json"
        with open(bundle_path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False)

        print(json.dumps({
            "status": "exported",
            "bundle_file": str(bundle_path),
            "manifest": bundle["manifest"],
        }, indent=2, ensure_ascii=False))

        if not args.no_upload:
            # Fix-6 (part 2): missing auth is a hard error — do not silently skip
            auth_file = root / "config" / "producer_auth.json"
            if not auth_file.exists():
                print(json.dumps({
                    "status": "upload_failed",
                    "reason": "auth_file_missing",
                    "path": str(auth_file),
                }, ensure_ascii=False))
                return 1

            with open(auth_file, "r", encoding="utf-8") as f:
                auth_data = json.load(f)
            os.environ["SHADOW_PRODUCER_TOKEN"] = auth_data["producer_token"]
            os.environ["SHADOW_SIGNING_KEY_ID"] = auth_data["key_id"]
            os.environ["SHADOW_SIGNING_SECRET"] = auth_data["signing_secret"]
            sync_url = getattr(args, "sync_url", None) or "https://etf.joviluma.com/api/shadow/sync"
            from app.workspace.shadow_client import upload_bundle_auto
            try:
                # <=16 MiB per request (wire and decoded); larger bundles go chunked + atomic commit.
                receipt = upload_bundle_auto(sync_url, bundle)
                receipt_path = outbox / f"bundle_{bundle['manifest']['sequence']}.receipt.json"
                with open(receipt_path, "w", encoding="utf-8") as rf:
                    json.dump(receipt, rf, indent=2, ensure_ascii=False)
                print(json.dumps({"status": "uploaded", "receipt": receipt}, indent=2, ensure_ascii=False))
            except Exception as exc:
                # Fix-6: upload failure must exit non-zero so Windows Task Scheduler records it
                print(json.dumps({"status": "upload_failed", "error": str(exc)}, ensure_ascii=False))
                return 1

        return 0
    finally:
        lock.release()


def cmd_reconcile(args: argparse.Namespace) -> int:
    from datetime import date, datetime
    from zoneinfo import ZoneInfo
    from app.workspace.local_compute import local_session
    from app.workspace.local_reconcile import recent_base_days, run_reconcile

    root = Path(args.root)
    database = Path(args.db) if args.db else root / "db" / "research.sqlite3"
    session = date.fromisoformat(args.session) if args.session else datetime.now(ZoneInfo("Asia/Shanghai")).date()
    settings = local_settings(root, database, profile=args.profile, market_provider=args.provider)
    with local_session(settings) as db:
        report = run_reconcile(root, session=session, db=db, outcome_base_days=recent_base_days(db, session, args.lookback))
    print(json.dumps({"status": "reconciled", "report_file": report["report_file"],
                      "delivery_counts": report["delivery"]["counts"],
                      "consumer_identity": report["consumer_identity"]["state"],
                      "outcomes": [{"base": o["base_trade_date"], **o["summary"]} for o in report["outcomes"]]},
                     indent=2, ensure_ascii=False))
    bad = {k: v for k, v in report["delivery"]["counts"].items() if k != "MATCHED"}
    return 1 if bad else 0


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
    p_run.add_argument("--provider", default="public_composite", help="Market provider")
    p_run.add_argument("--config", default=None, help="Path to config json (universe, slots)")
    p_run.add_argument("--sync-url", default="https://etf.joviluma.com/api/shadow/sync", help="HTTPS upload endpoint")
    p_run.add_argument("--no-upload", action="store_true", help="Do not upload after export")
    p_run.add_argument("--skip-trade-day-check", action="store_true", help="Bypass trading day gate (for testing/manual runs)")

    p_run.add_argument("--board-only", action="store_true", help="Local refresh-then-sync: rebuild decision board from stored local rows, no market fetch")

    # Reconcile (16:30): local outbox vs receipts + matured T+1/T+5 outcomes; read-only, results stay local
    p_rec = subparsers.add_parser("reconcile", help="Reconcile local bundles with receipts and summarise matured T+1/T+5 outcomes")
    p_rec.add_argument("--root", required=True, help="Local root directory")
    p_rec.add_argument("--db", default=None, help="SQLite database path")
    p_rec.add_argument("--profile", default="live", choices=["live", "mock"], help="Execution profile")
    p_rec.add_argument("--provider", default="public_composite", help="Market provider (no network use in reconcile)")
    p_rec.add_argument("--session", default=None, help="Session date YYYY-MM-DD (default: today Asia/Shanghai)")
    p_rec.add_argument("--lookback", type=int, default=6, help="Number of recent trade days used as outcome bases")

    args = parser.parse_args()
    if args.command == "doctor":
        return cmd_doctor(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "reconcile":
        return cmd_reconcile(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())

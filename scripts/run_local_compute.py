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
    load_local_config,
    validate_provider_admission,
    OPTIONAL_TASK_PARTS,
    closed_session_result_accepted,
)
from app.workspace.local_schedule import LocalRunLock
from app.workspace.local_atomic import write_json_atomic


def get_current_git_sha() -> str:
    import subprocess
    # Hard gate: verify that tracked runtime code (backend, scripts, config) has NO uncommitted changes
    status_proc = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "backend/", "scripts/", "config/", "frontend/", "pyproject.toml"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    if status_proc.stdout.strip():
        raise RuntimeError("uncommitted runtime modifications detected in repo")

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
    return 0 if all(result.get(key) for key in ("root_exists", "marker_exists", "database_exists", "disk_sufficient")) else 1


def cmd_run(args: argparse.Namespace) -> int:
    import time
    from datetime import datetime
    from zoneinfo import ZoneInfo

    root = Path(args.root)
    database = Path(args.db) if args.db else root / "db" / "research.sqlite3"
    config_path = Path(args.config) if args.config else root / "config" / "live.json"
    cfg = load_local_config(root, config_path)
    sha = get_current_git_sha()
    expected = getattr(args, "expected_sha", None)
    if expected and expected != sha:
        raise ValueError("configured code identity mismatch")
    if args.profile == "live" and not expected:
        raise ValueError("live execution requires --expected-sha")
    if args.profile == "mock" and not args.no_upload:
        raise ValueError("mock profile cannot upload")
    settings = local_settings(root, database, profile=args.profile, market_provider=args.provider)
    universe = cfg["universe"]
    admission = cfg.get("provider_admission")
    private_research = getattr(args, "private_research", False)
    closed_session_research = getattr(args, "closed_session_research", False)
    if closed_session_research and (not private_research or args.profile != "live"):
        raise ValueError("closed-session research requires explicit live private research scope")
    if args.profile == "live":
        required = "compute" if getattr(args, "compute_only", False) else "export"
        check = validate_provider_admission(args.provider, evidence=admission, purpose=required,
                                            private_research=private_research)
        if not check["operation_permitted"]:
            print(json.dumps({"status": "admission_blocked", "admission": check}, ensure_ascii=False))
            return 1
    original_config = config_path.read_bytes()

    # Fix-7: Trading day gate — check verified trade day
    if not args.skip_trade_day_check:
        from app.services.trading_calendar_service import TradingCalendarService
        SHANGHAI = ZoneInfo("Asia/Shanghai")
        today = datetime.now(SHANGHAI).date()
        cal = TradingCalendarService(settings)
        decision = cal.decision(today)
        if not decision.verified:
            print(json.dumps({"status": "calendar_unknown", "date": today.isoformat()}))
            return 1
        if not decision.is_trade_day:
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
        if getattr(args, "board_only", False):
            # Local refresh-then-sync: no market fetch, rebuild board from stored rows, then export + upload.
            results = compute_board_only(settings, universe=universe)
        else:
            results = compute_local(settings, universe=universe, admission=admission, private_research=private_research,
                                    closed_session_research=closed_session_research)

        # Check if any required task failed
        if not results:
            print(json.dumps({"status": "compute_failed", "reason": "no_task_results"}))
            return 1
        for task_result in results:
            closed_accepted = closed_session_research and private_research and closed_session_result_accepted(task_result)
            if task_result.get("required", True) and task_result.get("status") != "succeeded" and not closed_accepted:
                print(json.dumps({"status": "compute_failed", "tasks": results}, indent=2, ensure_ascii=False))
                return 1

        print(json.dumps({"status": "completed", "tasks": results}, indent=2, ensure_ascii=False))
        if getattr(args, "compute_only", False):
            return 0

        # Export v2 bundle — monotonic sequence: max(current ms, previous max seq + 1)
        if get_current_git_sha() != sha or config_path.read_bytes() != original_config:
            raise ValueError("code/config identity changed during compute")
        if args.profile == "live" and not validate_provider_admission(
            args.provider, evidence=admission, private_research=private_research
        )["operation_permitted"]:
            print(json.dumps({"status": "export_blocked", "reason": "display_or_quality_UNKNOWN"}))
            return 1
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

        unavailable = [OPTIONAL_TASK_PARTS[item["task_name"]] for item in results
                       if item.get("task_name") in OPTIONAL_TASK_PARTS and item.get("status") != "succeeded"]
        bundle = export_local_v2(settings, sequence=sequence, code_sha=sha, universe=universe,
                                 admission=admission, private_research=private_research, unavailable_parts=unavailable,
                                 closed_session_result=next((item for item in results if closed_session_result_accepted(item)), None))

        bundle_path = outbox / f"bundle_{bundle['manifest']['sequence']}.json"
        write_json_atomic(bundle_path, bundle)

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
                write_json_atomic(receipt_path, receipt)
                print(json.dumps({"status": "uploaded", "receipt": receipt}, indent=2, ensure_ascii=False))
            except Exception as exc:
                # Fix-6: upload failure must exit non-zero so Windows Task Scheduler records it
                print(json.dumps({"status": "upload_failed", "error_type": type(exc).__name__}, ensure_ascii=False))
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
    expected = getattr(args, "expected_sha", None)
    if args.profile == "live" and (not expected or get_current_git_sha() != expected):
        raise ValueError("reconcile requires approved clean --expected-sha")
    settings = local_settings(root, database, profile=args.profile, market_provider=args.provider)
    with local_session(settings) as db:
        report = run_reconcile(root, session=session, db=db, outcome_base_days=recent_base_days(db, session, args.lookback))
    print(json.dumps({"status": "reconciled", "report_file": report["report_file"],
                      "delivery_counts": report["delivery"]["counts"],
                      "consumer_identity": report["consumer_identity"]["state"],
                      "outcomes": [{"base": o["base_trade_date"], **o["summary"]} for o in report["outcomes"]]},
                     indent=2, ensure_ascii=False))
    return 0 if report["state"] == "PASS" else 1


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
    p_run.add_argument("--expected-sha", default=None, help="Full approved code SHA (required for live execution)")
    p_run.add_argument("--sync-url", default="https://etf.joviluma.com/api/shadow/sync", help="HTTPS upload endpoint")
    p_run.add_argument("--no-upload", action="store_true", help="Do not upload after export")
    p_run.add_argument("--compute-only", action="store_true", help="Local compute only; no display export or upload")
    p_run.add_argument("--private-research", action="store_true", help="Explicit owner-private research execution scope; does not certify data rights or quality")
    p_run.add_argument("--closed-session-research", action="store_true", help="After 16:00 only: validate newly fetched same-session stale quotes as non-realtime private research inputs")
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
    p_rec.add_argument("--expected-sha", default=None, help="Full approved code SHA (required for live reconcile)")

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

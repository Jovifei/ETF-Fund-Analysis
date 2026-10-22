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
    optional_result_available,
    closed_session_result_accepted,
    compute_local_fast,
    create_base_manifest,
    validate_base_manifest,
    validate_fast_result,
    build_execution_lineage,
)
from app.workspace.local_schedule import LocalRunLock
from app.workspace.local_atomic import write_json_atomic
from app.workspace.local_execution import execution_identity


def read_execution(args):
    root = Path(args.root)
    database = Path(args.db) if args.db else root / 'db' / 'research.sqlite3'
    config = Path(args.config) if args.config else root / 'config' / 'live.json'
    try:
        if not config.is_file() or config.is_symlink():
            raise ValueError('local config file required')
        raw = config.read_bytes()
    except OSError:
        raise ValueError('local config file required') from None
    cfg = load_local_config(root, config, content=raw)
    settings = local_settings(root, database, profile=args.profile, market_provider=args.provider)
    identity = execution_identity(raw, database=database, profile=args.profile, provider=args.provider,
        private_research=getattr(args, 'private_research', False),
        closed_session_research=getattr(args, 'closed_session_research', False),
        sync_url=getattr(args, 'sync_url', None) or 'https://etf.joviluma.com/api/shadow/sync')
    return cfg, settings, identity, raw


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
    config_path = Path(args.config) if args.config else root / "config" / "live.json"
    sha = get_current_git_sha()
    expected = getattr(args, "expected_sha", None)
    if expected and expected != sha:
        raise ValueError("configured code identity mismatch")
    if args.profile == "live" and not expected:
        raise ValueError("live execution requires --expected-sha")
    if args.profile == "mock" and not args.no_upload:
        raise ValueError("mock profile cannot upload")
    cfg, settings, execution, original_config = read_execution(args)
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
    def check_execution():
        current_cfg, _, current, _ = read_execution(args)
        if args.profile == 'live' and not validate_provider_admission(args.provider, profile=args.profile,
                evidence=current_cfg.get('provider_admission'), purpose='export',
                private_research=private_research)['operation_permitted']:
            raise ValueError('current provider admission blocked')
        if current != execution or get_current_git_sha() != sha:
            raise ValueError('execution configuration changed')

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

    external_lock = getattr(args, '_external_lock', None)
    lock = external_lock or LocalRunLock(root / ".run.lock")
    if external_lock is not None and (not isinstance(external_lock, LocalRunLock) or external_lock._fd is None):
        raise ValueError('dispatcher execution lock required')
    if external_lock is None and not lock.acquire():
        print(json.dumps({"error": "another local compute task is currently running"}, ensure_ascii=False))
        return 2

    try:
        previous_source = os.environ.get('GIT_COMMIT_SHA')
        os.environ['GIT_COMMIT_SHA'] = sha  # Only this verified process; no persistent configuration change.
        mode = getattr(args, 'cadence_mode', 'full')
        base_path = root / 'state' / 'settled_base.json'
        base = None
        if mode in {'fast', 'auto'}:
            try:
                base = json.loads(base_path.read_text(encoding='utf-8'))
                validate_base_manifest(settings, universe, base, code_sha=sha, execution_hash=execution['execution_hash'])
                mode = 'fast'
            except (OSError, ValueError, TypeError):
                if mode == 'fast':
                    raise ValueError('fast settled base unavailable') from None
                mode = 'full'
                print(json.dumps({'status': 'base_recovery', 'mode': 'full'}))
        observer = getattr(args, '_on_task', None)
        if getattr(args, "board_only", False):
            # Local refresh-then-sync: no market fetch, rebuild board from stored rows, then export + upload.
            results = compute_board_only(settings, universe=universe)
        elif mode in {'fast', 'auto'}:
            results = compute_local_fast(settings, universe, base_manifest=base, code_sha=sha,
                admission=admission, private_research=private_research, on_task=observer,
                execution_hash=execution['execution_hash'])
        else:
            results = compute_local(settings, universe=universe, admission=admission, private_research=private_research,
                                    closed_session_research=closed_session_research, on_task=observer)

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
        if mode == 'full' and getattr(args, 'prepare_base', False):
            base = create_base_manifest(settings, universe, code_sha=sha, execution_hash=execution['execution_hash'])
            write_json_atomic(base_path, base)
        def validate_fast():
            if mode in {'fast', 'auto'}:
                validate_base_manifest(settings, universe, base, code_sha=sha, execution_hash=execution['execution_hash'])
                validate_fast_result(settings, universe, results)
        validate_fast()
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

        unavailable = sorted({OPTIONAL_TASK_PARTS[item["task_name"]] for item in results
                              if item.get("task_name") in OPTIONAL_TASK_PARTS and not optional_result_available(item)})
        # Fast slots never call providers for optional context; they re-publish a same-day
        # full refresh labelled as carried forward, or an honest not_refreshed_today reason.
        carry_optional = mode in {'fast', 'auto'}
        lineage = (build_execution_lineage(settings, universe, results, base_manifest=base,
                    execution_hash=execution['execution_hash'], config_file_hash=execution['config_file_hash'],
                    mode='fast' if mode == 'fast' else 'full')
                   if getattr(args, 'prepare_base', False) else None)
        check_execution()
        bundle = export_local_v2(settings, sequence=sequence, code_sha=sha, universe=universe,
                                 admission=admission, private_research=private_research, unavailable_parts=unavailable,
                                 closed_session_result=next((item for item in results if closed_session_result_accepted(item)), None),
                                 execution_lineage=lineage, carry_optional=carry_optional)

        bundle_path = outbox / f"bundle_{bundle['manifest']['sequence']}.json"
        if callback := getattr(args, '_on_export_intent', None):
            callback(bundle, bundle_path)
        write_json_atomic(bundle_path, bundle)
        if callback := getattr(args, '_on_export', None):
            callback(bundle, bundle_path)

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
                check_execution()
                validate_fast()
                # <=16 MiB per request (wire and decoded); larger bundles go chunked + atomic commit.
                receipt = upload_bundle_auto(sync_url, bundle)
                receipt_path = outbox / f"bundle_{bundle['manifest']['sequence']}.receipt.json"
                write_json_atomic(receipt_path, receipt)
                if callback := getattr(args, '_on_receipt', None):
                    callback(bundle['manifest'], receipt)
                print(json.dumps({"status": "uploaded", "receipt": receipt}, indent=2, ensure_ascii=False))
            except Exception as exc:
                # Fix-6: upload failure must exit non-zero so Windows Task Scheduler records it
                print(json.dumps({"status": "upload_failed", "error_type": type(exc).__name__}, ensure_ascii=False))
                return 1

        return 0
    finally:
        if previous_source is None:
            os.environ.pop('GIT_COMMIT_SHA', None)
        else:
            os.environ['GIT_COMMIT_SHA'] = previous_source
        if external_lock is None:
            lock.release()


def cmd_dispatch(args: argparse.Namespace) -> int:
    """Minute wake-ups share one durable scheduling and execution owner."""
    from copy import copy
    from datetime import datetime, timezone
    from app.services.trading_calendar_service import TradingCalendarService
    from app.utils.hashing import stable_hash
    from app.workspace.local_dispatch import dispatch_once, load_pending_bundle
    from app.workspace.shadow_bundle import digest
    from app.workspace.shadow_client import upload_bundle_auto
    root = Path(args.root)
    cfg, settings, execution, _ = read_execution(args)
    sha = get_current_git_sha()
    if args.profile != 'live' or args.expected_sha != sha or args.no_upload or args.compute_only or args.board_only:
        raise ValueError('dispatcher requires approved live source and real delivery')
    identity = {'code_sha': sha, 'config_hash': stable_hash(settings.load_strategy()),
                'scope_hash': digest(sorted(cfg['universe']))}

    def run_job(mode, *, on_task, on_export_intent, on_export, on_receipt, lock):
        child = copy(args)
        child.cadence_mode = 'auto' if mode == 'fast' else 'full'
        child.prepare_base = True
        def observe(name, result, run_id):
            if name == 'refresh_decision_board' and result is not None and result.get('status') == 'succeeded':
                from sqlalchemy import select
                from app.models import DecisionBoardSnapshot
                from app.workspace.local_compute import local_session
                with local_session(settings) as db:
                    snapshot = db.scalar(select(DecisionBoardSnapshot).where(
                        DecisionBoardSnapshot.snapshot_id == result.get('snapshot_id')))
                    rows = (snapshot.payload_json or {}).get('rows', []) if snapshot else []
                    found = [row.get('ts_code') for row in rows if row.get('ts_code') in cfg['universe']]
                result = {**result, 'requested': len(cfg['universe']), 'completed': len(found),
                          'coverage_complete': len(found) == len(set(found)) == len(cfg['universe'])}
            on_task(name, result, run_id)
        child._external_lock, child._on_task = lock, observe
        child._on_export_intent, child._on_export, child._on_receipt = on_export_intent, on_export, on_receipt
        return cmd_run(child)

    def recover_export(*, attempt):
        if get_current_git_sha() != sha:
            raise ValueError('replay source changed')
        current_cfg, _, current_execution, _ = read_execution(args)
        if not validate_provider_admission(args.provider, profile=args.profile,
                evidence=current_cfg.get('provider_admission'), purpose='export',
                private_research=args.private_research)['operation_permitted']:
            raise ValueError('current provider admission blocked')
        return load_pending_bundle(root, attempt, {**identity, **current_execution}, now=datetime.now(timezone.utc))

    def replay(*, attempt, on_receipt):
        bundle = recover_export(attempt=attempt)
        bundle_path = root / 'outbox' / attempt['bundle_file']
        manifest = bundle['manifest']
        auth_file = root / 'config' / 'producer_auth.json'
        auth_data = json.loads(auth_file.read_text(encoding='utf-8'))
        os.environ.update(SHADOW_PRODUCER_TOKEN=auth_data['producer_token'],
                          SHADOW_SIGNING_KEY_ID=auth_data['key_id'], SHADOW_SIGNING_SECRET=auth_data['signing_secret'])
        receipt = upload_bundle_auto(args.sync_url, bundle)
        write_json_atomic(bundle_path.with_suffix('.receipt.json'), receipt)
        on_receipt(manifest, receipt)

    result = dispatch_once(root, identity, calendar=TradingCalendarService(settings),
                           run_job=run_job, replay=replay, recover_export=recover_export, execution=execution)
    print(json.dumps({'status': 'dispatch_finished', 'exit_code': result}))
    return result


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
    p_run.add_argument("--closed-session-research", action="store_true", help="Private non-realtime closing research: current verified session after 16:00, previous verified session before 09:00")
    p_run.add_argument("--skip-trade-day-check", action="store_true", help="Bypass trading day gate (for testing/manual runs)")

    p_run.add_argument("--board-only", action="store_true", help="Local refresh-then-sync: rebuild decision board from stored local rows, no market fetch")
    p_run.add_argument('--cadence-mode', default='full', choices=['full', 'fast', 'auto'])
    p_run.add_argument('--prepare-base', action='store_true', help='Persist validated settled inputs after full preparation')

    subparsers.add_parser('dispatch', parents=[p_run], add_help=False,
                         help='Recover and execute the latest due slot; invoke every minute')

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
    elif args.command == 'dispatch':
        return cmd_dispatch(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())

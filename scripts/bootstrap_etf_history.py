#!/usr/bin/env python3
"""Bootstrap historical K-line and indicator data for local ETF universe."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models import DailyBar, Instrument
from app.services.task_service import TaskService
from app.workspace.local_compute import local_settings, load_local_config, validate_provider_admission


def check_instrument_coverage(db: Session, codes: list[str], min_bars: int = 120) -> tuple[list[str], list[str]]:
    """Split codes into (adequate_history, missing_history)."""
    adequate = []
    missing = []
    for code in codes:
        inst = db.scalar(select(Instrument).where(Instrument.ts_code == code.upper()))
        if not inst:
            missing.append(code)
            continue
        bar_count = db.scalar(select(func.count(func.distinct(DailyBar.trade_date))).where(
            DailyBar.instrument_id == inst.id, DailyBar.adjust == "none",
            ~DailyBar.source.ilike("%mock%"), DailyBar.close > 0, DailyBar.volume > 0)) or 0
        if bar_count >= min_bars:
            adequate.append(code)
        else:
            missing.append(code)
    return adequate, missing


def bootstrap_universe(
    root: Path,
    database: Path,
    universe: list[str],
    provider: str = "public_composite",
    lookback_days: int = 420,
    delay_seconds: float = 1.5,
    dry_run: bool = False,
    admission: dict | None = None,
) -> dict[str, Any]:
    settings = local_settings(root, database, profile="live", market_provider=provider)
    engine = create_engine(settings.database_url)

    report: dict[str, Any] = {
        "total_universe": len(universe),
        "already_adequate": [],
        "bootstrapped": [],
        "failed": [],
    }

    try:
        with Session(engine) as db:
            adequate, missing = check_instrument_coverage(db, universe, min_bars=120)
            report["already_adequate"] = adequate
            report["missing_history"] = missing
            if dry_run:
                report["state"] = "DRY_RUN_NO_FETCH_OR_WRITE"
                return report
            check = validate_provider_admission(provider, evidence=admission, purpose="compute")
            if not check["admitted"]:
                raise ValueError("provider acquisition/storage admission UNKNOWN")
            service = TaskService(settings)
            try:
                # 0. Sync instruments first so any newly declared universe items exist in DB
                print("[*] Synchronizing instruments into local database...")
                with Session(engine) as sync_db, sync_db.begin():
                    sync_res = service.run(sync_db, "sync_instruments", codes=universe)
                print(f"    -> Sync result: created={sync_res.get('created')}, updated={sync_res.get('updated')}")

                adequate, missing = check_instrument_coverage(db, universe, min_bars=120)
                report["already_adequate"] = adequate
                print(f"[*] Universe status: {len(adequate)} adequate, {len(missing)} missing/incomplete.")

                if sync_res.get("status") != "succeeded":
                    raise ValueError("instrument synchronization incomplete")
                if not missing:
                    return report

                for idx, code in enumerate(missing, 1):
                    print(f"[{idx}/{len(missing)}] Fetching history for {code} (lookback={lookback_days}d)...")
                    try:
                        # 1. Refresh bars
                        with Session(engine) as task_db, task_db.begin():
                            bar_res = service.run(task_db, "refresh_bars", lookback_days=lookback_days, codes=[code])
                        print(f"    -> Bars: {bar_res.get('status')} ({bar_res.get('inserted', 0)} inserted)")
                        if bar_res.get("status") != "succeeded":
                            raise ValueError("required bar refresh incomplete")

                        # 2. Refresh indicators for this code
                        with Session(engine) as task_db, task_db.begin():
                            ind_res = service.run(task_db, "refresh_indicators", codes=[code])
                        print(f"    -> Indicators: {ind_res.get('status')}")
                        if ind_res.get("status") != "succeeded":
                            raise ValueError("required indicator refresh incomplete")

                        # 3. Refresh forecasts for this code
                        with Session(engine) as task_db, task_db.begin():
                            fc_res = service.run(task_db, "refresh_forecasts", codes=[code])
                        print(f"    -> Forecasts: {fc_res.get('status')}")
                        if fc_res.get("status") != "succeeded":
                            raise ValueError("required forecast refresh incomplete")

                        ready, _ = check_instrument_coverage(db, [code], min_bars=120)
                        if not ready:
                            raise ValueError("observed history remains incomplete")

                        report["bootstrapped"].append(code)
                    except Exception as exc:
                        print(f"    [!] Failed to bootstrap {code}: {exc}")
                        report["failed"].append({"code": code, "error_type": type(exc).__name__})

                    if delay_seconds > 0 and idx < len(missing):
                        time.sleep(delay_seconds)
            finally:
                service.close()
    finally:
        engine.dispose()

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap historical ETF bars into local SQLite database")
    parser.add_argument("--root", default="F:\\ETF_Data\\ETF-Fund-Analysis", help="Local root directory")
    parser.add_argument("--db", default=None, help="SQLite database path")
    parser.add_argument("--config", default=None, help="Config file containing universe")
    parser.add_argument("--symbols", nargs="+", default=None, help="Specific symbols to bootstrap")
    parser.add_argument("--provider", default="public_composite", help="Market provider")
    parser.add_argument("--lookback", type=int, default=420, help="History lookback days")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay seconds between instruments")
    parser.add_argument("--dry-run", action="store_true", help="Check status without fetching")
    parser.add_argument("--expected-sha", default=None, help="Full approved code SHA; required except dry run")

    args = parser.parse_args()
    root = Path(args.root)
    database = Path(args.db) if args.db else root / "db" / "research.sqlite3"

    universe = args.symbols
    cfg = load_local_config(root, Path(args.config) if args.config else None)
    if not args.dry_run:
        from run_local_compute import get_current_git_sha
        if not args.expected_sha or get_current_git_sha() != args.expected_sha:
            raise ValueError("bootstrap requires approved clean --expected-sha")
    if not universe:
        universe = cfg["universe"]

    print(f"[*] Starting history bootstrap for {len(universe)} symbols...")
    result = bootstrap_universe(
        root=root,
        database=database,
        universe=universe,
        provider=args.provider,
        lookback_days=args.lookback,
        delay_seconds=args.delay,
        dry_run=args.dry_run,
        admission=cfg.get("provider_admission"),
    )
    print("\n[+] Bootstrap Report:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())

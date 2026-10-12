#!/usr/bin/env python3
"""Bootstrap historical K-line and indicator data for local ETF universe."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models import DailyBar, Instrument
from app.services.task_service import TaskService
from app.workspace.local_compute import local_settings


def check_instrument_coverage(db: Session, codes: list[str], min_bars: int = 120) -> tuple[list[str], list[str]]:
    """Split codes into (adequate_history, missing_history)."""
    adequate = []
    missing = []
    for code in codes:
        inst = db.scalar(select(Instrument).where(Instrument.ts_code == code.upper()))
        if not inst:
            missing.append(code)
            continue
        bar_count = db.scalar(select(func.count(DailyBar.id)).where(DailyBar.instrument_id == inst.id)) or 0
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
            print(f"[*] Universe status: {len(adequate)} adequate, {len(missing)} missing/incomplete.")

            if dry_run or not missing:
                return report

            service = TaskService(settings)
            try:
                for idx, code in enumerate(missing, 1):
                    print(f"[{idx}/{len(missing)}] Fetching history for {code} (lookback={lookback_days}d)...")
                    try:
                        # 1. Refresh bars
                        with Session(engine) as task_db, task_db.begin():
                            bar_res = service.run(task_db, "refresh_bars", lookback_days=lookback_days, codes=[code])
                        print(f"    -> Bars: {bar_res.get('status')} ({bar_res.get('inserted', 0)} inserted)")

                        # 2. Refresh indicators for this code
                        with Session(engine) as task_db, task_db.begin():
                            ind_res = service.run(task_db, "refresh_indicators", codes=[code])
                        print(f"    -> Indicators: {ind_res.get('status')}")

                        # 3. Refresh forecasts for this code
                        with Session(engine) as task_db, task_db.begin():
                            fc_res = service.run(task_db, "refresh_forecasts", codes=[code])
                        print(f"    -> Forecasts: {fc_res.get('status')}")

                        report["bootstrapped"].append(code)
                    except Exception as exc:
                        print(f"    [!] Failed to bootstrap {code}: {exc}")
                        report["failed"].append({"code": code, "error": str(exc)})

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

    args = parser.parse_args()
    root = Path(args.root)
    database = Path(args.db) if args.db else root / "db" / "research.sqlite3"

    universe = args.symbols
    if not universe:
        cfg_path = Path(args.config) if args.config else root / "config" / "live.json"
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                universe = cfg.get("universe", [])
        else:
            print(f"[!] Config not found at {cfg_path}, please specify --symbols or --config")
            return 1

    print(f"[*] Starting history bootstrap for {len(universe)} symbols...")
    result = bootstrap_universe(
        root=root,
        database=database,
        universe=universe,
        provider=args.provider,
        lookback_days=args.lookback,
        delay_seconds=args.delay,
        dry_run=args.dry_run,
    )
    print("\n[+] Bootstrap Report:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

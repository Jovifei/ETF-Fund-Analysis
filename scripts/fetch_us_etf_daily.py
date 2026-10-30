#!/usr/bin/env python3
"""Fetch US ETF daily bars and compute indicators for local research."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
import sys
from pathlib import Path

# Add backend directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.models import DailyBar, Instrument
from app.providers.yfinance_provider import YFinanceProvider, _DEFAULT_US_ETF_CATALOG
from app.utils.hashing import stable_hash

DEFAULT_SYMBOLS = [item["symbol"] for item in _DEFAULT_US_ETF_CATALOG]


def sync_us_etfs(
    db: Session,
    symbols: list[str],
    start_date: date,
    end_date: date,
    dry_run: bool = False,
) -> dict:
    provider = YFinanceProvider()
    results = {"total": len(symbols), "synced": [], "failed": [], "bars_count": {}}

    for sym in symbols:
        inst_meta = provider.resolve_instrument(sym)
        if not inst_meta:
            results["failed"].append({"symbol": sym, "reason": "unsupported_symbol"})
            continue

        ts_code = inst_meta.ts_code
        try:
            bars = provider.fetch_daily_bars(sym, start_date, end_date)
        except Exception as exc:
            results["failed"].append({"symbol": sym, "reason": type(exc).__name__})
            continue

        results["bars_count"][sym] = len(bars)
        if dry_run or not bars:
            results["synced"].append(sym)
            continue

        # Ensure Instrument exists in DB
        inst = db.scalar(select(Instrument).where(Instrument.ts_code == ts_code))
        if not inst:
            inst = Instrument(
                ts_code=ts_code,
                symbol=inst_meta.symbol,
                name=inst_meta.name,
                kind="ETF",
                exchange=inst_meta.exchange,
                theme_l1=inst_meta.theme_l1,
                theme_l2=inst_meta.theme_l2,
                benchmark=inst_meta.benchmark,
                enabled=True,
                metadata_json={"market": "US", "currency": "USD", "provider": "yfinance"},
            )
            db.add(inst)
            db.flush()

        # Insert or update DailyBars
        inserted = 0
        for b in bars:
            quality_digest = stable_hash(b.to_dict())
            existing = db.scalar(
                select(DailyBar).where(
                    DailyBar.instrument_id == inst.id,
                    DailyBar.trade_date == b.trade_date,
                    DailyBar.adjust == b.adjust,
                )
            )
            if existing:
                existing.open = b.open
                existing.high = b.high
                existing.low = b.low
                existing.close = b.close
                existing.volume = b.volume
                existing.pct_change = b.pct_change
                existing.source = b.source
                existing.quality_hash = quality_digest
            else:
                new_bar = DailyBar(
                    instrument_id=inst.id,
                    trade_date=b.trade_date,
                    open=b.open,
                    high=b.high,
                    low=b.low,
                    close=b.close,
                    volume=b.volume,
                    pct_change=b.pct_change,
                    adjust=b.adjust,
                    source=b.source,
                    quality_hash=quality_digest,
                )
                db.add(new_bar)
            inserted += 1

        db.commit()
        results["synced"].append(sym)

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_SYMBOLS,
        help="US ETF symbols (e.g. SPY QQQ GLD)",
    )
    parser.add_argument(
        "--start-date",
        default=(date.today() - timedelta(days=365)).isoformat(),
        help="Start date YYYY-MM-DD",
    )
    parser.add_argument(
        "--end-date",
        default=date.today().isoformat(),
        help="End date YYYY-MM-DD",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and validate without writing to database",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="SQLAlchemy database URL override",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    db_url = args.db_url or settings.database_url
    engine = create_engine(db_url)
    session_factory = sessionmaker(bind=engine)

    start_d = date.fromisoformat(args.start_date)
    end_d = date.fromisoformat(args.end_date)

    with session_factory() as db:
        res = sync_us_etfs(
            db,
            symbols=args.symbols,
            start_date=start_d,
            end_date=end_d,
            dry_run=args.dry_run,
        )

    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if not res["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

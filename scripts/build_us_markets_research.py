#!/usr/bin/env python
"""Build the US markets research snapshot + 2018-> history into an explicit directory.

Research only (actionable=false, not_calibrated). Writes UTF-8/LF files and never
touches the live data root, the database, scheduled tasks or bundles.

Examples:
  python scripts/build_us_markets_research.py --out-dir D:/scratch/us_research --source yfinance
  python scripts/build_us_markets_research.py --out-dir D:/scratch/us_research --source csv --csv us_daily_ohlcv.csv --as-of 2026-11-13
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.us_markets_research import builder  # noqa: E402
from app.us_markets_research.providers import CsvProvider, YFinanceProvider  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", required=True, help="explicit output directory (never defaulted)")
    parser.add_argument("--source", choices=["yfinance", "csv"], default="yfinance")
    parser.add_argument("--csv", help="tidy long CSV for --source csv")
    parser.add_argument("--as-of", help="truncate at this US session date (YYYY-MM-DD)")
    parser.add_argument("--config", default=str(builder.DEFAULT_CONFIG_PATH))
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if args.source == "csv" and not args.csv:
        parser.error("--csv is required with --source csv")
    provider = CsvProvider(args.csv) if args.source == "csv" else YFinanceProvider()
    config = builder.load_config(args.config)
    result = builder.build(config, provider, as_of=date.fromisoformat(args.as_of) if args.as_of else None)
    files = builder.write_outputs(result, args.out_dir)
    summary = {"availability": result.part["availability"], "as_of": result.part["as_of"],
               "series": [{"id": s["series_id"], "available": s.get("available"), "reason": s.get("reason")}
                          for s in result.part["series"]],
               "provisional_closes": len(result.part["provisional_closes"]),
               "failed_tickers": result.part["failed_tickers"], "problems": result.problems, "files": files}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 1 if result.problems or result.part["availability"] == "unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build structure_v1 shadow JSON from OHLCV bars — in-repo, reproducible.

Uses the real etf_structure_features proxies (not stubs). Does not call
assign_grade / does not flip CONFIG_HASH.

Examples:
  # From an existing bars cache (no network):
  python build_shadow.py --cache data/bars_cache.json --slim /path/to/slim.json

  # Fetch missing symbols via akshare (optional):
  python build_shadow.py --slim /path/to/slim.json --fetch

  # Universe list as ts_code JSON array when slim is unavailable:
  python build_shadow.py --universe-json data/universe_34.json --cache data/bars_cache.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from etf_structure_features import RISK_BUCKET_RULE_VERSION, build_structure_row  # noqa: E402

SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_OUT = ROOT / "out"
DEFAULT_CACHE = ROOT / "data" / "bars_cache.json"


def fetch_hist(symbol: str, start: str, end: str):
    import akshare as ak

    df = ak.fund_etf_hist_em(
        symbol=symbol, period="daily", start_date=start, end_date=end, adjust="qfq"
    )
    rows = []
    for rec in df.to_dict("records"):
        rows.append(
            {
                "date": str(rec["日期"])[:10],
                "open": float(rec["开盘"]),
                "high": float(rec["最高"]),
                "low": float(rec["最低"]),
                "close": float(rec["收盘"]),
                "volume": float(rec["成交量"]),
            }
        )
    return rows


def _load_universe(args: argparse.Namespace) -> list[dict]:
    if args.slim:
        slim = json.loads(Path(args.slim).read_text(encoding="utf-8"))
        rows = slim.get("rows") or slim
        if not isinstance(rows, list):
            raise SystemExit("slim JSON must contain a rows list")
        return [
            {
                "ts_code": r["ts_code"],
                "name": r.get("name"),
                "atr14": r.get("atr14"),
                "price": r.get("price"),
                "_slim_meta": slim.get("manifest") if isinstance(slim, dict) else None,
            }
            for r in rows
        ]
    if args.universe_json:
        raw = json.loads(Path(args.universe_json).read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "rows" in raw:
            raw = raw["rows"]
        out = []
        for item in raw:
            if isinstance(item, str):
                out.append({"ts_code": item, "name": None, "atr14": None, "price": None})
            else:
                out.append(
                    {
                        "ts_code": item["ts_code"],
                        "name": item.get("name"),
                        "atr14": item.get("atr14"),
                        "price": item.get("price"),
                    }
                )
        return out
    raise SystemExit("provide --slim or --universe-json")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--slim", type=Path, help="email slim JSON with rows[].ts_code")
    p.add_argument("--universe-json", type=Path, help="JSON list of ts_code or row objects")
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="bars cache path")
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--fetch", action="store_true", help="akshare-fetch missing cache entries")
    p.add_argument("--start", default="20250101")
    p.add_argument("--end", default=datetime.now(tz=SHANGHAI).strftime("%Y%m%d"))
    p.add_argument("--expect-n", type=int, default=0, help="optional universe size assert")
    args = p.parse_args(argv)

    universe = _load_universe(args)
    if args.expect_n and len(universe) != args.expect_n:
        raise SystemExit(f"universe size {len(universe)} != expect-n {args.expect_n}")

    cache: dict = {}
    if args.cache.exists():
        cache = json.loads(args.cache.read_text(encoding="utf-8"))

    rows_out: list[dict] = []
    errors: list[dict] = []
    slim_meta = universe[0].get("_slim_meta") if universe else None

    for i, sr in enumerate(universe):
        ts = sr["ts_code"]
        symbol = ts.split(".")[0]
        name = sr.get("name")
        slim_atr = sr.get("atr14")
        slim_price = sr.get("price")
        try:
            if ts not in cache or len(cache.get(ts) or []) < 30:
                if not args.fetch:
                    raise RuntimeError(
                        f"missing/short bars for {ts} in cache; re-run with --fetch or supply bars"
                    )
                print(f"[{i+1}/{len(universe)}] fetch {ts}", flush=True)
                cache[ts] = fetch_hist(symbol, args.start, args.end)
                time.sleep(0.15)
            bars = cache[ts]
            if not bars:
                raise RuntimeError("empty bars")
            as_of = bars[-1]["date"]
            row = build_structure_row(
                ts_code=ts,
                as_of=as_of,
                opens=[b["open"] for b in bars],
                highs=[b["high"] for b in bars],
                lows=[b["low"] for b in bars],
                closes=[b["close"] for b in bars],
                volumes=[b["volume"] for b in bars],
                name=name,
                atr14_override=float(slim_atr) if slim_atr is not None else None,
                price_override=float(slim_price) if slim_price is not None else None,
            )
            rows_out.append(row)
            print(
                f"  ok {ts} as_of={as_of} dow={row['dow_phase']} "
                f"wy={row['wyckoff_phase']} atr_bucket={row['atr_risk_bucket']}",
                flush=True,
            )
        except Exception as e:  # noqa: BLE001 — collect per-symbol errors into shadow header
            errors.append({"ts_code": ts, "error": f"{type(e).__name__}: {e}"})
            print(f"  FAIL {ts}: {e}", flush=True)

    if args.fetch or cache:
        args.cache.parent.mkdir(parents=True, exist_ok=True)
        args.cache.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    now = datetime.now(tz=SHANGHAI)
    shadow_date = now.strftime("%Y%m%d")
    as_ofs = [r["as_of"] for r in rows_out]
    trading_as_of = max(as_ofs) if as_ofs else shadow_date
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"shadow_{shadow_date}.json"

    payload = {
        "header": {
            "schema_version": "structure_v1",
            "shadow_date": shadow_date,
            "generated_at": now.isoformat(),
            "timezone": "Asia/Shanghai",
            "source_slim": str(args.slim) if args.slim else None,
            "slim_generated_at": (slim_meta or {}).get("generated_at") if isinstance(slim_meta, dict) else None,
            "bar_source": "cache+optional akshare.fund_etf_hist_em(qfq)",
            "atr14_policy": "match slim top-level atr14 when present else Wilder ATR(14)",
            "atr_pct_policy": "atr14 / slim.price (fallback close)",
            "atr_risk_bucket_rule_version": RISK_BUCKET_RULE_VERSION,
            "atr_risk_bucket_rule": {
                "version": RISK_BUCKET_RULE_VERSION,
                "metric": "atr_pct = atr14 / price",
                "bands": {
                    "low": "[0, 0.010)",
                    "mid": "[0.010, 0.020)",
                    "high": "[0.020, 0.035)",
                    "extreme": "[0.035, +inf)",
                    "unknown": "missing atr14 or price",
                },
            },
            "dow_lag_n": 2,
            "research_only": True,
            "grades_unchanged": True,
            "proxies_in_repo": True,
            "universe_target": args.expect_n or len(universe),
            "universe_emitted": len(rows_out),
            "max_bar_as_of": trading_as_of,
            "errors": errors,
        },
        "rows": rows_out,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {out_path} rows={len(rows_out)} errors={len(errors)}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

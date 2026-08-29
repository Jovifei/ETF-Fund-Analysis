#!/usr/bin/env python3
"""Provider capability qualification for real market data.

Structural model: scripts/provider_smoke.py. This script is read-only against
providers -- it never writes the database and never mutates settings.

Field semantics (kept separate on purpose):
  * source_timestamp -- upstream quote time (QuoteRecord.quote_time); may be
    naive. This is the only time eligible as "realtime" evidence.
  * fetched_at       -- local clock time immediately after the fetch call.
  * is_realtime      -- provider's own realtime claim, re-verified here.
  * degraded_reason  -- provider-reported degradation (e.g. daily-close
    fallback); any non-empty reason blocks actionable.
  * verification_status -- actionable verdict from the 8-condition gate
    below; "verified" only when every condition passes.

The 8 actionable conditions (ALL required):
  (a) upstream_timestamp_missing  -- quote_time present
  (b) not_today                   -- source date == local trade day
  (c) outside_price_session       -- source time inside a price session
  (d) timestamp_age               -- fetch/source age in [-5min, +20min]
  (e) invalid_price_volume_amount -- positive price, non-negative volume/amount
  (f) provider_not_timestamp_qualified -- MarketService._qualify_quote_timestamp
  (g) mock_source                 -- provider source must not be mock
  (h) degraded_or_daily_fallback  -- no degraded_reason, no fund_daily source
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.clock import MarketClock  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.providers.factory import create_provider  # noqa: E402
from app.services.market_service import MarketService  # noqa: E402
from app.services.trading_calendar_service import TradingCalendarService  # noqa: E402
from app.utils.reproducibility import current_git_commit  # noqa: E402

FIELD_SEMANTICS = {
    "source_timestamp": "upstream quote time (QuoteRecord.quote_time); the only time eligible as realtime evidence",
    "fetched_at": "local clock time captured immediately after the provider call",
    "verification_status": "actionable verdict from the 8-condition gate; verified only when all conditions pass",
    "is_realtime": "provider's realtime claim, re-verified against the timestamp gate",
    "degraded_reason": "provider-reported degradation; any non-empty value blocks actionable",
}

CONDITION_KEYS = [
    "upstream_timestamp_missing",
    "not_today",
    "outside_price_session",
    "timestamp_age",
    "invalid_price_volume_amount",
    "provider_not_timestamp_qualified",
    "mock_source",
    "degraded_or_daily_fallback",
]


class LatencyTracker:
    def __init__(self) -> None:
        self._samples: dict[str, list[float]] = {}

    def record(self, operation: str, ms: float) -> None:
        self._samples.setdefault(operation, []).append(ms)

    def summary(self) -> dict:
        out: dict[str, dict] = {}
        for operation, values in sorted(self._samples.items()):
            ordered = sorted(values)
            p50 = ordered[len(ordered) // 2] if ordered else 0.0
            p95_idx = max(0, math.ceil(0.95 * len(ordered)) - 1)
            out[operation] = {
                "calls": len(ordered),
                "p50_ms": round(p50, 1),
                "p95_ms": round(ordered[p95_idx], 1),
            }
        return out


def _percentile(values: list[float]) -> tuple[float, float]:
    ordered = sorted(values)
    p50 = ordered[len(ordered) // 2] if ordered else 0.0
    p95_idx = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return p50, ordered[p95_idx]


def _call_with_timeout(func, timeout_seconds: float):
    """Run func() in a worker thread with a hard timeout. Returns (value, error)."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(func)
        try:
            return future.result(timeout=timeout_seconds), None
        except FutureTimeout:
            return None, TimeoutError(f"exceeded {timeout_seconds:.0f}s budget")
        except Exception as exc:  # noqa: BLE001 - qualification tool records everything
            return None, exc


def _bar_quality(bars: list, today: date) -> dict:
    violations = 0
    future_dates = 0
    duplicates = 0
    null_volume = 0
    null_amount = 0
    seen_dates: set[date] = set()
    first_date: date | None = None
    last_date: date | None = None
    for bar in bars:
        if first_date is None or bar.trade_date < first_date:
            first_date = bar.trade_date
        if last_date is None or bar.trade_date > last_date:
            last_date = bar.trade_date
        if bar.trade_date > today:
            future_dates += 1
        if bar.trade_date in seen_dates:
            duplicates += 1
        seen_dates.add(bar.trade_date)
        try:
            o, h, l, c = float(bar.open), float(bar.high), float(bar.low), float(bar.close)
            if not (h >= max(o, c) and l <= min(o, c) and o > 0 and h > 0 and l > 0 and c > 0):
                violations += 1
        except (TypeError, ValueError):
            violations += 1
        if bar.volume is None:
            null_volume += 1
        if bar.amount is None:
            null_amount += 1
    return {
        "ohlc_violations": violations,
        "future_date_violations": future_dates,
        "duplicate_trade_dates": duplicates,
        "null_volume_count": null_volume,
        "null_amount_count": null_amount,
        "first_trade_date": first_date.isoformat() if first_date else None,
        "last_trade_date": last_date.isoformat() if last_date else None,
    }


def _actionable_verdict(quote, fetched_at: datetime, clock: MarketClock, trade_day: bool) -> dict:
    failed: list[str] = []
    source = str(quote.source or "")
    source_lower = source.lower()
    source_time = quote.quote_time
    if source_time is None:
        failed.append("upstream_timestamp_missing")
        source_time_local = None
    else:
        if source_time.tzinfo is None:
            source_time_local = source_time.replace(tzinfo=fetched_at.tzinfo)
        else:
            source_time_local = source_time.astimezone(fetched_at.tzinfo)
        if source_time_local.date() != fetched_at.date():
            failed.append("not_today")
        if not clock.price_session_open(source_time_local, is_trade_day=True):
            failed.append("outside_price_session")
        age = fetched_at - source_time_local
        if not (timedelta(minutes=-5) <= age <= timedelta(minutes=20)):
            failed.append("timestamp_age")
    # price/volume/amount validity
    price_ok = quote.price is not None and math.isfinite(float(quote.price)) and float(quote.price) > 0
    volume = quote.volume
    volume_ok = volume is not None and math.isfinite(float(volume)) and float(volume) >= 0
    amount = quote.amount
    amount_ok = amount is not None and math.isfinite(float(amount)) and float(amount) >= 0
    if not (price_ok and volume_ok and amount_ok):
        failed.append("invalid_price_volume_amount")
    # provider timestamp qualification (reuses the production gate verbatim)
    verified, _reason = MarketService._qualify_quote_timestamp(quote, fetched_at)
    if not verified:
        failed.append("provider_not_timestamp_qualified")
    if "mock" in source_lower:
        failed.append("mock_source")
    if quote.degraded_reason or "fund_daily" in source_lower:
        failed.append("degraded_or_daily_fallback")
    # trade_day False means today is not a trading day per calendar
    if not trade_day:
        failed.append("outside_price_session")
    failed = list(dict.fromkeys(failed))  # keep first-seen order, drop duplicates
    return {
        "ts_code": quote.ts_code,
        "source": source,
        "source_timestamp": source_time_local.isoformat() if source_time_local else None,
        "fetched_at": fetched_at.isoformat(),
        "is_realtime_claim": bool(quote.is_realtime),
        "degraded_reason": quote.degraded_reason,
        "actionable": not failed,
        "failed_conditions": failed,
    }


def _run_bars_check(provider, codes: list[str], history_years: int, sample_size: int,
                    tracker: LatencyTracker, timeout_seconds: float, today: date) -> dict:
    start = today - timedelta(days=history_years * 365 + 30)
    per_code: dict[str, dict] = {}
    for code in codes[:sample_size]:
        began = time.perf_counter()
        bars, error = _call_with_timeout(
            lambda c=code: provider.fetch_daily_bars(c, start, today), timeout_seconds
        )
        tracker.record("fetch_daily_bars", (time.perf_counter() - began) * 1000)
        if error is not None:
            per_code[code] = {"ok": False, "error": f"{type(error).__name__}: {error}"[:200]}
            continue
        quality = _bar_quality(bars or [], today)
        per_code[code] = {
            "ok": bool(bars) and quality["ohlc_violations"] == 0
                  and quality["future_date_violations"] == 0,
            "record_count": len(bars or []),
            "source": bars[-1].source if bars else None,
            "units_note": "volume/amount as reported by provider, unconverted",
            **quality,
        }
    ok_count = sum(1 for item in per_code.values() if item.get("ok"))
    return {"ok": ok_count > 0, "checked": len(per_code), "ok_count": ok_count, "per_code": per_code}


def _run_quotes_check(provider, codes: list[str], tracker: LatencyTracker,
                      timeout_seconds: float) -> tuple[dict, list]:
    began = time.perf_counter()
    quotes, error = _call_with_timeout(
        lambda: provider.fetch_spot_quotes(codes[:3]), timeout_seconds
    )
    tracker.record("fetch_spot_quotes", (time.perf_counter() - began) * 1000)
    if error is not None:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"[:200]}, []
    quotes = quotes or []
    return (
        {
            "ok": bool(quotes),
            "count": len(quotes),
            "sources": sorted({str(q.source) for q in quotes}),
            "realtime_claim_count": sum(1 for q in quotes if q.is_realtime),
            "degraded_count": sum(1 for q in quotes if q.degraded_reason),
        },
        list(quotes),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider capability qualification")
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--history-years", type=int, default=5)
    parser.add_argument("--output", type=str, default="deployment_reports/provider-qualification.json")
    parser.add_argument("--provider", choices=["tushare", "akshare", "composite", "mock"], default=None)
    parser.add_argument("--allow-mock-check", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()

    settings = get_settings()
    provider_name = args.provider or settings.market_provider
    tracker = LatencyTracker()
    clock = MarketClock()
    today = date.today()
    report: dict = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "git_commit_sha": current_git_commit(),
        "provider": provider_name,
        "tushare_token_present": bool(settings.tushare_token),
        "field_semantics": FIELD_SEMANTICS,
        "actionable_conditions": CONDITION_KEYS,
        "status": "ok",
    }

    if provider_name == "mock" and not args.allow_mock_check:
        report["status"] = "mock_refused"
        report["reason"] = "mock provider can never be qualification evidence; pass --allow-mock-check for structure checks only"
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"status": report["status"], "reason": report["reason"]}, ensure_ascii=False))
        return 3

    watchlist = settings.load_watchlist()["instruments"]
    codes = [item["ts_code"] for item in watchlist if item.get("enabled", True)]

    # Trading calendar for today
    try:
        decision = TradingCalendarService(settings).decision(today)
        trade_day = bool(decision.is_trade_day and decision.verified)
        report["trade_calendar"] = {
            "ok": True, "is_trade_day": decision.is_trade_day,
            "verified": decision.verified, "source": decision.source, "reason": decision.reason,
        }
    except Exception as exc:  # noqa: BLE001
        trade_day = False
        report["trade_calendar"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}

    # Resolve provider instance
    try:
        provider = create_provider(settings)
    except Exception as exc:  # noqa: BLE001
        report["status"] = "structural_failure"
        report["provider_error"] = f"{type(exc).__name__}: {exc}"[:200]
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print("provider construction failed", file=sys.stderr)
        return 2

    token_present = bool(settings.tushare_token)
    needs_tushare = provider_name in ("tushare", "composite")
    if needs_tushare and not token_present:
        report["status"] = "token_missing"
        report["tushare"] = {"status": "token_missing"}
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"status": "token_missing"}, ensure_ascii=False))
        return 3

    all_quotes: list = []
    sections: dict[str, dict] = {}

    # --- instruments ---
    began = time.perf_counter()
    instruments, error = _call_with_timeout(lambda: provider.list_instruments(codes[:5]), args.timeout_seconds)
    tracker.record("list_instruments", (time.perf_counter() - began) * 1000)
    if error is not None:
        sections["instruments"] = {"ok": False, "error": f"{type(error).__name__}: {error}"[:200]}
    else:
        instruments = instruments or []
        sections["instruments"] = {
            "ok": bool(instruments),
            "count": len(instruments),
            "sample": [{"ts_code": i.ts_code, "name": i.name} for i in instruments[:3]],
        }

    # --- daily bars ---
    sections["daily_bars"] = _run_bars_check(
        provider, codes, args.history_years, args.sample_size, tracker, args.timeout_seconds, today
    )

    # --- quotes (also feeds actionable verdicts) ---
    quotes_summary, quotes = _run_quotes_check(provider, codes, tracker, args.timeout_seconds)
    sections["quotes"] = quotes_summary
    all_quotes.extend(quotes)

    # --- news ---
    began = time.perf_counter()
    news, error = _call_with_timeout(lambda: provider.fetch_news(24), args.timeout_seconds)
    tracker.record("fetch_news", (time.perf_counter() - began) * 1000)
    if error is not None:
        sections["news"] = {"ok": False, "error": f"{type(error).__name__}: {error}"[:200]}
    else:
        news = news or []
        sections["news"] = {
            "ok": True,
            "count": len(news),
            "sample_titles": [n.title[:40] for n in news[:3]],
        }

    # --- composite trace ---
    if provider_name == "composite" and hasattr(provider, "last_trace"):
        trace_counts: dict[str, dict] = {}
        for trace in provider.last_trace or []:
            entry = trace_counts.setdefault(trace.operation, {})
            entry[trace.status] = entry.get(trace.status, 0) + 1
        sections["composite_trace"] = {
            "ok": True,
            "operations": trace_counts,
            "traces": [t.to_dict() for t in (provider.last_trace or [])],
        }

    report["sections"] = sections

    # --- actionable verdicts ---
    verdicts = []
    now_local = clock.now()
    for quote in all_quotes:
        verdicts.append(_actionable_verdict(quote, now_local, clock, trade_day))
    report["realtime_actionable"] = {
        "verdicts": verdicts,
        "summary": {
            "checked": len(verdicts),
            "actionable_count": sum(1 for v in verdicts if v["actionable"]),
        },
    }
    report["latency"] = tracker.summary()

    core_ok = bool(sections.get("instruments", {}).get("ok")) and bool(
        sections.get("daily_bars", {}).get("ok")
    )
    report["status"] = "ok" if core_ok else "structural_failure"

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "provider": provider_name,
                "tushare_token_present": token_present,
                "actionable": report["realtime_actionable"]["summary"],
                "output": args.output,
            },
            ensure_ascii=False,
        )
    )
    return 0 if core_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

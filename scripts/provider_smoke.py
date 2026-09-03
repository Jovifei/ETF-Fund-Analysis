#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta

from app.core.config import get_settings
from app.providers.factory import create_provider
from app.services.market_service import MarketService


def main() -> int:
    settings = get_settings()
    provider = create_provider(settings)
    result: dict = {
        "provider": provider.name,
        "configured_market_provider": settings.market_provider,
        "tushare_token_present": bool(settings.tushare_token),
        "checks": {},
    }
    codes = [item["ts_code"] for item in settings.load_watchlist()["instruments"] if item.get("enabled", True)]
    try:
        instruments = provider.list_instruments(codes[:5])
        result["checks"]["instruments"] = {"ok": bool(instruments), "count": len(instruments)}
    except Exception as exc:
        result["checks"]["instruments"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        end = date.today()
        bars = provider.fetch_daily_bars(codes[0], end - timedelta(days=45), end)
        result["checks"]["daily_bars"] = {
            "ok": len(bars) >= 15,
            "count": len(bars),
            "latest": bars[-1].trade_date.isoformat() if bars else None,
            "source": bars[-1].source if bars else None,
        }
    except Exception as exc:
        result["checks"]["daily_bars"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        quotes = provider.fetch_spot_quotes(codes[:3])
        qualified_at = datetime.now(settings.timezone)
        qualification = [MarketService._qualify_quote_timestamp(item, qualified_at) for item in quotes]
        provider_realtime = sum(int(item.is_realtime and not item.degraded_reason) for item in quotes)
        verified_realtime = sum(
            int(verified and item.is_realtime and not item.degraded_reason)
            for item, (verified, _reason) in zip(quotes, qualification, strict=True)
        )
        reasons = sorted(
            {
                reason
                for _item, (verified, reason) in zip(quotes, qualification, strict=True)
                if not verified and reason
            }
        )
        result["checks"]["quotes"] = {
            "ok": bool(quotes),
            "count": len(quotes),
            # `realtime` now means the same execution-grade qualification used
            # when QuoteSnapshot rows are persisted, not merely a provider flag.
            "realtime": verified_realtime,
            "verified_realtime": verified_realtime,
            "provider_realtime": provider_realtime,
            "qualification_reasons": reasons,
            "degraded": [item.degraded_reason for item in quotes if item.degraded_reason],
            "sources": sorted({item.source for item in quotes}),
        }
    except Exception as exc:
        result["checks"]["quotes"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        news = provider.fetch_news(24)
        result["checks"]["news"] = {"ok": True, "count": len(news), "note": "empty may mean account permission/source unavailable"}
    except Exception as exc:
        result["checks"]["news"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        result["checks"]["trade_calendar"] = {"ok": True, "today_open": provider.is_trade_day(date.today())}
    except Exception as exc:
        result["checks"]["trade_calendar"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    core_ok = bool(result["checks"].get("instruments", {}).get("ok")) and bool(
        result["checks"].get("daily_bars", {}).get("ok")
    )
    if settings.market_provider != "mock" and result["checks"].get("quotes", {}).get("verified_realtime", 0) == 0:
        print("WARNING: no application-qualified execution-grade real-time quote was verified.", file=sys.stderr)
    return 0 if core_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

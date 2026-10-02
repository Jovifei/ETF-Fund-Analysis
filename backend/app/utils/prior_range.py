"""Display-only prior high/low range for the daily chart checkbox.

This is not the audited price-structure box. It exists so a missing snapshot
still has a drawable OHLC range, and it never becomes an actionable signal.
"""
from __future__ import annotations

from math import isfinite
from typing import Any


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def prior_high_low_range(bars: list[dict[str, Any]], *, window: int = 20) -> dict[str, Any] | None:
    usable: list[dict[str, Any]] = []
    for bar in bars:
        high, low = _number(bar.get("high")), _number(bar.get("low"))
        day = str(bar.get("date") or bar.get("trade_date") or "")[:10]
        if high is None or low is None or high < low or low <= 0 or len(day) != 10:
            continue
        usable.append({"date": day, "high": high, "low": low})
    sample = usable[-max(int(window), 1):]
    if len(sample) < 5:
        return None
    upper = max(sample, key=lambda item: (item["high"], item["date"]))
    lower = min(sample, key=lambda item: (item["low"], item["date"]))
    if upper["high"] <= lower["low"]:
        return None
    return {
        "kind": "prior_high_low",
        "qualified": False,
        "actionable": False,
        "persisted": False,
        "window": len(sample),
        "origin_at": sample[0]["date"],
        "valid_until": sample[-1]["date"],
        "upper": upper["high"],
        "lower": lower["low"],
        "upper_date": upper["date"],
        "lower_date": lower["date"],
        "label": "前高前低",
        "disclaimer": "快照缺失时按当前图表最近日线 OHLC 现算的前高前低，不是已审计箱体，不生成操作信号。",
    }

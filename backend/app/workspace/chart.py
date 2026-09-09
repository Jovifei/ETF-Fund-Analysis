"""Chart-only series projection; never produces or overwrites domain decisions.

The existing base indicator module supplies the persisted core indicator values.
In v0.8 the advanced module retains base.values for RSI despite enriching its
frame with other diagnostics. Use this very same base formula for chart parity.
"""
from __future__ import annotations

import copy
import json
import math
from functools import lru_cache

import pandas as pd

from app.utils.indicators import calculate_indicators

CORE_FIELDS = ("ma5", "ma10", "ma20", "ma30", "ma60", "macd_dif", "macd_dea", "macd_hist", "kdj_k", "kdj_d", "kdj_j", "rsi6", "rsi12", "rsi14", "td_buy_setup", "td_sell_setup")


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def build_indicator_series(rows: list[dict], config: dict) -> list[dict]:
    if not rows:
        return []
    frame = pd.DataFrame(rows).rename(columns={"date": "trade_date"})
    result = calculate_indicators(frame, config)
    ordered = sorted(rows, key=lambda row: row["date"])
    # Use unrounded numbers in the wire protocol. Presentation rounds only.
    return [
        {**row, "indicators": {field: number(result.frame.iloc[index].get(field)) for field in CORE_FIELDS}}
        for index, row in enumerate(ordered)
    ]


@lru_cache(maxsize=24)
def _cached(rows_json: str, config_json: str) -> tuple[dict, ...]:
    return tuple(build_indicator_series(json.loads(rows_json), json.loads(config_json)))


def cached_indicator_series(rows: list[dict], config: dict) -> list[dict]:
    # Inputs contain public market bars only. No user/cost/token can enter this
    # bounded cache. Revision of any historic bar invalidates the complete key.
    return copy.deepcopy(list(_cached(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, allow_nan=False),
        json.dumps(config, ensure_ascii=False, sort_keys=True, allow_nan=False),
    )))

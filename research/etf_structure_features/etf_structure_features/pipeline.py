"""Assemble flat structure_v1 fund row. Does not call assign_grade."""

from __future__ import annotations

from typing import Any

from .atr_risk import RISK_BUCKET_RULE_VERSION, atr_features
from .dow_proxy import confirmed_pivots, dow_phase_from_pivots
from .wyckoff_proxy import wyckoff_from_ohlcv

__all__ = ["build_structure_row", "RISK_BUCKET_RULE_VERSION"]


def build_structure_row(
    *,
    ts_code: str,
    as_of: str,
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    name: str | None = None,
    lag_n: int = 2,
    atr14_override: float | None = None,
    price_override: float | None = None,
) -> dict[str, Any]:
    if not closes:
        raise ValueError("closes required")
    as_of_index = len(closes) - 1
    pivots = confirmed_pivots(highs, lows, as_of_index=as_of_index, lag_n=lag_n)
    dow_phase, dow_score, dow_conf, dow_ev = dow_phase_from_pivots(pivots)
    wy_phase, wy_score, wy_conf, wy_ev = wyckoff_from_ohlcv(
        opens, highs, lows, closes, volumes, as_of_index=as_of_index, lag_n=lag_n
    )
    atr14, atr_pct, bucket, atr_ev = atr_features(
        highs, lows, closes,
        as_of_index=as_of_index,
        atr14_override=atr14_override,
        price_override=price_override,
    )
    return {
        "schema_version": "structure_v1",
        "ts_code": ts_code,
        "name": name,
        "as_of": as_of,
        "lag_n": lag_n,
        "wyckoff_phase": wy_phase,
        "wyckoff_score": round(float(wy_score), 4),
        "wyckoff_confidence": round(float(wy_conf), 4),
        "dow_phase": dow_phase,
        "dow_score": round(float(dow_score), 4),
        "dow_confidence": round(float(dow_conf), 4),
        "atr14": atr14,
        "atr_pct": atr_pct,
        "atr_risk_bucket": bucket,
        "evidence": [*dow_ev, *wy_ev, *atr_ev],
        "research_only": True,
        "proxy_disclaimer": "Wyckoff/Dow labels are OHLCV proxies; ETF volume is not underlying flow.",
    }

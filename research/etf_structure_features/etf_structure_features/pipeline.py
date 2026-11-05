"""Assemble one structure_v1 fund row. Does not call assign_grade."""

from __future__ import annotations

from typing import Any

from .atr_risk import atr_features
from .dow_proxy import confirmed_pivots, dow_phase_from_pivots
from .wyckoff_proxy import wyckoff_from_ohlcv


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
) -> dict[str, Any]:
    if not closes:
        raise ValueError("closes required")
    as_of_index = len(closes) - 1
    pivots = confirmed_pivots(highs, lows, as_of_index=as_of_index, lag_n=lag_n)
    dow_phase, dow_score, dow_conf, dow_ev = dow_phase_from_pivots(pivots)
    wy_phase, wy_score, wy_conf, wy_ev = wyckoff_from_ohlcv(
        opens, highs, lows, closes, volumes, as_of_index=as_of_index, lag_n=lag_n
    )
    atr14, atr_pct, bucket, atr_ev = atr_features(highs, lows, closes, as_of_index=as_of_index)
    evidence = [*dow_ev, *wy_ev, *atr_ev]
    return {
        "schema_version": "structure_v1",
        "ts_code": ts_code,
        "name": name,
        "as_of": as_of,
        "lag_n": lag_n,
        "wyckoff_phase": wy_phase,
        "wyckoff_score": wy_score,
        "wyckoff_confidence": wy_conf,
        "dow_phase": dow_phase,
        "dow_score": dow_score,
        "dow_confidence": dow_conf,
        "atr14": atr14,
        "atr_pct": atr_pct,
        "atr_risk_bucket": bucket,
        "evidence": evidence,
        "research_only": True,
        "proxy_disclaimer": (
            "Wyckoff/Dow labels are OHLCV proxies; ETF volume is not underlying flow."
        ),
    }

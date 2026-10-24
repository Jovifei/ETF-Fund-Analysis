from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from app.services.strategy_evaluation.contracts import StrategyResult


def calc_momentum(prices: pd.Series, lookback: int = 120) -> pd.Series:
    """Calculate cumulative return over lookback periods: P(t) / P(t - lookback) - 1."""
    if len(prices) < lookback + 1:
        return pd.Series(index=prices.index, dtype=float)
    return prices / prices.shift(lookback) - 1.0


def calc_volatility_annualized(rets: pd.Series, window: int = 20) -> pd.Series:
    """Calculate rolling annualized realized volatility: std(rets, ddof=1) * sqrt(252)."""
    return rets.rolling(window, min_periods=window).std(ddof=1) * math.sqrt(252)


def compute_volatility_target_weight(
    trend_state: int,
    vol: float,
    target_vol: float = 0.15,
    max_weight: float = 1.0,
) -> float:
    """Compute true volatility target position weight (M2).

    w = 1[trend_state > 0] * min(max_weight, target_vol / vol)
    If trend is flat or down, weight is 0.0 (cash).
    """
    if trend_state <= 0:
        return 0.0
    if pd.isna(vol) or vol <= 0.0 or not math.isfinite(vol):
        return 0.0
    raw_w = target_vol / vol
    return float(min(max_weight, raw_w))


def calc_cross_sectional_ranks(scores: dict[str, float]) -> dict[str, float]:
    """Compute cross-sectional percentile rank [0.0, 1.0] from factor scores."""
    valid = {k: v for k, v in scores.items() if v is not None and not pd.isna(v) and math.isfinite(v)}
    n = len(valid)
    if n == 0:
        return {}
    if n == 1:
        return {next(iter(valid)): 1.0}

    # Sort ascending so highest score gets highest rank
    sorted_items = sorted(valid.items(), key=lambda x: x[1])
    ranks: dict[str, float] = {}
    for idx, (code, _) in enumerate(sorted_items):
        ranks[code] = idx / (n - 1)
    return ranks


def compute_dual_momentum_weights(
    cs_scores: dict[str, float],
    ts_trends: dict[str, int],
    top_k: int = 4,
) -> dict[str, float]:
    """Dual Momentum (C1): Top-K by cross-sectional momentum, gated by absolute momentum.

    If an asset is in the top-K but its 12m trend is flat/negative (ts_trends <= 0),
    its slot is allocated to CASH (weight 0.0), avoiding holding falling assets in bear markets.
    """
    valid_scores = {k: v for k, v in cs_scores.items() if v is not None and not pd.isna(v) and math.isfinite(v)}
    weights: dict[str, float] = {k: 0.0 for k in cs_scores}
    if not valid_scores or top_k <= 0:
        return weights

    sorted_candidates = sorted(valid_scores.items(), key=lambda x: x[1], reverse=True)
    selected = sorted_candidates[:top_k]
    slot_weight = 1.0 / top_k

    for code, _ in selected:
        if ts_trends.get(code, 0) > 0:
            weights[code] = slot_weight
        else:
            weights[code] = 0.0  # Cash filter!

    return weights


class MomentumStrategyEngine:
    """Thin computation engine for momentum and volatility decision factors."""

    def __init__(self, version: str = "20261024_v2") -> None:
        self.version = version

    def evaluate_single_asset_tsmom(
        self,
        ts_code: str,
        df: pd.DataFrame,
        lookback: int = 252,
        vol_lookback: int = 20,
        target_vol: float = 0.15,
        max_weight: float = 1.0,
    ) -> StrategyResult:
        """Evaluate Time Series Momentum (M0/M1/M2) for a single asset."""
        if df.empty or len(df) < lookback + 1:
            trade_date = str(df["trade_date"].iloc[-1]) if not df.empty and "trade_date" in df else "UNKNOWN"
            return StrategyResult.abstain(
                strategy_id="M0_TSMOM_RAW",
                version=self.version,
                trade_date=trade_date,
                ts_code=ts_code,
                reason=f"insufficient_history:bars_count={len(df)}_required={lookback + 1}",
                as_of=f"{trade_date} 15:00:00",
                available_at=f"{trade_date} 17:00:00",
            )

        trade_date = str(df["trade_date"].iloc[-1])
        close_series = df["close"]
        ret_series = df["ret_1"] if "ret_1" in df else close_series.pct_change()

        curr_close = float(close_series.iloc[-1])
        past_close = float(close_series.iloc[-lookback - 1])
        if past_close <= 0 or pd.isna(past_close):
            return StrategyResult.abstain(
                strategy_id="M0_TSMOM_RAW",
                version=self.version,
                trade_date=trade_date,
                ts_code=ts_code,
                reason="invalid_historical_close_price",
                as_of=f"{trade_date} 15:00:00",
                available_at=f"{trade_date} 17:00:00",
            )

        mom_val = curr_close / past_close - 1.0
        trend_state = 1 if mom_val > 0 else 0

        # Realized volatility
        recent_rets = ret_series.iloc[-vol_lookback:]
        vol = float(recent_rets.std(ddof=1) * math.sqrt(252)) if len(recent_rets) >= vol_lookback else float("nan")

        target_weight = compute_volatility_target_weight(
            trend_state=trend_state,
            vol=vol,
            target_vol=target_vol,
            max_weight=max_weight,
        )

        return StrategyResult(
            strategy_id="M2_TSMOM_VOL_TARGET",
            version=self.version,
            trade_date=trade_date,
            ts_code=ts_code,
            signal_score=round(mom_val, 6),
            rank_percentile=None,
            trend_state=trend_state,
            target_weight=round(target_weight, 4),
            qualification="research_candidate",
            as_of=f"{trade_date} 15:00:00",
            available_at=f"{trade_date} 17:00:00",
            research_only=True,
            actionable=False,
        )

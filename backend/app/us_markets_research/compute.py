"""Deterministic metrics for the US research block (no LLM, no randomness).

Baskets are equal-weight, daily-rebalanced over members that have a valid
adjusted close on both the day and the prior day (at least ``min_members``).
Structure columns reuse the repo's own ``research/etf_structure_features``
rules (``atr_pct_fixed_v1`` bands, confirmed-pivot Dow proxy, OHLCV Wyckoff
proxy); nothing here touches grading.
"""
from __future__ import annotations

import math
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.us_markets_research.providers import CLOSE_SOURCE_PROVISIONAL

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PKG_PARENT = _REPO_ROOT / "research" / "etf_structure_features"

WINDOWS = {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252}
SPARK_POINTS = 252
RS_MIN_OVERLAP = 30


@lru_cache(maxsize=1)
def _structure_rules():
    """Soft-import the repo structure rules; ``None`` when unavailable."""
    if not _PKG_PARENT.is_dir():
        return None
    if str(_PKG_PARENT) not in sys.path:
        sys.path.insert(0, str(_PKG_PARENT))
    try:
        from etf_structure_features import atr_risk, dow_proxy, wyckoff_proxy  # type: ignore
        return atr_risk, dow_proxy, wyckoff_proxy
    except Exception:
        return None


def clean(value: Any, digits: int | None = 6) -> Any:
    """JSON-safe number: NaN/inf -> None, numpy -> python, optional rounding."""
    if value is None:
        return None
    if isinstance(value, (np.floating, float)):
        value = float(value)
        if not math.isfinite(value):
            return None
        return round(value, digits) if digits is not None else value
    if isinstance(value, (np.integer,)):
        return int(value)
    return value


def equal_weight_basket(frames: dict[str, pd.DataFrame], members: list[str],
                        min_members: int = 3) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return basket OHLC levels (first valid day = 100) and coverage metadata."""
    close = {m: frames[m]["close"][frames[m]["close"] > 0] for m in members if m in frames and not frames[m].empty}
    if not close:
        return pd.DataFrame(), {"error": "no_member_data"}
    close_df = pd.DataFrame(close).sort_index()
    valid = close_df.notna() & close_df.shift(1).notna()
    n_members = valid.sum(axis=1)
    expected = pd.DataFrame({m: close_df.index > close_df[m].first_valid_index()
                             for m in close_df.columns}, index=close_df.index).sum(axis=1)
    enough = (n_members >= min_members) & (n_members == expected)
    # Missing an entire requested member is not permission to invent a smaller basket.
    if set(members) - set(close_df.columns):
        return pd.DataFrame(), {"error": "missing_requested_members", "missing_members": sorted(set(members) - set(close_df.columns))}

    def mean_ret(column: str) -> pd.Series:
        parts = []
        for m in close_df.columns:
            level = frames[m][column].reindex(close_df.index)
            ret = level / close_df[m].shift(1) - 1.0
            parts.append(ret.where(valid[m]))
        return pd.concat(parts, axis=1).mean(axis=1).where(enough)

    ret_close = mean_ret("close")
    first = ret_close.first_valid_index()
    if first is None:
        return pd.DataFrame(), {"error": "fewer_than_min_members_overlap", "min_members": min_members}
    # A gap cannot be interpreted as a 0% return. Publish only the contiguous
    # prefix before it; never silently reweight around a missing quote or chain
    # the next day's return across a missing day.
    usable = ret_close.loc[first:]
    gaps = usable[usable.isna()]
    gap_date = str(gaps.index[0].date()) if not gaps.empty else None
    if not gaps.empty:
        usable = usable.loc[usable.index < gaps.index[0]]
    level = (1.0 + usable).cumprod()
    level = level / level.iloc[0] * 100.0
    prev = level.shift(1)
    out = pd.DataFrame({"close": level, "n_members": n_members.reindex(level.index)})
    for column in ("open", "high", "low"):
        out[column] = prev * (1.0 + mean_ret(column).reindex(level.index))
    out.loc[first, ["open", "high", "low"]] = out.loc[first, "close"]
    out["high"] = out[["open", "high", "low", "close"]].max(axis=1)
    out["low"] = out[["open", "high", "low", "close"]].min(axis=1)
    provisional = pd.DataFrame({
        m: (frames[m]["close_source"].reindex(close_df.index) == CLOSE_SOURCE_PROVISIONAL) & valid[m]
        for m in close_df.columns}).any(axis=1)
    out["provisional"] = provisional.reindex(out.index).fillna(False)
    out["volume"] = np.nan
    presence = {m: {"first": str(close_df[m].first_valid_index().date()) if close_df[m].notna().any() else None,
                    "last": str(close_df[m].last_valid_index().date()) if close_df[m].notna().any() else None,
                    "rows": int(close_df[m].notna().sum())} for m in close_df.columns}
    missing = [m for m in members if m not in close_df.columns]
    return out, {"presence": presence, "missing_members": missing, "min_members": min_members,
                 "first_gap_date": gap_date, "published_through": str(out.index[-1].date())}


def period_return(close: pd.Series, bars: int) -> float | None:
    s = close.dropna()
    if len(s) <= bars:
        return None
    base = float(s.iloc[-(bars + 1)])
    return None if base == 0 else float(s.iloc[-1] / base - 1.0)


def ytd_return(close: pd.Series) -> float | None:
    s = close.dropna()
    if s.empty:
        return None
    year = s.index[-1].year
    before = s[s.index < pd.Timestamp(year, 1, 1)]
    if before.empty:
        return None  # no prior-year close: refuse to invent a base (series listed this year)
    base = float(before.iloc[-1])
    return None if base == 0 else float(s.iloc[-1] / base - 1.0)


def drawdown(close: pd.Series) -> dict[str, Any]:
    s = close.dropna()
    if s.empty:
        return {"current": None, "max": None, "peak_date": None, "trough_date": None}
    dd = s / s.cummax() - 1.0
    trough = dd.idxmin()
    return {"current": clean(dd.iloc[-1]), "max": clean(dd.min()),
            "peak_date": str(s.loc[:trough].idxmax().date()), "trough_date": str(trough.date())}


def ma_gap(close: pd.Series, window: int) -> float | None:
    s = close.dropna()
    if len(s) < window:
        return None
    ma = float(s.rolling(window).mean().iloc[-1])
    return None if ma == 0 else float(s.iloc[-1] / ma - 1.0)


def relative_strength(series: pd.Series, bench: pd.Series) -> dict[str, Any] | None:
    # Prices align on common dates; daily correlation uses adjacent UNION sessions,
    # not pct_change after dropping unmatched dates (which creates multi-day returns).
    union = pd.concat([series.rename("series"), bench.rename("benchmark")], axis=1).sort_index()
    common = union.dropna()
    if len(common) < RS_MIN_OVERLAP:
        return None
    start, end = common.index[0], common.index[-1]
    window = union.loc[start:end]
    pair = window.pct_change(fill_method=None).dropna()
    a, b = common.iloc[:, 0], common.iloc[:, 1]
    excess = {}
    for key, bars in WINDOWS.items():
        # Fixed session horizons only when all union sessions in the window exist.
        w = window.tail(bars + 1)
        excess[key] = clean(float(w.iloc[-1,0]/w.iloc[0,0] - w.iloc[-1,1]/w.iloc[0,1])) if len(w) == bars + 1 and w.notna().all().all() else None
    ya, yb = ytd_return(a), ytd_return(b)
    excess["ytd"] = clean(ya-yb) if ya is not None and yb is not None else None
    corr = pair.iloc[:,0].corr(pair.iloc[:,1]) if len(pair) >= RS_MIN_OVERLAP else None
    return {"excess": excess, "daily_return_corr": clean(corr,4), "n_overlap": len(common),
            "first_overlap": str(start.date()), "last_overlap": str(end.date()),
            "n_price_pairs": len(common), "n_daily_return_pairs": len(pair),
            "n_union_sessions": len(window), "n_missing_sessions": int(window.isna().any(axis=1).sum()),
            "sample_policy": "common_prices; daily_returns_on_adjacent_union_sessions_no_fill"}


def structure_columns(df: pd.DataFrame, *, with_volume: bool) -> dict[str, Any]:
    """ATR bucket (atr_pct_fixed_v1), Dow proxy and (indices only) Wyckoff proxy."""
    rules = _structure_rules()
    base = {"atr14": None, "atr_pct": None, "atr_risk_bucket": "unknown", "atr_rule": None,
            "dow_phase": "unknown", "dow_score": None, "wyckoff_phase": "not_computed", "wyckoff_score": None,
            "structure_note": "structure rules unavailable" if rules is None else None}
    if rules is None or len(df) < 20:
        return base
    atr_risk, dow_proxy, wyckoff_proxy = rules
    highs, lows, closes = df["high"].tolist(), df["low"].tolist(), df["close"].tolist()
    opens = df["open"].tolist()
    last = len(closes) - 1
    atr14, atr_pct, bucket, _ = atr_risk.atr_features(highs, lows, closes, as_of_index=last)
    pivots = dow_proxy.confirmed_pivots(highs, lows, as_of_index=last)
    dow_phase, dow_score, _, _ = dow_proxy.dow_phase_from_pivots(pivots)
    out = {**base, "atr14": clean(atr14), "atr_pct": clean(atr_pct), "atr_risk_bucket": bucket,
           "atr_rule": atr_risk.RISK_BUCKET_RULE_VERSION, "dow_phase": dow_phase, "dow_score": clean(dow_score, 3),
           "structure_note": None}
    volumes = df["volume"].tolist()
    if with_volume and sum(1 for v in df["volume"].tail(60) if v and v > 0) >= 20:
        vols = [float(v) if v and v == v else 0.0 for v in volumes]
        phase, score, _, _ = wyckoff_proxy.wyckoff_from_ohlcv(opens, highs, lows, closes, vols, as_of_index=last)
        out.update(wyckoff_phase=phase, wyckoff_score=clean(score, 3))
    return out


def series_entry(*, series_id: str, label: str, group_id: str, kind: str, df: pd.DataFrame,
                 with_volume: bool, benchmarks: dict[str, pd.Series], source_label: str,
                 extra: dict[str, Any]) -> dict[str, Any]:
    close = df["close"].dropna()
    last_provisional = bool(df["provisional"].iloc[-1]) if "provisional" in df.columns and len(df) else False
    entry: dict[str, Any] = {
        "series_id": series_id, "label": label, "group_id": group_id, "kind": kind, "available": True,
        "as_of": str(close.index[-1].date()), "first_date": str(close.index[0].date()), "n_bars": int(len(close)),
        "level": clean(close.iloc[-1], 4),
        "source_label": source_label,
        "provisional_last_close": last_provisional,
        "returns": {**{k: clean(period_return(close, n), 6) for k, n in WINDOWS.items()}, "ytd": clean(ytd_return(close), 6)},
        "drawdown": drawdown(close),
        "ma_gap": {"ma20": clean(ma_gap(close, 20)), "ma60": clean(ma_gap(close, 60)), "ma120": clean(ma_gap(close, 120))},
        **structure_columns(df, with_volume=with_volume),
        "rs": {f"vs_{role}": relative_strength(close, bench.dropna()) for role, bench in benchmarks.items()},
        "spark": [[str(i.date()), round(float(v), 2)] for i, v in (close.tail(SPARK_POINTS) / close.tail(SPARK_POINTS).iloc[0] * 100).items()],
        "research_only": True, "actionable": False, "calibration_status": "not_calibrated",
        **extra,
    }
    entry["rs"] = {key: value for key, value in entry["rs"].items() if value is not None}
    return entry

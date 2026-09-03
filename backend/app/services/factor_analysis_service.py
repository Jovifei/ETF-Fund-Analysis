from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import DailyBar, Instrument, ReportArtifact
from app.services.event_service import emit_event
from app.utils.feature_store import add_cross_sectional_features, build_feature_frame
from app.utils.hashing import stable_hash
from app.utils.horizons import aligned_research_horizons

OSS_RESEARCH_FACTORS = (
    "linear_slope_20",
    "trend_r2_20",
    "trend_residual_20",
    "time_since_high_20",
    "time_since_low_20",
    "up_day_fraction_20",
    "down_day_fraction_20",
    "return_volume_corr_20",
    "benchmark_beta_60",
    "benchmark_corr_60",
)

DEFAULT_FACTORS = (
    "return_5d",
    "return_20d",
    "return_60d",
    "ma_gap_5_20",
    "ma_gap_20_60",
    "macd_norm",
    "kdj_j",
    "rsi14",
    "atr_pct",
    "volume_ratio",
    "amount_ratio",
    "obv_slope_5",
    "mfi14",
    "cmf20",
    "adx14",
    "cci20",
    "wr14",
    "roc12",
    "rsrs_zscore",
    "box_position_20",
    "box_position_55",
    "pullback_ready",
    "second_launch",
    "rps20",
    "rps60",
    "rps120",
    "vp_peak_distance",
    "cost50_distance",
    "profit_ratio_est",
    "chip_concentration",
    *OSS_RESEARCH_FACTORS,
)


@dataclass(frozen=True, slots=True)
class FactorMetric:
    factor: str
    horizon: int
    coverage: float
    ic_mean: float | None
    rank_ic_mean: float | None
    rank_ic_std: float | None
    icir: float | None
    top_bottom_spread: float | None
    top_quantile_turnover: float | None
    observation_dates: int

    def model_dump(self) -> dict:
        return {
            "factor": self.factor,
            "horizon": self.horizon,
            "coverage": self.coverage,
            "ic_mean": self.ic_mean,
            "rank_ic_mean": self.rank_ic_mean,
            "rank_ic_std": self.rank_ic_std,
            "icir": self.icir,
            "top_bottom_spread": self.top_bottom_spread,
            "top_quantile_turnover": self.top_quantile_turnover,
            "observation_dates": self.observation_dates,
        }


def _finite(value: float | None, digits: int = 6) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """Return deterministic average ranks without a SciPy dependency."""
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    cursor = 0
    while cursor < len(order):
        stop = cursor + 1
        while stop < len(order) and values[order[stop]] == values[order[cursor]]:
            stop += 1
        average = (cursor + 1 + stop) / 2.0
        ranks[order[cursor:stop]] = average
        cursor = stop
    return ranks


def _safe_corr(left: np.ndarray, right: np.ndarray) -> float | None:
    if len(left) < 4 or np.ptp(left) == 0 or np.ptp(right) == 0:
        return None
    left_centered = left - left.mean()
    right_centered = right - right.mean()
    denominator = float(
        np.sqrt(
            np.dot(left_centered, left_centered)
            * np.dot(right_centered, right_centered)
        )
    )
    if denominator <= 0:
        return None
    value = float(np.dot(left_centered, right_centered) / denominator)
    return value if math.isfinite(value) else None


def _rolling_linear_window(values: np.ndarray) -> tuple[float, float, float]:
    """Return normalized log-price slope, R² and current residual for one past-only window."""
    values = np.asarray(values, dtype=float)
    if len(values) < 4 or not np.isfinite(values).all() or np.any(values <= 0):
        return np.nan, np.nan, np.nan
    y = np.log(values)
    x = np.arange(len(y), dtype=float)
    x_centered = x - x.mean()
    y_centered = y - y.mean()
    denominator = float(np.dot(x_centered, x_centered))
    if denominator <= 0:
        return np.nan, np.nan, np.nan
    slope = float(np.dot(x_centered, y_centered) / denominator)
    intercept = float(y.mean() - slope * x.mean())
    fitted = intercept + slope * x
    ss_tot = float(np.dot(y_centered, y_centered))
    ss_res = float(np.dot(y - fitted, y - fitted))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    residual = float(y[-1] - fitted[-1])
    return slope, r2, residual


def _add_instrument_research_factors(group: pd.DataFrame) -> pd.DataFrame:
    result = group.sort_values("trade_date").copy()
    close = result["close"].astype(float)
    volume = result["volume"].astype(float).replace(0, np.nan)
    daily_return = close.pct_change()
    volume_change = np.log(volume).diff()

    slopes = np.full(len(result), np.nan)
    r2s = np.full(len(result), np.nan)
    residuals = np.full(len(result), np.nan)
    close_values = close.to_numpy(dtype=float)
    for end in range(19, len(result)):
        slope, r2, residual = _rolling_linear_window(close_values[end - 19 : end + 1])
        slopes[end] = slope
        r2s[end] = r2
        residuals[end] = residual
    result["linear_slope_20"] = slopes
    result["trend_r2_20"] = r2s
    result["trend_residual_20"] = residuals

    def since_high(values: pd.Series) -> float:
        array = values.to_numpy(dtype=float)
        if not np.isfinite(array).any():
            return np.nan
        return float(len(array) - 1 - int(np.nanargmax(array)))

    def since_low(values: pd.Series) -> float:
        array = values.to_numpy(dtype=float)
        if not np.isfinite(array).any():
            return np.nan
        return float(len(array) - 1 - int(np.nanargmin(array)))

    result["time_since_high_20"] = close.rolling(20, min_periods=20).apply(since_high, raw=False)
    result["time_since_low_20"] = close.rolling(20, min_periods=20).apply(since_low, raw=False)
    result["up_day_fraction_20"] = (
        daily_return.gt(0).astype(float).where(daily_return.notna()).rolling(20, min_periods=20).mean()
    )
    result["down_day_fraction_20"] = (
        daily_return.lt(0).astype(float).where(daily_return.notna()).rolling(20, min_periods=20).mean()
    )
    result["return_volume_corr_20"] = daily_return.rolling(20, min_periods=20).corr(volume_change)
    return result


def add_oss_research_factor_diagnostics(panel: pd.DataFrame, benchmark_code: str) -> pd.DataFrame:
    """Add point-in-time research-only factors inspired by Qlib/ETF literature.

    These columns are deliberately added only inside factor analysis. They are
    not part of `feature_columns_for_horizon()` and therefore cannot change the
    production similarity forecast or the canonical five-grade action.
    """
    if panel.empty:
        return panel.copy()
    result = (
        panel.groupby("ts_code", observed=True, group_keys=False)
        .apply(_add_instrument_research_factors, include_groups=False)
        .reset_index(drop=True)
    )
    # groupby.apply with include_groups=False removes the grouping column; restore
    # identity deterministically from the original per-code groups when needed.
    if "ts_code" not in result.columns:
        rebuilt: list[pd.DataFrame] = []
        for code, group in panel.groupby("ts_code", observed=True, sort=False):
            enriched = _add_instrument_research_factors(group)
            enriched["ts_code"] = str(code)
            rebuilt.append(enriched)
        result = pd.concat(rebuilt, ignore_index=True)

    benchmark = result.loc[
        result["ts_code"] == benchmark_code, ["trade_date", "return_1d"]
    ].rename(columns={"return_1d": "benchmark_return_1d"})
    result = result.merge(benchmark, on="trade_date", how="left", validate="many_to_one")

    def add_beta_corr(group: pd.DataFrame) -> pd.DataFrame:
        group = group.sort_values("trade_date").copy()
        left = group["return_1d"].astype(float)
        right = group["benchmark_return_1d"].astype(float)
        covariance = left.rolling(60, min_periods=40).cov(right)
        variance = right.rolling(60, min_periods=40).var()
        group["benchmark_beta_60"] = covariance / variance.replace(0, np.nan)
        group["benchmark_corr_60"] = left.rolling(60, min_periods=40).corr(right)
        return group

    result = (
        result.groupby("ts_code", observed=True, group_keys=False)
        .apply(add_beta_corr, include_groups=False)
        .reset_index(drop=True)
    )
    if "ts_code" not in result.columns:
        # Pandas may omit grouping columns when include_groups=False. Rebuild once
        # with explicit identity instead of relying on a version-specific apply detail.
        rebuilt = []
        for code, group in panel.groupby("ts_code", observed=True, sort=False):
            enriched = _add_instrument_research_factors(group)
            enriched["ts_code"] = str(code)
            rebuilt.append(enriched)
        result = pd.concat(rebuilt, ignore_index=True)
        benchmark = result.loc[
            result["ts_code"] == benchmark_code, ["trade_date", "return_1d"]
        ].rename(columns={"return_1d": "benchmark_return_1d"})
        result = result.merge(benchmark, on="trade_date", how="left", validate="many_to_one")
        rebuilt = []
        for code, group in result.groupby("ts_code", observed=True, sort=False):
            enriched = add_beta_corr(group)
            enriched["ts_code"] = str(code)
            rebuilt.append(enriched)
        result = pd.concat(rebuilt, ignore_index=True)
    return result


def _daily_correlations(
    panel: pd.DataFrame, factor: str, target: str
) -> tuple[list[float], list[float]]:
    pearson: list[float] = []
    spearman: list[float] = []
    clean = (
        panel[["trade_date", factor, target]]
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    for _, group in clean.groupby("trade_date", observed=True, sort=False):
        left = group[factor].to_numpy(dtype=float, copy=False)
        right = group[target].to_numpy(dtype=float, copy=False)
        p = _safe_corr(left, right)
        s = _safe_corr(_average_ranks(left), _average_ranks(right))
        if p is not None:
            pearson.append(p)
        if s is not None:
            spearman.append(s)
    return pearson, spearman


def _quantile_spread_and_turnover(
    panel: pd.DataFrame, factor: str, target: str
) -> tuple[float | None, float | None]:
    spreads: list[float] = []
    previous_top: set[str] | None = None
    turnovers: list[float] = []
    clean = (
        panel[["trade_date", "ts_code", factor, target]]
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    for _, group in clean.groupby("trade_date", observed=True, sort=False):
        values = group[factor].to_numpy(dtype=float, copy=False)
        targets = group[target].to_numpy(dtype=float, copy=False)
        unique_count = len(np.unique(values))
        if len(values) < 5 or unique_count < 3:
            continue
        quantiles = min(5, unique_count)
        order = np.argsort(values, kind="mergesort")
        bins = np.empty(len(values), dtype=int)
        bins[order] = np.minimum(
            quantiles - 1,
            np.arange(len(values)) * quantiles // len(values),
        )
        bottom_mask = bins == 0
        top_mask = bins == quantiles - 1
        if not bottom_mask.any() or not top_mask.any():
            continue
        spreads.append(
            float(targets[top_mask].mean() - targets[bottom_mask].mean())
        )
        codes = group["ts_code"].astype(str).to_numpy(copy=False)
        top_set = set(codes[top_mask])
        if previous_top is not None and (top_set or previous_top):
            overlap = len(top_set & previous_top) / max(
                1, len(top_set | previous_top)
            )
            turnovers.append(1.0 - overlap)
        previous_top = top_set
    return (
        _finite(float(np.mean(spreads))) if spreads else None,
        _finite(float(np.mean(turnovers))) if turnovers else None,
    )


def factor_metric(panel: pd.DataFrame, factor: str, horizon: int) -> FactorMetric:
    target = f"forward_return_{horizon}"
    usable = panel[["trade_date", "ts_code", factor, target]].replace([np.inf, -np.inf], np.nan)
    coverage = float(usable[factor].notna().mean()) if len(usable) else 0.0
    pearson, spearman = _daily_correlations(usable, factor, target)
    spread, turnover = _quantile_spread_and_turnover(usable, factor, target)
    rank_mean = float(np.mean(spearman)) if spearman else None
    rank_std = float(np.std(spearman, ddof=1)) if len(spearman) > 1 else None
    icir = rank_mean / rank_std if rank_mean is not None and rank_std and rank_std > 0 else None
    return FactorMetric(
        factor=factor,
        horizon=horizon,
        coverage=round(coverage, 6),
        ic_mean=_finite(float(np.mean(pearson))) if pearson else None,
        rank_ic_mean=_finite(rank_mean),
        rank_ic_std=_finite(rank_std),
        icir=_finite(icir),
        top_bottom_spread=spread,
        top_quantile_turnover=turnover,
        observation_dates=len(spearman),
    )


def _regime_labels(panel: pd.DataFrame, benchmark_code: str) -> pd.Series:
    benchmark = panel.loc[panel["ts_code"] == benchmark_code, ["trade_date", "return_20d", "volatility_20d"]]
    if benchmark.empty:
        return pd.Series(dtype="object")

    def classify(row: pd.Series) -> str:
        momentum = float(row.get("return_20d") or 0.0)
        volatility = float(row.get("volatility_20d") or 0.0)
        if volatility >= 0.35:
            return "high_volatility"
        if momentum >= 0.05:
            return "bull"
        if momentum <= -0.05:
            return "bear"
        return "sideways"

    return benchmark.set_index("trade_date").apply(classify, axis=1)


class FactorAnalysisService:
    """Alphalens-style, dependency-light factor diagnostics for ETF selection."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()

    def _panel(self, db: Session) -> pd.DataFrame:
        instruments = db.scalars(
            select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)
        ).all()
        frames: list[pd.DataFrame] = []
        for instrument in instruments:
            rows = db.scalars(
                select(DailyBar)
                .where(DailyBar.instrument_id == instrument.id)
                .order_by(DailyBar.trade_date)
            ).all()
            if len(rows) < 160:
                continue
            raw = pd.DataFrame(
                [
                    {
                        "trade_date": row.trade_date,
                        "open": row.open,
                        "high": row.high,
                        "low": row.low,
                        "close": row.close,
                        "volume": row.volume or 0,
                        "amount": row.amount or 0,
                    }
                    for row in rows
                ]
            )
            rich = build_feature_frame(raw, self.strategy["indicator"]).frame
            rich["instrument_id"] = instrument.id
            rich["ts_code"] = instrument.ts_code
            rich["theme_l1"] = instrument.theme_l1 or "未分类"
            rich["theme_l2"] = instrument.theme_l2 or "未分类"
            frames.append(rich)
        if not frames:
            return pd.DataFrame()
        panel = add_cross_sectional_features(pd.concat(frames, ignore_index=True))
        benchmark_code = str(self.strategy["signal"].get("regime_benchmark", "510300.SH"))
        panel = add_oss_research_factor_diagnostics(panel, benchmark_code)
        for horizon in aligned_research_horizons(self.strategy):
            panel[f"forward_return_{horizon}"] = (
                panel.groupby("ts_code", observed=True)["close"].shift(-horizon) / panel["close"] - 1.0
            )
        regimes = _regime_labels(panel, benchmark_code)
        panel["regime"] = panel["trade_date"].map(regimes).fillna("unknown")
        return panel

    def run(self, db: Session, run_id: str | None = None) -> dict:
        run_id = run_id or uuid4().hex
        panel = self._panel(db)
        if panel.empty:
            raise ValueError("factor analysis requires at least one instrument with sufficient history")
        horizons = aligned_research_horizons(self.strategy)
        configured = self.strategy.get("factor_analysis", {}).get("factors", DEFAULT_FACTORS)
        factors = [name for name in configured if name in panel.columns]
        metrics = [
            factor_metric(panel, factor, horizon).model_dump()
            for factor in factors
            for horizon in horizons
        ]
        regime_horizons = tuple(horizon for horizon in horizons if horizon >= 3)
        by_regime: dict[str, list[dict]] = {}
        for regime, subset in panel.groupby("regime", observed=True):
            by_regime[str(regime)] = [
                factor_metric(subset, factor, horizon).model_dump()
                for factor in factors
                for horizon in regime_horizons
            ]
        theme_horizon = 5 if 5 in horizons else horizons[0]
        by_theme: dict[str, dict] = {}
        for theme, subset in panel.groupby("theme_l1", observed=True):
            if subset["ts_code"].nunique() < 3:
                continue
            by_theme[str(theme)] = {
                "instrument_count": int(subset["ts_code"].nunique()),
                "horizon": theme_horizon,
                "metrics": [
                    factor_metric(subset, factor, theme_horizon).model_dump()
                    for factor in factors
                ],
            }
        ranked = sorted(
            metrics,
            key=lambda item: (
                abs(float(item.get("rank_ic_mean") or 0.0)),
                abs(float(item.get("icir") or 0.0)),
            ),
            reverse=True,
        )
        now = datetime.now(self.settings.timezone)
        payload = {
            "run_id": run_id,
            "generated_at": now.isoformat(),
            "report_type": "factor_effectiveness",
            "feature_schema_version": self.strategy.get("feature_schema_version"),
            "strategy_version": self.strategy.get("version"),
            "research_status": "diagnostic_only_not_strategy_promotion",
            "horizons": list(horizons),
            "panel": {
                "rows": int(len(panel)),
                "instruments": int(panel["ts_code"].nunique()),
                "first_date": str(panel["trade_date"].min()),
                "last_date": str(panel["trade_date"].max()),
            },
            "metrics": metrics,
            "top_absolute_rank_ic": ranked[:30],
            "regime_analysis": by_regime,
            "theme_analysis": by_theme,
            "methodology": {
                "ic": "date-local cross-sectional Pearson correlation",
                "rank_ic": "date-local cross-sectional Spearman correlation",
                "icir": "mean rank IC divided by sample standard deviation",
                "quantiles": "up to five date-local quantiles",
                "turnover": "Jaccard turnover of top quantile membership",
                "horizon_contract": list(horizons),
                "oss_research_factors": list(OSS_RESEARCH_FACTORS),
                "oss_factor_scope": "factor-analysis-only; excluded from production forecast feature templates",
                "benchmark_exposure": f"rolling 60-session beta/correlation versus {benchmark_code}",
                "promotion_policy": "manual review plus walk-forward/holdout/ablation required",
            },
        }
        content_hash = stable_hash(payload)
        self.settings.reports_dir.mkdir(parents=True, exist_ok=True)
        filename = f"factor_effectiveness_{now:%Y%m%d_%H%M%S}_{content_hash[:10]}.json"
        path = self.settings.reports_dir / filename
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        db.add(
            ReportArtifact(
                report_type="factor_effectiveness",
                as_of_time=now,
                file_path=str(path),
                content_hash=content_hash,
                metadata_json={
                    "run_id": run_id,
                    "filename": filename,
                    "factor_count": len(factors),
                    "instrument_count": int(panel["ts_code"].nunique()),
                },
            )
        )
        db.flush()
        emit_event(db, "factors.analysis.completed", {"run_id": run_id, "filename": filename})
        return {
            "run_id": run_id,
            "filename": filename,
            "path": str(path),
            "url": f"/api/reports/{filename}",
            "content_hash": content_hash,
            "factor_count": len(factors),
            "instrument_count": int(panel["ts_code"].nunique()),
        }

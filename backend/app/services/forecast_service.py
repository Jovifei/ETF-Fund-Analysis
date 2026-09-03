from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import DailyBar, ForecastSnapshot, Instrument
from app.services.event_service import emit_event
from app.utils.feature_store import (
    FEATURE_SCHEMA_VERSION,
    LEGACY_FEATURES,
    add_cross_sectional_features,
    build_feature_frame,
    feature_columns_for_horizon,
)
from app.utils.hashing import stable_hash
from app.utils.horizons import DEFAULT_RESEARCH_HORIZONS
from app.utils.numbers import clamp
from app.utils.reproducibility import reproducibility_payload

FEATURES = list(LEGACY_FEATURES)


@dataclass(slots=True)
class ForecastResult:
    horizon: int
    p_up: float | None
    expected_return: float | None
    q10: float | None
    q50: float | None
    q90: float | None
    sample_count: int
    confidence: float
    similarity_distance: float | None
    diagnostics: dict[str, Any]
    corridor: dict[str, Any] = field(default_factory=dict)


def _empty_result(horizon: int, reason: str, sample_count: int = 0) -> ForecastResult:
    return ForecastResult(
        horizon=horizon,
        p_up=None,
        expected_return=None,
        q10=None,
        q50=None,
        q90=None,
        sample_count=sample_count,
        confidence=0.0,
        similarity_distance=None,
        diagnostics={"reason": reason},
    )


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, quantiles: Iterable[float]) -> np.ndarray:
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    cumulative = np.cumsum(weights)
    if len(values) == 0:
        return np.full(len(tuple(quantiles)), np.nan)
    if cumulative[-1] <= 0:
        return np.quantile(values, tuple(quantiles))
    positions = (cumulative - 0.5 * weights) / cumulative[-1]
    return np.interp(np.asarray(tuple(quantiles), dtype=float), positions, values)


def _future_target_frame(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
    close = frame["close"].astype(float)
    lows = pd.concat([frame["low"].shift(-step) for step in range(1, horizon + 1)], axis=1)
    highs = pd.concat([frame["high"].shift(-step) for step in range(1, horizon + 1)], axis=1)
    result = pd.DataFrame(index=frame.index)
    result["target_terminal"] = close.shift(-horizon) / close - 1.0
    result["target_path_low"] = lows.min(axis=1) / close - 1.0
    result["target_path_high"] = highs.max(axis=1) / close - 1.0
    return result


def _box_levels(current: pd.Series, window: int = 20) -> tuple[float | None, float | None]:
    close = float(current.get("close") or 0.0)
    box_range = current.get(f"box_range_{window}")
    box_position = current.get(f"box_position_{window}")
    if close <= 0 or pd.isna(box_range) or pd.isna(box_position):
        return None, None
    box_range = float(box_range)
    box_position = float(box_position)
    denominator = 1.0 + box_position * box_range
    if denominator <= 0:
        return None, None
    low = close / denominator
    high = low * (1.0 + box_range)
    return low, high


def _price(value: float | None, current_close: float) -> float | None:
    if value is None or not math.isfinite(value) or current_close <= 0:
        return None
    return round(current_close * (1.0 + value), 6)


def _pinball_safe_quantiles(values: np.ndarray) -> tuple[float, float, float, float, float]:
    q05, q10, q50, q90, q95 = np.quantile(values, [0.05, 0.10, 0.50, 0.90, 0.95])
    ordered = np.maximum.accumulate(np.asarray([q05, q10, q50, q90, q95], dtype=float))
    return tuple(float(item) for item in ordered)  # type: ignore[return-value]


def similarity_forecast(
    indicator_frame: pd.DataFrame,
    *,
    horizon: int,
    neighbors: int,
    minimum_neighbors: int,
    maximum_confidence: float,
    feature_columns: Iterable[str] | None = None,
    conformal_alpha: float = 0.20,
) -> ForecastResult:
    horizon = int(horizon)
    frame = indicator_frame.copy()
    if len(frame) < max(100, horizon + 70):
        return _empty_result(horizon, "history_too_short")

    targets = _future_target_frame(frame, horizon)
    for column in targets:
        frame[column] = targets[column]
    current = frame.iloc[-1]
    requested = tuple(feature_columns or feature_columns_for_horizon(horizon, frame.columns))
    selected = tuple(
        name
        for name in requested
        if name in frame.columns and not pd.isna(current.get(name))
    )
    if len(selected) < 6:
        selected = tuple(
            name for name in LEGACY_FEATURES if name in frame.columns and not pd.isna(current.get(name))
        )
    if len(selected) < 4:
        return _empty_result(horizon, "feature_shortage")

    candidates = frame.iloc[:-horizon].dropna(
        subset=list(selected) + ["target_terminal", "target_path_low", "target_path_high"]
    )
    if len(candidates) < minimum_neighbors:
        return _empty_result(horizon, "feature_or_sample_shortage", int(len(candidates)))

    matrix = candidates[list(selected)].astype(float)
    means = matrix.mean()
    stds = matrix.std(ddof=0).replace(0, 1.0)
    normalized = (matrix - means) / stds
    current_vector = (current[list(selected)].astype(float) - means) / stds
    distances = np.sqrt(((normalized - current_vector) ** 2).mean(axis=1))
    candidate_count = min(int(neighbors), len(candidates))
    nearest_positions = np.argsort(distances.to_numpy())[:candidate_count]
    nearest = candidates.iloc[nearest_positions]
    nearest_distances = distances.iloc[nearest_positions].to_numpy(dtype=float)
    terminal = nearest["target_terminal"].to_numpy(dtype=float)
    path_low = nearest["target_path_low"].to_numpy(dtype=float)
    path_high = nearest["target_path_high"].to_numpy(dtype=float)
    if len(terminal) < minimum_neighbors:
        return _empty_result(horizon, "not_enough_neighbors", len(terminal))

    weights = 1.0 / np.maximum(nearest_distances, 0.05)
    weights = weights / weights.sum()
    expected = float(np.sum(terminal * weights))
    p_up = float(np.sum(weights * (terminal > 0)))
    q05, q10, q50, q90, q95 = _pinball_safe_quantiles(terminal)
    low_q10, low_q50, low_q90 = (
        float(value) for value in np.quantile(path_low, [0.10, 0.50, 0.90])
    )
    high_q10, high_q50, high_q90 = (
        float(value) for value in np.quantile(path_high, [0.10, 0.50, 0.90])
    )

    # Local residual widening is deliberately labelled research-only. It follows
    # conformal interval ideas but does not promote the model to calibrated.
    residuals = np.abs(terminal - q50)
    correction = float(np.quantile(residuals, max(0.5, min(0.99, 1.0 - conformal_alpha))))
    conformal_q10 = min(q10, expected - correction)
    conformal_q90 = max(q90, expected + correction)
    conformal_q05 = min(q05, expected - 1.25 * correction)
    conformal_q95 = max(q95, expected + 1.25 * correction)

    current_close = float(current["close"])
    box_low, box_high = _box_levels(current, 20)
    support = box_low
    if support is None and not pd.isna(current.get("ma20")):
        support = float(current["ma20"])
    if support is None and not pd.isna(current.get("boll_lower")):
        support = float(current["boll_lower"])
    resistance = box_high
    if resistance is None and not pd.isna(current.get("boll_upper")):
        resistance = float(current["boll_upper"])
    support_return = support / current_close - 1.0 if support and current_close > 0 else None
    resistance_return = resistance / current_close - 1.0 if resistance and current_close > 0 else None
    support_touch = (
        float(np.sum(weights * (path_low <= support_return))) if support_return is not None else None
    )
    resistance_touch = (
        float(np.sum(weights * (path_high >= resistance_return)))
        if resistance_return is not None
        else None
    )

    low_mid_price = _price(low_q50, current_close)
    high_mid_price = _price(high_q50, current_close)
    if low_mid_price is not None and high_mid_price is not None and high_mid_price > low_mid_price:
        corridor_position = clamp(
            (current_close - low_mid_price) / (high_mid_price - low_mid_price) * 100.0,
            0.0,
            100.0,
        )
    else:
        corridor_position = None

    corridor = {
        "interval_method": "local_conformal_research_v1",
        "terminal_price_q10": _price(conformal_q10, current_close),
        "terminal_price_q50": _price(q50, current_close),
        "terminal_price_q90": _price(conformal_q90, current_close),
        "terminal_price_q05": _price(conformal_q05, current_close),
        "terminal_price_q95": _price(conformal_q95, current_close),
        "path_low_price_q10": _price(low_q10, current_close),
        "path_low_price_q50": low_mid_price,
        "path_low_price_q90": _price(low_q90, current_close),
        "path_high_price_q10": _price(high_q10, current_close),
        "path_high_price_q50": high_mid_price,
        "path_high_price_q90": _price(high_q90, current_close),
        "path_low_return_q10": round(low_q10, 6),
        "path_low_return_q50": round(low_q50, 6),
        "path_low_return_q90": round(low_q90, 6),
        "path_high_return_q10": round(high_q10, 6),
        "path_high_return_q50": round(high_q50, 6),
        "path_high_return_q90": round(high_q90, 6),
        "corridor_position": round(float(corridor_position), 2) if corridor_position is not None else None,
        "support_level": round(float(support), 6) if support is not None else None,
        "resistance_level": round(float(resistance), 6) if resistance is not None else None,
        "support_touch_probability": round(support_touch, 6) if support_touch is not None else None,
        "resistance_touch_probability": round(resistance_touch, 6) if resistance_touch is not None else None,
    }

    mean_distance = float(np.mean(nearest_distances))
    dispersion = float(np.std(terminal))
    interval_width = max(0.0, conformal_q90 - conformal_q10)
    sample_factor = min(1.0, len(terminal) / max(neighbors, 1))
    distance_factor = 1.0 / (1.0 + mean_distance)
    dispersion_factor = 1.0 / (1.0 + dispersion * 20.0)
    width_factor = 1.0 / (1.0 + interval_width * 10.0)
    feature_factor = min(1.0, len(selected) / max(1, len(requested)))
    confidence = maximum_confidence * (
        0.28 * sample_factor
        + 0.24 * distance_factor
        + 0.18 * dispersion_factor
        + 0.15 * width_factor
        + 0.15 * feature_factor
    )
    diagnostics = {
        "features": list(selected),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "candidate_count": int(len(candidates)),
        "neighbor_count": int(len(terminal)),
        "mean_distance": round(mean_distance, 6),
        "target_std": round(dispersion, 6),
        "terminal_return_q05": round(conformal_q05, 6),
        "terminal_return_q95": round(conformal_q95, 6),
        "local_conformal_correction": round(correction, 6),
        "calibration_claim": "research_only_not_calibrated",
        "weighted": True,
        "corridor": corridor,
        "no_lookahead_rule": (
            "candidate features use t or earlier; terminal and path labels require t+h and "
            "are available only for historical candidates; current row never enters candidates"
        ),
    }
    return ForecastResult(
        horizon=horizon,
        p_up=round(p_up, 6),
        expected_return=round(expected, 6),
        q10=round(conformal_q10, 6),
        q50=round(q50, 6),
        q90=round(conformal_q90, 6),
        sample_count=len(terminal),
        confidence=round(clamp(confidence, 0.0, maximum_confidence), 2),
        similarity_distance=round(mean_distance, 6),
        diagnostics=diagnostics,
        corridor=corridor,
    )


class ForecastService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()

    def _frames(self, db: Session, instruments: list[Instrument]) -> dict[int, pd.DataFrame]:
        frames: dict[int, pd.DataFrame] = {}
        panel: list[pd.DataFrame] = []
        for instrument in instruments:
            rows = db.scalars(
                select(DailyBar)
                .where(DailyBar.instrument_id == instrument.id)
                .order_by(DailyBar.trade_date)
            ).all()
            if len(rows) < int(self.strategy["forecast"].get("min_history", 180)):
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
            frames[instrument.id] = rich
            panel.append(rich)
        if not panel:
            return frames
        combined = add_cross_sectional_features(pd.concat(panel, ignore_index=True))
        return {
            int(instrument_id): group.sort_values("trade_date").reset_index(drop=True)
            for instrument_id, group in combined.groupby("instrument_id", observed=True)
        }

    def refresh_all(self, db: Session, run_id: str | None = None) -> dict:
        run_id = run_id or uuid4().hex
        instruments = db.scalars(select(Instrument).where(Instrument.enabled.is_(True))).all()
        forecast_cfg = self.strategy["forecast"]
        model_version = self.strategy["forecast_version"]
        feature_schema_version = self.strategy.get("feature_schema_version", FEATURE_SCHEMA_VERSION)
        frames = self._frames(db, instruments)
        created = 0
        updated = 0
        failures: list[dict[str, str]] = []
        for instrument in instruments:
            frame = frames.get(instrument.id)
            if frame is None or frame.empty:
                failures.append({"ts_code": instrument.ts_code, "reason": "历史数据不足或指标计算失败"})
                continue
            as_of_date = frame.iloc[-1]["trade_date"]
            rows = db.scalars(
                select(DailyBar)
                .where(DailyBar.instrument_id == instrument.id)
                .order_by(DailyBar.trade_date.desc())
                .limit(600)
            ).all()
            input_hash = stable_hash(
                [{"date": row.trade_date, "hash": row.quality_hash} for row in reversed(rows)]
            )
            for horizon in [int(value) for value in forecast_cfg.get("horizons", DEFAULT_RESEARCH_HORIZONS)]:
                selected = feature_columns_for_horizon(horizon, frame.columns)
                result = similarity_forecast(
                    frame,
                    horizon=horizon,
                    neighbors=int(forecast_cfg.get("neighbors", 80)),
                    minimum_neighbors=int(forecast_cfg.get("minimum_neighbors", 25)),
                    maximum_confidence=float(forecast_cfg.get("maximum_confidence_uncalibrated", 55)),
                    feature_columns=selected,
                    conformal_alpha=float(forecast_cfg.get("conformal_alpha", 0.20)),
                )
                reproducibility = reproducibility_payload(
                    strategy=self.strategy,
                    feature_schema_version=feature_schema_version,
                    features=selected,
                    code_component="ForecastService.v0.7",
                )
                result.diagnostics["reproducibility"] = reproducibility
                snapshot = db.scalar(
                    select(ForecastSnapshot).where(
                        ForecastSnapshot.instrument_id == instrument.id,
                        ForecastSnapshot.as_of_date == as_of_date,
                        ForecastSnapshot.horizon == horizon,
                        ForecastSnapshot.model_version == model_version,
                    )
                )
                if snapshot is None:
                    snapshot = ForecastSnapshot(
                        instrument_id=instrument.id,
                        as_of_date=as_of_date,
                        horizon=horizon,
                        model_version=model_version,
                        input_hash=input_hash,
                    )
                    db.add(snapshot)
                    created += 1
                else:
                    updated += 1
                snapshot.p_up = result.p_up
                snapshot.expected_return = result.expected_return
                snapshot.q10 = result.q10
                snapshot.q50 = result.q50
                snapshot.q90 = result.q90
                snapshot.sample_count = result.sample_count
                snapshot.confidence = result.confidence
                snapshot.calibration_status = "not_calibrated"
                snapshot.similarity_distance = result.similarity_distance
                snapshot.diagnostics_json = result.diagnostics
                snapshot.input_hash = input_hash
                snapshot.feature_schema_version = feature_schema_version
                snapshot.config_hash = reproducibility["config_hash"]
                snapshot.git_commit_sha = reproducibility["git_commit_sha"]
                snapshot.reproducibility_json = reproducibility
                snapshot.interval_method = result.corridor.get("interval_method")
                for name in (
                    "terminal_price_q10",
                    "terminal_price_q50",
                    "terminal_price_q90",
                    "path_low_price_q10",
                    "path_low_price_q50",
                    "path_low_price_q90",
                    "path_high_price_q10",
                    "path_high_price_q50",
                    "path_high_price_q90",
                    "corridor_position",
                    "support_touch_probability",
                    "resistance_touch_probability",
                ):
                    setattr(snapshot, name, result.corridor.get(name))
        db.flush()
        emit_event(
            db,
            "forecasts.updated",
            {
                "run_id": run_id,
                "created": created,
                "updated": updated,
                "failures": failures,
                "model_version": model_version,
                "feature_schema_version": feature_schema_version,
            },
        )
        return {
            "run_id": run_id,
            "created": created,
            "updated": updated,
            "failures": failures,
            "model_version": model_version,
            "feature_schema_version": feature_schema_version,
        }

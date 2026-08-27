from __future__ import annotations

import math
from dataclasses import dataclass
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import DailyBar, ForecastSnapshot, Instrument
from app.services.event_service import emit_event
from app.utils.hashing import stable_hash
from app.utils.indicators import calculate_indicators
from app.utils.numbers import clamp


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
    diagnostics: dict


FEATURES = [
    "return_1d",
    "return_5d",
    "return_20d",
    "ma_gap_5_20",
    "ma_gap_20_60",
    "macd_norm",
    "kdj_j",
    "rsi14",
    "atr_pct",
    "volume_ratio",
    "volatility_20d",
    "drawdown_60d",
]


def _feature_frame(indicator_frame: pd.DataFrame) -> pd.DataFrame:
    frame = indicator_frame.copy()
    frame["ma_gap_5_20"] = frame["ma5"] / frame["ma20"] - 1
    frame["ma_gap_20_60"] = frame["ma20"] / frame["ma60"] - 1
    frame["macd_norm"] = frame["macd_hist"] / frame["close"].replace(0, np.nan)
    return frame


def similarity_forecast(
    indicator_frame: pd.DataFrame,
    *,
    horizon: int,
    neighbors: int,
    minimum_neighbors: int,
    maximum_confidence: float,
) -> ForecastResult:
    frame = _feature_frame(indicator_frame)
    if len(frame) < max(100, horizon + 70):
        return ForecastResult(horizon, None, None, None, None, None, 0, 0, None, {"reason": "history_too_short"})

    frame["target"] = frame["close"].shift(-horizon) / frame["close"] - 1
    candidates = frame.iloc[:-horizon].copy()
    current = frame.iloc[-1]
    candidates = candidates.dropna(subset=FEATURES + ["target"])
    if current[FEATURES].isna().any() or len(candidates) < minimum_neighbors:
        return ForecastResult(
            horizon,
            None,
            None,
            None,
            None,
            None,
            int(len(candidates)),
            0,
            None,
            {"reason": "feature_or_sample_shortage"},
        )

    matrix = candidates[FEATURES].astype(float)
    means = matrix.mean()
    stds = matrix.std(ddof=0).replace(0, 1.0)
    normalized = (matrix - means) / stds
    current_vector = (current[FEATURES].astype(float) - means) / stds
    distances = np.sqrt(((normalized - current_vector) ** 2).mean(axis=1))
    candidate_count = min(neighbors, len(candidates))
    nearest_positions = np.argsort(distances.to_numpy())[:candidate_count]
    nearest = candidates.iloc[nearest_positions].copy()
    nearest_distances = distances.iloc[nearest_positions].to_numpy(dtype=float)
    targets = nearest["target"].to_numpy(dtype=float)
    if len(targets) < minimum_neighbors:
        return ForecastResult(
            horizon,
            None,
            None,
            None,
            None,
            None,
            len(targets),
            0,
            None,
            {"reason": "not_enough_neighbors"},
        )

    weights = 1.0 / np.maximum(nearest_distances, 0.05)
    weights = weights / weights.sum()
    expected = float(np.sum(targets * weights))
    p_up = float(np.sum(weights * (targets > 0)))
    q10, q50, q90 = [float(value) for value in np.quantile(targets, [0.1, 0.5, 0.9])]
    mean_distance = float(np.mean(nearest_distances))
    sample_factor = min(1.0, len(targets) / max(neighbors, 1))
    distance_factor = 1.0 / (1.0 + mean_distance)
    dispersion = float(np.std(targets))
    dispersion_factor = 1.0 / (1.0 + dispersion * 20)
    confidence = maximum_confidence * (0.4 * sample_factor + 0.35 * distance_factor + 0.25 * dispersion_factor)
    diagnostics = {
        "features": FEATURES,
        "candidate_count": int(len(candidates)),
        "neighbor_count": int(len(targets)),
        "mean_distance": round(mean_distance, 6),
        "target_std": round(dispersion, 6),
        "weighted": True,
        "no_lookahead_rule": "candidate target only uses rows with t+h available; current row never enters candidates",
    }
    return ForecastResult(
        horizon=horizon,
        p_up=round(p_up, 6),
        expected_return=round(expected, 6),
        q10=round(q10, 6),
        q50=round(q50, 6),
        q90=round(q90, 6),
        sample_count=len(targets),
        confidence=round(clamp(confidence, 0, maximum_confidence), 2),
        similarity_distance=round(mean_distance, 6),
        diagnostics=diagnostics,
    )


class ForecastService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()

    def refresh_all(self, db: Session, run_id: str | None = None) -> dict:
        run_id = run_id or uuid4().hex
        instruments = db.scalars(select(Instrument).where(Instrument.enabled.is_(True))).all()
        forecast_cfg = self.strategy["forecast"]
        model_version = self.strategy["forecast_version"]
        created = 0
        failures: list[dict] = []
        for instrument in instruments:
            rows = db.scalars(
                select(DailyBar)
                .where(DailyBar.instrument_id == instrument.id)
                .order_by(DailyBar.trade_date)
            ).all()
            if len(rows) < int(forecast_cfg.get("min_history", 180)):
                failures.append({"ts_code": instrument.ts_code, "reason": "历史数据不足"})
                continue
            input_frame = pd.DataFrame(
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
            try:
                indicator_result = calculate_indicators(input_frame, self.strategy["indicator"])
            except Exception as exc:
                failures.append({"ts_code": instrument.ts_code, "reason": f"indicator: {exc}"})
                continue
            as_of_date = rows[-1].trade_date
            input_hash = stable_hash(
                [{"date": row.trade_date, "hash": row.quality_hash} for row in rows[-600:]]
            )
            for horizon in forecast_cfg.get("horizons", [1, 5, 20]):
                result = similarity_forecast(
                    indicator_result.frame,
                    horizon=int(horizon),
                    neighbors=int(forecast_cfg.get("neighbors", 80)),
                    minimum_neighbors=int(forecast_cfg.get("minimum_neighbors", 25)),
                    maximum_confidence=float(forecast_cfg.get("maximum_confidence_uncalibrated", 55)),
                )
                snapshot = db.scalar(
                    select(ForecastSnapshot).where(
                        ForecastSnapshot.instrument_id == instrument.id,
                        ForecastSnapshot.as_of_date == as_of_date,
                        ForecastSnapshot.horizon == int(horizon),
                        ForecastSnapshot.model_version == model_version,
                    )
                )
                if snapshot is None:
                    snapshot = ForecastSnapshot(
                        instrument_id=instrument.id,
                        as_of_date=as_of_date,
                        horizon=int(horizon),
                        model_version=model_version,
                        input_hash=input_hash,
                    )
                    db.add(snapshot)
                    created += 1
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
        db.flush()
        emit_event(db, "forecasts.updated", {"run_id": run_id, "created": created, "failures": failures})
        return {"run_id": run_id, "created": created, "failures": failures}

from __future__ import annotations

import json
import math
from datetime import datetime
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import DailyBar, Instrument, ReportArtifact
from app.services.event_service import emit_event
from app.services.forecast_service import ForecastResult, similarity_forecast
from app.utils.feature_store import add_cross_sectional_features, build_feature_frame, feature_columns_for_horizon
from app.utils.hashing import stable_hash


def _safe_mean(values: list[float]) -> float | None:
    selected = [float(value) for value in values if math.isfinite(float(value))]
    return round(float(np.mean(selected)), 6) if selected else None


def _pinball(actual: np.ndarray, predicted: np.ndarray, quantile: float) -> float:
    error = actual - predicted
    return float(np.mean(np.maximum(quantile * error, (quantile - 1.0) * error)))


def _calibration_bins(probabilities: np.ndarray, actual_up: np.ndarray) -> list[dict]:
    bins: list[dict] = []
    for lower in (0.0, 0.2, 0.4, 0.6, 0.8):
        upper = min(1.0, lower + 0.2)
        mask = (probabilities >= lower) & (
            probabilities <= upper if upper == 1.0 else probabilities < upper
        )
        if mask.any():
            bins.append(
                {
                    "range": [lower, upper],
                    "count": int(mask.sum()),
                    "mean_predicted": round(float(probabilities[mask].mean()), 4),
                    "actual_frequency": round(float(actual_up[mask].mean()), 4),
                }
            )
    return bins


def _record_metrics(records: list[dict]) -> dict:
    if not records:
        return {"sample_count": 0, "status": "no_valid_points"}
    p = np.asarray([item["p_up"] for item in records], dtype=float)
    actual = np.asarray([item["actual_terminal"] for item in records], dtype=float)
    predicted = np.asarray([item["predicted_terminal"] for item in records], dtype=float)
    actual_up = (actual > 0).astype(float)
    q10 = np.asarray([item["q10"] for item in records], dtype=float)
    q50 = np.asarray([item["q50"] for item in records], dtype=float)
    q90 = np.asarray([item["q90"] for item in records], dtype=float)
    q05 = np.asarray([item["q05"] for item in records], dtype=float)
    q95 = np.asarray([item["q95"] for item in records], dtype=float)
    low_actual = np.asarray([item["actual_path_low"] for item in records], dtype=float)
    high_actual = np.asarray([item["actual_path_high"] for item in records], dtype=float)
    low10 = np.asarray([item["low_q10"] for item in records], dtype=float)
    low50 = np.asarray([item["low_q50"] for item in records], dtype=float)
    low90 = np.asarray([item["low_q90"] for item in records], dtype=float)
    high10 = np.asarray([item["high_q10"] for item in records], dtype=float)
    high50 = np.asarray([item["high_q50"] for item in records], dtype=float)
    high90 = np.asarray([item["high_q90"] for item in records], dtype=float)
    support_rows = [item for item in records if item.get("support_touch_probability") is not None]
    resistance_rows = [item for item in records if item.get("resistance_touch_probability") is not None]
    support_brier = None
    if support_rows:
        probs = np.asarray([item["support_touch_probability"] for item in support_rows], dtype=float)
        outcomes = np.asarray([item["actual_support_touch"] for item in support_rows], dtype=float)
        support_brier = round(float(np.mean((probs - outcomes) ** 2)), 6)
    resistance_brier = None
    if resistance_rows:
        probs = np.asarray([item["resistance_touch_probability"] for item in resistance_rows], dtype=float)
        outcomes = np.asarray([item["actual_resistance_touch"] for item in resistance_rows], dtype=float)
        resistance_brier = round(float(np.mean((probs - outcomes) ** 2)), 6)
    return {
        "sample_count": len(records),
        "directional_accuracy": round(float(((p >= 0.5) == (actual_up > 0)).mean()), 4),
        "brier_score": round(float(np.mean((p - actual_up) ** 2)), 6),
        "return_mae": round(float(np.mean(np.abs(predicted - actual))), 6),
        "mean_predicted_return": _safe_mean(predicted.tolist()),
        "mean_actual_return": _safe_mean(actual.tolist()),
        "pinball_loss": {
            "q10": round(_pinball(actual, q10, 0.10), 6),
            "q50": round(_pinball(actual, q50, 0.50), 6),
            "q90": round(_pinball(actual, q90, 0.90), 6),
        },
        "interval_80_coverage": round(float(np.mean((actual >= q10) & (actual <= q90))), 4),
        "interval_90_coverage": round(float(np.mean((actual >= q05) & (actual <= q95))), 4),
        "interval_80_mean_width": round(float(np.mean(q90 - q10)), 6),
        "interval_90_mean_width": round(float(np.mean(q95 - q05)), 6),
        "quantile_crossing_rate": round(float(np.mean((q10 > q50) | (q50 > q90))), 6),
        "path_low": {
            "median_mae": round(float(np.mean(np.abs(low50 - low_actual))), 6),
            "interval_80_coverage": round(float(np.mean((low_actual >= low10) & (low_actual <= low90))), 4),
            "mean_interval_width": round(float(np.mean(low90 - low10)), 6),
        },
        "path_high": {
            "median_mae": round(float(np.mean(np.abs(high50 - high_actual))), 6),
            "interval_80_coverage": round(float(np.mean((high_actual >= high10) & (high_actual <= high90))), 4),
            "mean_interval_width": round(float(np.mean(high90 - high10)), 6),
        },
        "support_touch_brier": support_brier,
        "resistance_touch_brier": resistance_brier,
        "calibration_bins": _calibration_bins(p, actual_up),
        "first_date": records[0]["as_of_date"],
        "last_date": records[-1]["as_of_date"],
    }


class ForecastValidationService:
    """Rolling-origin audit for endpoint and path-corridor forecasts."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()

    def _frames(self, db: Session, instruments: list[Instrument]) -> dict[int, pd.DataFrame]:
        items: list[pd.DataFrame] = []
        for instrument in instruments:
            rows = db.scalars(
                select(DailyBar)
                .where(DailyBar.instrument_id == instrument.id)
                .order_by(DailyBar.trade_date)
            ).all()
            if not rows:
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
            items.append(rich)
        if not items:
            return {}
        panel = add_cross_sectional_features(pd.concat(items, ignore_index=True))
        return {
            int(instrument_id): group.sort_values("trade_date").reset_index(drop=True)
            for instrument_id, group in panel.groupby("instrument_id", observed=True)
        }

    def _validate_instrument(self, instrument: Instrument, frame: pd.DataFrame) -> dict:
        cfg = self.strategy["forecast"]
        minimum = int(cfg.get("min_history", 180))
        maximum_horizon = max(int(value) for value in cfg.get("horizons", [1, 5, 20]))
        if len(frame) < minimum + maximum_horizon + 10:
            return {"ts_code": instrument.ts_code, "status": "skipped", "reason": "history_too_short"}
        horizons: dict[str, dict] = {}
        step = max(1, int(cfg.get("validation_step", 5)))
        max_points = max(20, int(cfg.get("validation_max_points", 120)))
        for horizon in [int(value) for value in cfg.get("horizons", [1, 5, 20])]:
            eligible = list(range(minimum - 1, len(frame) - horizon, step))
            if len(eligible) > max_points:
                positions = np.linspace(0, len(eligible) - 1, max_points, dtype=int)
                eligible = [eligible[index] for index in positions]
            records: list[dict] = []
            for end_index in eligible:
                history = frame.iloc[: end_index + 1]
                forecast: ForecastResult = similarity_forecast(
                    history,
                    horizon=horizon,
                    neighbors=int(cfg.get("neighbors", 80)),
                    minimum_neighbors=int(cfg.get("minimum_neighbors", 25)),
                    maximum_confidence=float(cfg.get("maximum_confidence_uncalibrated", 55)),
                    feature_columns=feature_columns_for_horizon(horizon, history.columns),
                    conformal_alpha=float(cfg.get("conformal_alpha", 0.20)),
                )
                if forecast.p_up is None or forecast.expected_return is None or not forecast.corridor:
                    continue
                current_close = float(frame.iloc[end_index]["close"])
                future = frame.iloc[end_index + 1 : end_index + horizon + 1]
                actual_terminal = float(frame.iloc[end_index + horizon]["close"] / current_close - 1.0)
                actual_low = float(future["low"].min() / current_close - 1.0)
                actual_high = float(future["high"].max() / current_close - 1.0)
                corridor = forecast.corridor
                support = corridor.get("support_level")
                resistance = corridor.get("resistance_level")
                records.append(
                    {
                        "as_of_date": str(frame.iloc[end_index]["trade_date"]),
                        "p_up": forecast.p_up,
                        "predicted_terminal": forecast.expected_return,
                        "actual_terminal": actual_terminal,
                        "q10": float(forecast.q10),
                        "q50": float(forecast.q50),
                        "q90": float(forecast.q90),
                        "q05": float(forecast.diagnostics.get("terminal_return_q05", forecast.q10)),
                        "q95": float(forecast.diagnostics.get("terminal_return_q95", forecast.q90)),
                        "actual_path_low": actual_low,
                        "actual_path_high": actual_high,
                        "low_q10": float(corridor["path_low_return_q10"]),
                        "low_q50": float(corridor["path_low_return_q50"]),
                        "low_q90": float(corridor["path_low_return_q90"]),
                        "high_q10": float(corridor["path_high_return_q10"]),
                        "high_q50": float(corridor["path_high_return_q50"]),
                        "high_q90": float(corridor["path_high_return_q90"]),
                        "support_touch_probability": corridor.get("support_touch_probability"),
                        "resistance_touch_probability": corridor.get("resistance_touch_probability"),
                        "actual_support_touch": bool(support is not None and float(future["low"].min()) <= float(support)),
                        "actual_resistance_touch": bool(
                            resistance is not None and float(future["high"].max()) >= float(resistance)
                        ),
                    }
                )
            horizons[str(horizon)] = _record_metrics(records)
        return {
            "ts_code": instrument.ts_code,
            "name": instrument.name,
            "status": "ok",
            "horizons": horizons,
        }

    def run(self, db: Session, run_id: str | None = None) -> dict:
        run_id = run_id or uuid4().hex
        instruments = db.scalars(
            select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)
        ).all()
        frames = self._frames(db, instruments)
        results = [
            self._validate_instrument(instrument, frames[instrument.id])
            if instrument.id in frames
            else {"ts_code": instrument.ts_code, "status": "skipped", "reason": "history_missing"}
            for instrument in instruments
        ]
        now = datetime.now(self.settings.timezone)
        payload = {
            "run_id": run_id,
            "generated_at": now.isoformat(),
            "model_version": self.strategy["forecast_version"],
            "feature_schema_version": self.strategy.get("feature_schema_version"),
            "method": "rolling-origin similarity endpoint-and-path forecast audit",
            "promotion_policy": "manual review required; this task never changes calibration_status",
            "metrics": [
                "directional_accuracy",
                "brier_score",
                "return_mae",
                "pinball_loss",
                "interval_80_coverage",
                "interval_90_coverage",
                "interval_width",
                "quantile_crossing_rate",
                "path_low_high_coverage",
                "support_resistance_touch_brier",
            ],
            "instruments": results,
        }
        content_hash = stable_hash(payload)
        self.settings.reports_dir.mkdir(parents=True, exist_ok=True)
        filename = f"forecast_validation_{now:%Y%m%d_%H%M%S}_{content_hash[:10]}.json"
        path = self.settings.reports_dir / filename
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        db.add(
            ReportArtifact(
                report_type="forecast_validation",
                as_of_time=now,
                file_path=str(path),
                content_hash=content_hash,
                metadata_json={
                    "run_id": run_id,
                    "filename": filename,
                    "model_version": self.strategy["forecast_version"],
                    "instrument_count": len(results),
                },
            )
        )
        db.flush()
        emit_event(db, "forecast.validation.completed", {"run_id": run_id, "filename": filename})
        return {
            "run_id": run_id,
            "filename": filename,
            "path": str(path),
            "content_hash": content_hash,
            "instrument_count": len(results),
        }

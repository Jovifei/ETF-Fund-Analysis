from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import DailyBar, Instrument, ReportArtifact
from app.services.event_service import emit_event
from app.services.forecast_service import similarity_forecast
from app.utils.hashing import stable_hash
from app.utils.indicators import calculate_indicators


def _safe_mean(values: list[float]) -> float | None:
    values = [float(value) for value in values if math.isfinite(float(value))]
    return round(float(np.mean(values)), 6) if values else None


class ForecastValidationService:
    """Walk-forward audit for the similarity forecast baseline.

    This is intentionally a separate manual task. The production UI keeps model
    status `not_calibrated` until this report is reviewed; running the task does
    not silently promote a model to calibrated.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()

    def _validate_instrument(self, db: Session, instrument: Instrument) -> dict:
        bars = db.scalars(
            select(DailyBar)
            .where(DailyBar.instrument_id == instrument.id)
            .order_by(DailyBar.trade_date)
        ).all()
        cfg = self.strategy["forecast"]
        minimum = int(cfg.get("min_history", 180))
        if len(bars) < minimum + max(cfg.get("horizons", [20])) + 10:
            return {"ts_code": instrument.ts_code, "status": "skipped", "reason": "history_too_short"}
        frame = pd.DataFrame(
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
                for row in bars
            ]
        )
        indicator_frame = calculate_indicators(frame, self.strategy["indicator"]).frame
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
                forecast = similarity_forecast(
                    indicator_frame.iloc[: end_index + 1],
                    horizon=horizon,
                    neighbors=int(cfg.get("neighbors", 80)),
                    minimum_neighbors=int(cfg.get("minimum_neighbors", 25)),
                    maximum_confidence=float(cfg.get("maximum_confidence_uncalibrated", 55)),
                )
                if forecast.p_up is None or forecast.expected_return is None:
                    continue
                actual = float(frame.iloc[end_index + horizon]["close"] / frame.iloc[end_index]["close"] - 1)
                records.append(
                    {
                        "as_of_date": str(frame.iloc[end_index]["trade_date"]),
                        "p_up": forecast.p_up,
                        "predicted": forecast.expected_return,
                        "actual": actual,
                        "covered_80": bool(forecast.q10 <= actual <= forecast.q90),
                    }
                )
            if not records:
                horizons[str(horizon)] = {"sample_count": 0, "status": "no_valid_points"}
                continue
            p = np.array([item["p_up"] for item in records], dtype=float)
            actual_returns = np.array([item["actual"] for item in records], dtype=float)
            predicted_returns = np.array([item["predicted"] for item in records], dtype=float)
            actual_up = (actual_returns > 0).astype(float)
            bins: list[dict] = []
            for lower in (0.0, 0.2, 0.4, 0.6, 0.8):
                mask = (p >= lower) & (p < lower + 0.2 + 1e-12)
                if mask.any():
                    bins.append(
                        {
                            "range": [lower, min(1.0, lower + 0.2)],
                            "count": int(mask.sum()),
                            "mean_predicted": round(float(p[mask].mean()), 4),
                            "actual_frequency": round(float(actual_up[mask].mean()), 4),
                        }
                    )
            horizons[str(horizon)] = {
                "sample_count": len(records),
                "directional_accuracy": round(float(((p >= 0.5) == (actual_up > 0)).mean()), 4),
                "brier_score": round(float(np.mean((p - actual_up) ** 2)), 6),
                "return_mae": round(float(np.mean(np.abs(predicted_returns - actual_returns))), 6),
                "mean_predicted_return": _safe_mean(predicted_returns.tolist()),
                "mean_actual_return": _safe_mean(actual_returns.tolist()),
                "interval_80_coverage": round(float(np.mean([item["covered_80"] for item in records])), 4),
                "calibration_bins": bins,
                "first_date": records[0]["as_of_date"],
                "last_date": records[-1]["as_of_date"],
            }
        return {"ts_code": instrument.ts_code, "name": instrument.name, "status": "ok", "horizons": horizons}

    def run(self, db: Session, run_id: str | None = None) -> dict:
        run_id = run_id or uuid4().hex
        instruments = db.scalars(
            select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)
        ).all()
        results = [self._validate_instrument(db, instrument) for instrument in instruments]
        now = datetime.now(self.settings.timezone)
        payload = {
            "run_id": run_id,
            "generated_at": now.isoformat(),
            "model_version": self.strategy["forecast_version"],
            "method": "rolling-origin similarity forecast audit",
            "promotion_policy": "manual review required; this task never changes calibration_status",
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

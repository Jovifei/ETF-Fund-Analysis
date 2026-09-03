from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import ReportArtifact
from app.services.event_service import emit_event
from app.services.factor_analysis_service import FactorAnalysisService
from app.utils.feature_store import HORIZON_FEATURES
from app.utils.hashing import stable_hash
from app.utils.horizons import aligned_research_horizons
from app.utils.time_split import purged_holdout_bounds


def _pinball(actual: np.ndarray, predicted: np.ndarray, quantile: float) -> float:
    error = actual - predicted
    return float(np.mean(np.maximum(quantile * error, (quantile - 1.0) * error)))


class GlobalModelResearchService:
    """Optional global ETF model benchmark; never writes production forecasts."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()

    @staticmethod
    def _backend() -> str | None:
        if importlib.util.find_spec("lightgbm") is not None:
            return "lightgbm"
        if importlib.util.find_spec("catboost") is not None:
            return "catboost"
        return None

    @staticmethod
    def _fit_predict(
        backend: str,
        train_x: pd.DataFrame,
        train_y: pd.Series,
        test_x: pd.DataFrame,
        quantile: float,
    ) -> np.ndarray:
        if backend == "lightgbm":
            from lightgbm import LGBMRegressor

            model = LGBMRegressor(
                objective="quantile",
                alpha=quantile,
                n_estimators=220,
                learning_rate=0.035,
                num_leaves=15,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=20260829,
                verbosity=-1,
            )
        else:
            from catboost import CatBoostRegressor

            model = CatBoostRegressor(
                loss_function=f"Quantile:alpha={quantile}",
                iterations=240,
                depth=5,
                learning_rate=0.035,
                random_seed=20260829,
                verbose=False,
            )
        model.fit(train_x, train_y)
        return np.asarray(model.predict(test_x), dtype=float)

    def run(self, db: Session, run_id: str | None = None) -> dict:
        run_id = run_id or uuid4().hex
        backend = self._backend()
        now = datetime.now(self.settings.timezone)
        if backend is None:
            payload = {
                "run_id": run_id,
                "generated_at": now.isoformat(),
                "status": "unavailable",
                "reason": "install optional research extra with LightGBM or CatBoost",
                "production_promotion": False,
            }
        else:
            panel = FactorAnalysisService(self.settings)._panel(db)
            if panel.empty:
                raise ValueError("global model research requires historical ETF panel")
            dates = sorted(panel["trade_date"].dropna().unique())
            if len(dates) < 240:
                raise ValueError("global model research requires at least 240 distinct trading dates")
            split_date = dates[int(len(dates) * 0.80)]
            horizons = aligned_research_horizons(self.strategy)
            research_cfg = self.strategy.get("global_model_research", {})
            embargo_sessions = max(0, int(research_cfg.get("embargo_sessions", 0)))
            payload = {
                "run_id": run_id,
                "generated_at": now.isoformat(),
                "status": "completed",
                "backend": backend,
                "split": {
                    "method": "chronological_80_20_holdout_with_horizon_purge",
                    "split_date": str(split_date),
                    "random_shuffle": False,
                    "embargo_sessions": embargo_sessions,
                    "label_leakage_policy": (
                        "for horizon h, exclude the h sessions immediately before the test boundary "
                        "from training so every training forward label ends before the first test session"
                    ),
                },
                "configured_horizons": list(horizons),
                "feature_schema_version": self.strategy.get("feature_schema_version"),
                "production_promotion": False,
                "horizons": {},
            }
            for horizon in horizons:
                target = f"forward_return_{horizon}"
                features = [name for name in HORIZON_FEATURES[horizon] if name in panel.columns]
                work = panel[["trade_date", target, *features]].replace([np.inf, -np.inf], np.nan).dropna()
                guard = purged_holdout_bounds(
                    dates,
                    test_start=split_date,
                    label_horizon=horizon,
                    embargo_sessions=embargo_sessions,
                )
                train = work.loc[work["trade_date"] < guard.train_before]
                test = work.loc[work["trade_date"] >= guard.test_start]
                if len(train) < 500 or len(test) < 100:
                    payload["horizons"][str(horizon)] = {
                        "status": "skipped",
                        "reason": "sample_shortage",
                        "train": len(train),
                        "test": len(test),
                        "leakage_guard": guard.model_dump(),
                    }
                    continue
                train_x = train[features].astype(float)
                test_x = test[features].astype(float)
                actual = test[target].to_numpy(dtype=float)
                predictions = {
                    quantile: self._fit_predict(backend, train_x, train[target], test_x, quantile)
                    for quantile in (0.10, 0.50, 0.90)
                }
                q10, q50, q90 = predictions[0.10], predictions[0.50], predictions[0.90]
                crossing = (q10 > q50) | (q50 > q90)
                ordered = np.sort(np.column_stack([q10, q50, q90]), axis=1)
                q10, q50, q90 = ordered[:, 0], ordered[:, 1], ordered[:, 2]
                payload["horizons"][str(horizon)] = {
                    "status": "ok",
                    "features": features,
                    "train_samples": len(train),
                    "holdout_samples": len(test),
                    "train_first_date": str(train["trade_date"].min()),
                    "train_last_date": str(train["trade_date"].max()),
                    "test_first_date": str(test["trade_date"].min()),
                    "test_last_date": str(test["trade_date"].max()),
                    "leakage_guard": guard.model_dump(),
                    "mae_q50": round(float(np.mean(np.abs(actual - q50))), 6),
                    "pinball_q10": round(_pinball(actual, q10, 0.10), 6),
                    "pinball_q50": round(_pinball(actual, q50, 0.50), 6),
                    "pinball_q90": round(_pinball(actual, q90, 0.90), 6),
                    "interval_80_coverage": round(float(np.mean((actual >= q10) & (actual <= q90))), 4),
                    "interval_mean_width": round(float(np.mean(q90 - q10)), 6),
                    "raw_quantile_crossing_rate": round(float(np.mean(crossing)), 6),
                }
        content_hash = stable_hash(payload)
        self.settings.reports_dir.mkdir(parents=True, exist_ok=True)
        filename = f"global_model_research_{now:%Y%m%d_%H%M%S}_{content_hash[:10]}.json"
        path = self.settings.reports_dir / filename
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        db.add(
            ReportArtifact(
                report_type="global_model_research",
                as_of_time=now,
                file_path=str(path),
                content_hash=content_hash,
                metadata_json={"run_id": run_id, "filename": filename, "status": payload["status"]},
            )
        )
        db.flush()
        emit_event(db, "global_model.research.completed", {"run_id": run_id, "filename": filename})
        return {
            "run_id": run_id,
            "filename": filename,
            "path": str(path),
            "url": f"/api/reports/{filename}",
            "content_hash": content_hash,
            "status": payload["status"],
        }

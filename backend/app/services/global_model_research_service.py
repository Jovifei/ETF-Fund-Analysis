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
from app.utils.time_split import purged_expanding_walk_forward_folds


def _pinball(actual: np.ndarray, predicted: np.ndarray, quantile: float) -> float:
    error = actual - predicted
    return float(np.mean(np.maximum(quantile * error, (quantile - 1.0) * error)))


def _metrics(
    actual: np.ndarray,
    q10: np.ndarray,
    q50: np.ndarray,
    q90: np.ndarray,
    raw_crossing: np.ndarray,
) -> dict[str, float]:
    return {
        "mae_q50": round(float(np.mean(np.abs(actual - q50))), 6),
        "pinball_q10": round(_pinball(actual, q10, 0.10), 6),
        "pinball_q50": round(_pinball(actual, q50, 0.50), 6),
        "pinball_q90": round(_pinball(actual, q90, 0.90), 6),
        "interval_80_coverage": round(float(np.mean((actual >= q10) & (actual <= q90))), 4),
        "interval_mean_width": round(float(np.mean(q90 - q10)), 6),
        "raw_quantile_crossing_rate": round(float(np.mean(raw_crossing)), 6),
    }


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
            horizons = aligned_research_horizons(self.strategy)
            research_cfg = self.strategy.get("global_model_research", {})
            embargo_sessions = max(0, int(research_cfg.get("embargo_sessions", 0)))
            walk_forward_folds = max(1, int(research_cfg.get("walk_forward_folds", 4)))
            walk_forward_test_sessions = max(
                1, int(research_cfg.get("walk_forward_test_sessions", 20))
            )
            walk_forward_min_train_sessions = max(
                1, int(research_cfg.get("walk_forward_min_train_sessions", 150))
            )
            payload = {
                "run_id": run_id,
                "generated_at": now.isoformat(),
                "status": "completed",
                "backend": backend,
                "research_version": research_cfg.get("version", "global-model-research-v0.2.0-purged-walk-forward"),
                "split": {
                    "method": "purged_expanding_walk_forward",
                    "folds": walk_forward_folds,
                    "test_sessions_per_fold": walk_forward_test_sessions,
                    "minimum_train_sessions": walk_forward_min_train_sessions,
                    "random_shuffle": False,
                    "embargo_sessions": embargo_sessions,
                    "label_leakage_policy": (
                        "for every horizon h and every fold, exclude h plus embargo sessions "
                        "immediately before the OOS test boundary so each training forward label "
                        "ends before the first test session"
                    ),
                    "preprocessing_policy": (
                        "fit any learned preprocessing inside each fold only; the current benchmark "
                        "uses no learned preprocessing before model fit"
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
                folds = purged_expanding_walk_forward_folds(
                    dates,
                    label_horizon=horizon,
                    folds=walk_forward_folds,
                    test_sessions=walk_forward_test_sessions,
                    min_train_sessions=walk_forward_min_train_sessions,
                    embargo_sessions=embargo_sessions,
                )
                fold_payloads: list[dict] = []
                actual_parts: list[np.ndarray] = []
                q10_parts: list[np.ndarray] = []
                q50_parts: list[np.ndarray] = []
                q90_parts: list[np.ndarray] = []
                crossing_parts: list[np.ndarray] = []
                for fold in folds:
                    train = work.loc[work["trade_date"] < fold.train_before]
                    test = work.loc[
                        (work["trade_date"] >= fold.test_start)
                        & (work["trade_date"] <= fold.test_end)
                    ]
                    fold_info = fold.model_dump()
                    fold_info.update(
                        {
                            "train_samples": len(train),
                            "test_samples": len(test),
                            "train_observed_first_date": (
                                str(train["trade_date"].min()) if not train.empty else None
                            ),
                            "train_observed_last_date": (
                                str(train["trade_date"].max()) if not train.empty else None
                            ),
                            "test_observed_first_date": (
                                str(test["trade_date"].min()) if not test.empty else None
                            ),
                            "test_observed_last_date": (
                                str(test["trade_date"].max()) if not test.empty else None
                            ),
                        }
                    )
                    if len(train) < 500 or len(test) < 100:
                        fold_info.update({"status": "skipped", "reason": "sample_shortage"})
                        fold_payloads.append(fold_info)
                        continue
                    train_x = train[features].astype(float)
                    test_x = test[features].astype(float)
                    actual = test[target].to_numpy(dtype=float)
                    predictions = {
                        quantile: self._fit_predict(
                            backend, train_x, train[target], test_x, quantile
                        )
                        for quantile in (0.10, 0.50, 0.90)
                    }
                    raw_q10, raw_q50, raw_q90 = (
                        predictions[0.10],
                        predictions[0.50],
                        predictions[0.90],
                    )
                    crossing = (raw_q10 > raw_q50) | (raw_q50 > raw_q90)
                    ordered = np.sort(
                        np.column_stack([raw_q10, raw_q50, raw_q90]), axis=1
                    )
                    q10, q50, q90 = ordered[:, 0], ordered[:, 1], ordered[:, 2]
                    fold_info.update(
                        {
                            "status": "ok",
                            **_metrics(actual, q10, q50, q90, crossing),
                        }
                    )
                    fold_payloads.append(fold_info)
                    actual_parts.append(actual)
                    q10_parts.append(q10)
                    q50_parts.append(q50)
                    q90_parts.append(q90)
                    crossing_parts.append(crossing)
                if not actual_parts:
                    payload["horizons"][str(horizon)] = {
                        "status": "skipped",
                        "reason": "no_valid_walk_forward_fold",
                        "features": features,
                        "folds": fold_payloads,
                    }
                    continue
                actual_all = np.concatenate(actual_parts)
                q10_all = np.concatenate(q10_parts)
                q50_all = np.concatenate(q50_parts)
                q90_all = np.concatenate(q90_parts)
                crossing_all = np.concatenate(crossing_parts)
                payload["horizons"][str(horizon)] = {
                    "status": "ok",
                    "features": features,
                    "fold_count": len(fold_payloads),
                    "valid_fold_count": sum(
                        1 for item in fold_payloads if item.get("status") == "ok"
                    ),
                    "oos_samples": len(actual_all),
                    "folds": fold_payloads,
                    **_metrics(actual_all, q10_all, q50_all, q90_all, crossing_all),
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

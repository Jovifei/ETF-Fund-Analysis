from __future__ import annotations

import hashlib
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
from app.utils.reproducibility import current_git_commit
from app.utils.time_split import purged_expanding_walk_forward_folds


def _pinball(actual: np.ndarray, predicted: np.ndarray, quantile: float) -> float:
    error = actual - predicted
    return float(np.mean(np.maximum(quantile * error, (quantile - 1.0) * error)))


def _frame_digest(frame: pd.DataFrame, columns: list[str]) -> str:
    """Content-address the exact ordered rows consumed by one research fold."""
    digest = hashlib.sha256()
    digest.update(json.dumps(columns, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    for row in frame[columns].itertuples(index=False, name=None):
        digest.update(b"\n")
        digest.update(json.dumps(row, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8"))
    return digest.hexdigest()


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
            universe_contract = panel.attrs.get("universe_contract")
            if not isinstance(universe_contract, dict) or not universe_contract.get("version"):
                raise ValueError("global model research requires explicit universe contract")
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
                        "each row carries its instrument-specific label_end_date; training requires "
                        "label_end_date strictly before the embargo-adjusted OOS boundary"
                    ),
                    "preprocessing_policy": (
                        "fit any learned preprocessing inside each fold only; the current benchmark "
                        "uses no learned preprocessing before model fit"
                    ),
                },
                "configured_horizons": list(horizons),
                "feature_schema_version": self.strategy.get("feature_schema_version"),
                "config_hash": stable_hash(self.strategy),
                "panel_research_input_contract_hash": stable_hash(
                    panel.attrs.get("research_input_contract", {})
                ),
                "panel_research_input_contract": panel.attrs.get("research_input_contract", {}),
                "panel_universe_contract_hash": stable_hash(panel.attrs.get("universe_contract", {})),
                "panel_universe_contract": panel.attrs.get("universe_contract", {}),
                "git_commit_sha": current_git_commit(),
                "evidence_contract": {
                    "source": self.settings.market_provider,
                    "pit_qualified": False,
                    "costs_included": False,
                    "slippage_included": False,
                    "strategy_backtest": False,
                    "qualification": "UNKNOWN",
                    "preprocessing": "none_learned_outside_fold",
                },
                "production_promotion": False,
                "horizons": {},
            }
            for horizon in horizons:
                target = f"forward_return_{horizon}"
                label_end = f"label_end_date_{horizon}"
                features = [name for name in HORIZON_FEATURES[horizon] if name in panel.columns]
                work = panel[["ts_code", "trade_date", label_end, target, *features]].replace([np.inf, -np.inf], np.nan).dropna()
                mature_dates = sorted(work["trade_date"].dropna().unique())
                folds = purged_expanding_walk_forward_folds(
                    mature_dates,
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
                    train = work.loc[
                        (work["trade_date"] < fold.test_start)
                        & (work[label_end] < fold.label_end_before)
                    ]
                    test = work.loc[
                        (work["trade_date"] >= fold.test_start)
                        & (work["trade_date"] <= fold.test_end)
                    ]
                    lineage_columns = ["ts_code", "trade_date", label_end, target, *features]
                    fold_info = fold.model_dump()
                    fold_info.update(
                        {
                            "train_samples": len(train),
                            "test_samples": len(test),
                            "train_instruments": int(train["ts_code"].nunique()),
                            "test_instruments": int(test["ts_code"].nunique()),
                            "train_input_hash": _frame_digest(train, lineage_columns),
                            "test_input_hash": _frame_digest(test, lineage_columns),
                            "lineage_columns": lineage_columns,
                            "train_observed_first_date": (
                                str(train["trade_date"].min()) if not train.empty else None
                            ),
                            "train_observed_last_date": (
                                str(train["trade_date"].max()) if not train.empty else None
                            ),
                            "train_label_end_last": (
                                str(train[label_end].max()) if not train.empty else None
                            ),
                            "label_end_guard": "per_sample_strict_before",
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
                    "mature_label_dates": len(mature_dates),
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
                metadata_json={
                    "run_id": run_id,
                    "filename": filename,
                    "status": payload["status"],
                    "research_version": payload.get("research_version"),
                    "panel_research_input_contract_hash": payload.get("panel_research_input_contract_hash"),
                    "panel_universe_contract_hash": payload.get("panel_universe_contract_hash"),
                },
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

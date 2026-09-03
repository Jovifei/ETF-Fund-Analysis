from __future__ import annotations

import json

import numpy as np
import pandas as pd

from app.services.factor_analysis_service import FactorAnalysisService
from app.services.global_model_research_service import GlobalModelResearchService
from app.utils.feature_store import HORIZON_FEATURES
from app.utils.horizons import DEFAULT_RESEARCH_HORIZONS


def _synthetic_panel() -> pd.DataFrame:
    dates = list(pd.bdate_range("2025-01-02", periods=260).date)
    features = sorted(
        {
            feature
            for horizon in DEFAULT_RESEARCH_HORIZONS
            for feature in HORIZON_FEATURES[horizon]
        }
    )
    rows: list[dict[str, object]] = []
    for date_index, trade_date in enumerate(dates):
        for instrument_index in range(6):
            row: dict[str, object] = {
                "trade_date": trade_date,
                "ts_code": f"TEST{instrument_index:02d}.SH",
            }
            for feature_index, feature in enumerate(features):
                row[feature] = (
                    0.001 * (feature_index + 1)
                    + 0.0001 * instrument_index
                    + 0.00001 * date_index
                )
            for horizon in DEFAULT_RESEARCH_HORIZONS:
                row[f"forward_return_{horizon}"] = (
                    0.0004 * horizon
                    + 0.0001 * ((date_index + instrument_index) % 5 - 2)
                )
            rows.append(row)
    return pd.DataFrame(rows)


def test_global_model_research_uses_purged_expanding_walk_forward(
    db_session, monkeypatch, tmp_path
):
    panel = _synthetic_panel()
    monkeypatch.setattr(FactorAnalysisService, "_panel", lambda self, db: panel)

    service = GlobalModelResearchService()
    monkeypatch.setattr(service.settings, "reports_dir", tmp_path)
    monkeypatch.setattr(service, "_backend", lambda: "stub")

    def fake_predict(backend, train_x, train_y, test_x, quantile):
        level = {0.10: -0.01, 0.50: 0.0, 0.90: 0.01}[quantile]
        return np.full(len(test_x), level, dtype=float)

    monkeypatch.setattr(service, "_fit_predict", fake_predict)
    result = service.run(db_session, run_id="walk-forward-test")
    payload = json.loads((tmp_path / result["filename"]).read_text(encoding="utf-8"))

    assert payload["status"] == "completed"
    assert payload["production_promotion"] is False
    assert payload["split"]["method"] == "purged_expanding_walk_forward"
    assert payload["split"]["folds"] == 4
    assert payload["split"]["test_sessions_per_fold"] == 20
    assert payload["split"]["minimum_train_sessions"] == 150
    assert payload["configured_horizons"] == [1, 3, 5, 10]

    for horizon in DEFAULT_RESEARCH_HORIZONS:
        item = payload["horizons"][str(horizon)]
        assert item["status"] == "ok"
        assert item["fold_count"] == 4
        assert item["valid_fold_count"] == 4
        assert item["oos_samples"] == 4 * 20 * 6
        folds = item["folds"]
        assert [fold["fold_index"] for fold in folds] == [1, 2, 3, 4]
        assert all(fold["status"] == "ok" for fold in folds)
        assert all(fold["purge_sessions"] == horizon for fold in folds)
        assert [fold["train_sessions"] for fold in folds] == [
            180 - horizon,
            200 - horizon,
            220 - horizon,
            240 - horizon,
        ]
        for previous, current in zip(folds, folds[1:]):
            assert previous["test_end"] < current["test_start"]
            assert previous["test_samples"] == current["test_samples"] == 120
        assert 0.0 <= item["interval_80_coverage"] <= 1.0
        assert item["interval_mean_width"] > 0

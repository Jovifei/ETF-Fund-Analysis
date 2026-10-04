from __future__ import annotations

import json

import numpy as np
import pandas as pd

from app.services.factor_analysis_service import FactorAnalysisService
from app.services.global_model_research_service import GlobalModelResearchService, _frame_digest
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
    panel = pd.DataFrame(rows)
    for horizon in DEFAULT_RESEARCH_HORIZONS:
        panel[f"label_end_date_{horizon}"] = (
            panel.groupby("ts_code", observed=True)["trade_date"].shift(-horizon)
        )
    return panel


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
    assert len(payload["config_hash"]) == 64
    assert payload["git_commit_sha"]
    assert payload["evidence_contract"]["pit_qualified"] is False
    assert payload["evidence_contract"]["costs_included"] is False
    assert payload["evidence_contract"]["slippage_included"] is False
    assert payload["evidence_contract"]["strategy_backtest"] is False
    assert payload["evidence_contract"]["qualification"] == "UNKNOWN"

    for horizon in DEFAULT_RESEARCH_HORIZONS:
        item = payload["horizons"][str(horizon)]
        assert item["status"] == "ok"
        assert item["mature_label_dates"] == 260 - horizon
        assert item["fold_count"] == 4
        assert item["valid_fold_count"] == 4
        assert item["oos_samples"] == 4 * 20 * 6
        folds = item["folds"]
        assert [fold["fold_index"] for fold in folds] == [1, 2, 3, 4]
        assert all(fold["status"] == "ok" for fold in folds)
        assert all(fold["purge_sessions"] == horizon for fold in folds)
        assert all(fold["label_end_guard"] == "per_sample_strict_before" for fold in folds)
        assert all(fold["train_label_end_last"] < fold["label_end_before"] for fold in folds)
        assert all(len(fold["train_input_hash"]) == 64 and len(fold["test_input_hash"]) == 64 for fold in folds)
        assert all(fold["train_instruments"] == fold["test_instruments"] == 6 for fold in folds)
        assert all("ts_code" in fold["lineage_columns"] and f"label_end_date_{horizon}" in fold["lineage_columns"] for fold in folds)
        assert [fold["train_sessions"] for fold in folds] == [
            180 - 2 * horizon,
            200 - 2 * horizon,
            220 - 2 * horizon,
            240 - 2 * horizon,
        ]
        for previous, current in zip(folds, folds[1:]):
            assert previous["test_end"] < current["test_start"]
            assert previous["test_samples"] == current["test_samples"] == 120
        assert 0.0 <= item["interval_80_coverage"] <= 1.0
        assert item["interval_mean_width"] > 0


def test_sparse_instrument_uses_actual_label_end_not_global_calendar_distance(
    db_session, monkeypatch, tmp_path
):
    panel = _synthetic_panel()
    dates = sorted(panel["trade_date"].unique())
    first_test = dates[-80:]
    missing = set(dates[175:180])
    panel = panel.loc[~((panel["ts_code"] == "TEST00.SH") & panel["trade_date"].isin(missing))].copy()
    for horizon in DEFAULT_RESEARCH_HORIZONS:
        panel[f"label_end_date_{horizon}"] = (
            panel.groupby("ts_code", observed=True)["trade_date"].shift(-horizon)
        )
    leaked_under_old_rule = panel.loc[
        (panel["ts_code"] == "TEST00.SH")
        & (panel["trade_date"] < dates[179])
        & (panel["label_end_date_1"] >= first_test[0])
    ]
    assert not leaked_under_old_rule.empty

    monkeypatch.setattr(FactorAnalysisService, "_panel", lambda self, db: panel)
    service = GlobalModelResearchService()
    monkeypatch.setattr(service.settings, "reports_dir", tmp_path)
    monkeypatch.setattr(service, "_backend", lambda: "stub")
    monkeypatch.setattr(
        service, "_fit_predict",
        lambda backend, train_x, train_y, test_x, quantile:
            np.full(len(test_x), {0.10: -0.01, 0.50: 0.0, 0.90: 0.01}[quantile]),
    )
    result = service.run(db_session, run_id="sparse-label-end")
    payload = json.loads((tmp_path / result["filename"]).read_text(encoding="utf-8"))
    for horizon in DEFAULT_RESEARCH_HORIZONS:
        for fold in payload["horizons"][str(horizon)]["folds"]:
            assert fold["train_label_end_last"] < fold["label_end_before"]


def test_fold_digest_is_ordered_and_changes_with_consumed_values():
    frame = pd.DataFrame({
        "ts_code": ["A.SH", "B.SH"],
        "trade_date": [pd.Timestamp("2026-01-05").date(), pd.Timestamp("2026-01-05").date()],
        "label_end_date_1": [pd.Timestamp("2026-01-06").date(), pd.Timestamp("2026-01-06").date()],
        "forward_return_1": [0.01, -0.02],
        "feature": [1.0, 2.0],
    })
    columns = ["ts_code", "trade_date", "label_end_date_1", "forward_return_1", "feature"]
    baseline = _frame_digest(frame, columns)
    mutated = frame.copy()
    mutated.loc[1, "forward_return_1"] = -0.03
    assert _frame_digest(mutated, columns) != baseline
    assert _frame_digest(frame.iloc[::-1].reset_index(drop=True), columns) != baseline

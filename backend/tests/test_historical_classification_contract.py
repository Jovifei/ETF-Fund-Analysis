from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from app.services.backtest_service import RotationBacktestService
from app.utils.historical_classification_contract import (
    HISTORICAL_CLASSIFICATION_CONTRACT_VERSION,
    current_metadata_classification_contract,
)


def test_current_metadata_contract_is_explicitly_not_point_in_time():
    instruments = [
        SimpleNamespace(ts_code="A.SH", theme_l1="医药", theme_l2="创新药"),
        SimpleNamespace(ts_code="B.SH", theme_l1="医药", theme_l2="医疗器械"),
    ]
    contract = current_metadata_classification_contract(instruments)
    assert contract["version"] == HISTORICAL_CLASSIFICATION_CONTRACT_VERSION
    assert contract["current_classification_only"] is True
    assert contract["effective_dated_history_available"] is False
    assert contract["theme_point_in_time_qualified"] is False
    assert contract["benchmark_membership_point_in_time_qualified"] is False
    assert contract["historical_backtest_theme_constraint_applied"] is False
    assert contract["qualification"] == "UNKNOWN"


def test_historical_backtest_does_not_use_current_theme_label_to_drop_candidate():
    service = RotationBacktestService()
    # The configured cap remains 1, but today's same-theme labels are not
    # point-in-time evidence for a historical rebalance date.
    assert int(service.config["max_per_theme"]) == 1
    service.config = {**service.config, "top_n": 2, "minimum_cross_section_score": 0.0}
    features = pd.DataFrame(
        {
            "score": [0.9, 0.8, 0.7],
            "absolute_momentum": [0.2, 0.15, 0.1],
            "volatility_20": [0.1, 0.12, 0.14],
        },
        index=["A.SH", "B.SH", "C.SH"],
    )
    instruments = {
        "A.SH": SimpleNamespace(theme_l1="医药"),
        "B.SH": SimpleNamespace(theme_l1="医药"),
        "C.SH": SimpleNamespace(theme_l1="科技"),
    }
    weights, details = service._select(
        features,
        instruments,
        positions={},
        day_index=100,
        exposure_cap=0.5,
    )
    assert list(weights) == ["A.SH", "B.SH"]
    assert details["selected"] == ["A.SH", "B.SH"]
    assert set(weights) == {"A.SH", "B.SH"}


def test_present_day_theme_labels_remain_available_for_diagnostic_grouping_only():
    instruments = [
        SimpleNamespace(ts_code="A.SH", theme_l1="医药", theme_l2=None),
    ]
    contract = current_metadata_classification_contract(instruments)
    assert contract["historical_projection_policy"] == "diagnostic_only_current_labels_projected_over_history"
    assert any("current theme labels" in item for item in contract["limitations"])

"""PIT/OOS freeze inventory: metadata never turns mock into real eligibility."""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

from app.services.pit_oos_freeze_report import build_1430_freeze_report


TZ = ZoneInfo("Asia/Shanghai")


def _report(*, tuned=False, provider=None, freeze_override=None):
    calendar = list(pd.bdate_range("2025-01-02", periods=260).date)
    test_start = calendar[240]
    cutoff = datetime(2026, 1, 15, 14, 30, tzinfo=TZ)
    earlier = cutoff - timedelta(minutes=5)
    after = cutoff + timedelta(minutes=5)
    return build_1430_freeze_report(
        calendar_dates=calendar, holdout_start=test_start,
        label_horizons=[1, 7, 20],
        cutoff=cutoff, provider_evidence=provider or {},
        strategy={"version": "offline-fixture-v1", "indicator": {"ma": [20]}},
        code_sha="a" * 40,
        frozen_at=freeze_override or datetime(2025, 8, 1, 10, tzinfo=TZ),
        holdout_access_count=0, holdout_tuned=tuned,
        holdout_access_log_hash="fixture-access-log-hash",
        feature_rows=[SimpleNamespace(trade_time=earlier, source_timestamp=earlier)],
        execution_rows=[SimpleNamespace(
            trade_time=after, source_timestamp=after,
            price=1.2, is_tradable=True,
        )],
        news_rows=[SimpleNamespace(published_at=earlier)],
        fold_count=2, fold_test_sessions=10, minimum_train_sessions=100,
    )


def test_freeze_inventory_purges_all_horizons_before_pristine_holdout():
    result = _report()
    assert result["candidate_seal_ready"] is False
    assert result["qualification"] == "UNKNOWN"
    assert result["actionable"] is False
    assert result["calibration_status"] == "not_calibrated"
    assert "provider_evidence_missing:license_storage_verified" in result["reasons"]
    assert "provider_interval_not_verified:5m" in result["reasons"]
    assert result["purged_walk_forward"]["purge_horizon"] == 20
    assert len(result["purged_walk_forward"]["folds"]) == 2
    holdout = result["pristine_holdout"]["bounds"]
    assert holdout["label_horizon"] == 20
    for fold in result["purged_walk_forward"]["folds"]:
        assert fold["purge_sessions"] >= 20
        assert fold["test_end"] < result["data_window"]["holdout_start"]
    assert result["comparisons"]["benchmark_510300.SH"] == "NOT_RUN_REAL_PIT_OOS"


def test_holdout_tuning_makes_candidate_invalid_even_with_declared_provider_evidence():
    result = _report(tuned=True)
    assert "holdout_contaminated_by_tuning" in result["reasons"]
    assert result["pristine_holdout"]["contaminated"] is True
    assert not result["candidate_seal_ready"]


def test_unverified_provider_claims_do_not_pass_rights_and_history_checks():
    report = _report(provider={
        "provider": "mock", "endpoint": "test", "intervals": ["5m", "15m"],
        "five_minute_ohlcva_verified": True, "fifteen_minute_ohlcva_verified": True,
    })
    assert report["qualification"] == "UNKNOWN"
    assert "mock_provider_not_eligible" in report["reasons"]
    assert "historical_source_records_unverified" in report["reasons"]


def test_freeze_after_holdout_start_is_rejected():
    days = list(pd.bdate_range("2025-01-02", periods=260).date)
    result = _report(freeze_override=datetime.combine(
        days[242], datetime.min.time(), tzinfo=TZ,
    ))
    assert "version_not_frozen_before_holdout" in result["reasons"]

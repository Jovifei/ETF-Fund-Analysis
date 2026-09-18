"""14:30 point-in-time rules: provisional observations are not EOD neighbors."""
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.services.pit_oos_harness import (
    SESSION_INTRADAY_1430,
    SESSION_SETTLED_EOD,
    assert_point_in_time_rows,
    assert_sessions_comparable,
    evaluate_1430_forecast_use,
    oos_walk_forward_status,
    PitLeakageError,
)
from app.services.qualification_gate import qualify_1430
from app.utils.time_split import purged_expanding_walk_forward_folds


def _calendar(count: int = 240) -> list[date]:
    start = date(2026, 1, 1)
    return [start + timedelta(days=index) for index in range(count)]


def test_1430_query_cannot_use_historical_eod_neighbors():
    with pytest.raises(PitLeakageError, match="intraday_1430_not_comparable_to_eod_neighbors"):
        assert_sessions_comparable(SESSION_INTRADAY_1430, SESSION_SETTLED_EOD)


def test_settled_eod_neighbors_remain_comparable_to_settled_eod_query():
    assert_sessions_comparable(SESSION_SETTLED_EOD, SESSION_SETTLED_EOD)


def test_post_cutoff_feature_row_is_lookahead_leakage():
    cutoff = datetime(2026, 8, 31, 14, 30)
    features = [
        SimpleNamespace(trade_time=datetime(2026, 8, 31, 14, 30)),
        SimpleNamespace(trade_time=datetime(2026, 8, 31, 15, 0)),
    ]
    labels = [SimpleNamespace(trade_time=datetime(2026, 9, 1, 15, 0))]
    with pytest.raises(PitLeakageError, match="feature_uses_post_cutoff_bar"):
        assert_point_in_time_rows(cutoff, features, labels)


def test_label_from_same_cutoff_bar_is_leakage():
    cutoff = datetime(2026, 8, 31, 14, 30)
    features = [SimpleNamespace(trade_time=datetime(2026, 8, 31, 14, 30))]
    labels = [SimpleNamespace(trade_time=datetime(2026, 8, 31, 14, 30))]
    with pytest.raises(PitLeakageError, match="label_not_strictly_after_cutoff"):
        assert_point_in_time_rows(cutoff, features, labels)


def test_oos_walk_forward_scaffolding_stays_unapproved_and_not_actionable():
    dates = _calendar(240)
    folds = purged_expanding_walk_forward_folds(
        dates, label_horizon=10, folds=4, test_sessions=20, min_train_sessions=150
    )
    status = oos_walk_forward_status(folds, approved_artifact=None)
    assert status.fold_count == 4
    assert status.approved is False
    assert status.actionable is False
    assert status.calibration_status == "not_calibrated"
    assert "oos_walk_forward_not_approved" in status.reasons


def test_overlapping_train_test_fold_is_rejected_as_leakage():
    leaky = [
        SimpleNamespace(
            fold_index=1,
            train_last=date(2026, 6, 1),
            test_start=date(2026, 6, 1),
            test_end=date(2026, 6, 20),
            purge_sessions=0,
            label_horizon=10,
        )
    ]
    status = oos_walk_forward_status(leaky, approved_artifact={"approved": True, "approved_by": "human"})
    assert status.approved is False
    assert status.actionable is False
    assert "walk_forward_train_test_overlap" in status.reasons


def test_unqualified_similarity_output_cannot_become_actionable():
    result = evaluate_1430_forecast_use(
        query_kind=SESSION_INTRADAY_1430,
        neighbor_kind=SESSION_SETTLED_EOD,
        walk_forward_approved=False,
    )
    assert result.actionable is False
    assert result.observation_kind == "provisional_1430"
    assert result.calibrated_eod is False
    assert "intraday_1430_not_comparable_to_eod_neighbors" in result.reasons
    assert "oos_walk_forward_not_approved" in result.reasons


def test_qualify_1430_keeps_provisional_observation_unactionable():
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    now = datetime(2026, 8, 31, 14, 30, tzinfo=settings.timezone)
    quote = SimpleNamespace(
        source="fixture:realtime",
        price=1.2,
        quote_time=now,
        is_realtime=True,
        timestamp_verified=True,
        degraded_reason=None,
    )
    result = qualify_1430(
        settings,
        quote,
        now,
        {"inside": True, "maximum_quote_age_minutes": 8},
    )
    assert result["actionable"] is False
    assert result["historical_1430_backtest"] == "not_qualified"
    assert "intraday_1430_not_comparable_to_eod_neighbors" in result["reasons"]
    assert "oos_walk_forward_not_approved" in result["reasons"]
    assert result["observation_kind"] == "provisional_1430"
    assert result["calibrated_eod"] is False

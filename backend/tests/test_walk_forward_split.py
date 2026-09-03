from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.utils.time_split import purged_expanding_walk_forward_folds


def _calendar(count: int = 240) -> list[date]:
    start = date(2026, 1, 1)
    return [start + timedelta(days=index) for index in range(count)]


def test_walk_forward_uses_expanding_train_and_non_overlapping_fixed_tests():
    dates = _calendar(240)
    folds = purged_expanding_walk_forward_folds(
        dates,
        label_horizon=10,
        folds=4,
        test_sessions=20,
        min_train_sessions=150,
    )

    assert len(folds) == 4
    assert [fold.train_sessions for fold in folds] == [150, 170, 190, 210]
    assert [fold.test_sessions for fold in folds] == [20, 20, 20, 20]
    assert [fold.purge_sessions for fold in folds] == [10, 10, 10, 10]

    for index, fold in enumerate(folds):
        test_start_index = dates.index(fold.test_start)
        test_end_index = dates.index(fold.test_end)
        train_last_index = dates.index(fold.train_last)
        assert test_end_index - test_start_index + 1 == 20
        assert train_last_index + fold.label_horizon < test_start_index
        assert fold.train_first == dates[0]
        if index:
            previous = folds[index - 1]
            assert dates.index(previous.test_end) + 1 == test_start_index
            assert fold.train_sessions - previous.train_sessions == 20


def test_walk_forward_embargo_extends_each_fold_purge():
    dates = _calendar(250)
    folds = purged_expanding_walk_forward_folds(
        dates,
        label_horizon=5,
        folds=3,
        test_sessions=20,
        min_train_sessions=160,
        embargo_sessions=3,
    )
    assert all(fold.purge_sessions == 8 for fold in folds)
    assert all(len(fold.purged_dates) == 8 for fold in folds)


def test_walk_forward_fails_closed_when_leakage_safe_training_history_is_too_short():
    dates = _calendar(220)
    with pytest.raises(ValueError, match="leakage-safe training sessions"):
        purged_expanding_walk_forward_folds(
            dates,
            label_horizon=10,
            folds=4,
            test_sessions=20,
            min_train_sessions=150,
        )

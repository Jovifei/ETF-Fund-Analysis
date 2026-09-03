from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.utils.time_split import purged_holdout_bounds


def _calendar(count: int = 30) -> list[date]:
    start = date(2026, 1, 1)
    return [start + timedelta(days=index) for index in range(count)]


def test_purged_holdout_excludes_labels_that_touch_test_boundary():
    dates = _calendar()
    split = purged_holdout_bounds(
        dates,
        test_start=dates[20],
        label_horizon=5,
    )

    assert split.test_start == dates[20]
    assert split.train_before == dates[15]
    assert split.train_last == dates[14]
    assert split.purged_dates == tuple(dates[15:20])
    assert split.purge_sessions == 5

    # The last allowed training sample at index 14 has a 5-session label ending
    # at index 19. It therefore cannot observe any return from the test window.
    assert dates.index(split.train_last) + split.label_horizon < dates.index(split.test_start)


def test_purged_holdout_embargo_widens_gap():
    dates = _calendar()
    split = purged_holdout_bounds(
        dates,
        test_start=dates[20],
        label_horizon=3,
        embargo_sessions=2,
    )
    assert split.train_before == dates[15]
    assert split.train_last == dates[14]
    assert split.purge_sessions == 5
    assert len(split.purged_dates) == 5


def test_purged_holdout_rejects_impossible_boundary():
    dates = _calendar(10)
    with pytest.raises(ValueError, match="not enough pre-test sessions"):
        purged_holdout_bounds(
            dates,
            test_start=dates[3],
            label_horizon=3,
        )

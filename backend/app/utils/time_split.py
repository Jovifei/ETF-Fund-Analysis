from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from typing import Iterable, TypeVar

DateT = TypeVar("DateT")


@dataclass(frozen=True, slots=True)
class PurgedHoldoutBounds:
    """Calendar bounds for a chronological holdout with horizon-aware label purge.

    A sample observed at session ``t`` with an ``h``-session forward label may only
    belong to the training set when its label is fully observable before the first
    test session. Therefore the ``h`` sessions immediately preceding the test
    boundary are excluded from training. Optional embargo sessions widen the gap.
    """

    test_start: object
    train_before: object
    train_last: object | None
    label_horizon: int
    embargo_sessions: int
    purge_sessions: int
    purged_dates: tuple[object, ...]

    def model_dump(self) -> dict[str, object]:
        return {
            "test_start": str(self.test_start),
            "train_before": str(self.train_before),
            "train_last": str(self.train_last) if self.train_last is not None else None,
            "label_horizon": self.label_horizon,
            "embargo_sessions": self.embargo_sessions,
            "purge_sessions": self.purge_sessions,
            "purged_dates": [str(value) for value in self.purged_dates],
            "rule": "training label end must be strictly earlier than first test session",
        }


@dataclass(frozen=True, slots=True)
class PurgedWalkForwardFold:
    """One expanding-train, fixed-test fold with an explicit leakage guard."""

    fold_index: int
    train_first: object
    train_before: object
    train_last: object
    test_start: object
    test_end: object
    label_horizon: int
    embargo_sessions: int
    purge_sessions: int
    purged_dates: tuple[object, ...]
    train_sessions: int
    test_sessions: int

    def model_dump(self) -> dict[str, object]:
        return {
            "fold_index": self.fold_index,
            "train_first": str(self.train_first),
            "train_before": str(self.train_before),
            "train_last": str(self.train_last),
            "test_start": str(self.test_start),
            "test_end": str(self.test_end),
            "label_horizon": self.label_horizon,
            "embargo_sessions": self.embargo_sessions,
            "purge_sessions": self.purge_sessions,
            "purged_dates": [str(value) for value in self.purged_dates],
            "train_sessions": self.train_sessions,
            "test_sessions": self.test_sessions,
            "rule": "expanding train; fixed non-overlapping test; target-overlap purge before every test fold",
        }


def purged_holdout_bounds(
    calendar_dates: Iterable[DateT],
    *,
    test_start: DateT,
    label_horizon: int,
    embargo_sessions: int = 0,
) -> PurgedHoldoutBounds:
    """Return leakage-safe train/test calendar bounds.

    This mirrors the multi-horizon truncation idea used by mature quant research
    frameworks: a longer forward label requires a larger gap before the holdout.
    The function is deliberately dependency-free and preserves the input date type.
    """

    horizon = int(label_horizon)
    embargo = int(embargo_sessions)
    if horizon <= 0:
        raise ValueError("label_horizon must be positive")
    if embargo < 0:
        raise ValueError("embargo_sessions must be non-negative")

    calendar = sorted(set(calendar_dates))
    if not calendar:
        raise ValueError("calendar_dates cannot be empty")

    split_index = bisect_left(calendar, test_start)
    if split_index >= len(calendar) or calendar[split_index] != test_start:
        raise ValueError("test_start must be present in calendar_dates")

    purge_sessions = horizon + embargo
    train_before_index = split_index - purge_sessions
    if train_before_index <= 0:
        raise ValueError("not enough pre-test sessions for requested purge")

    train_before = calendar[train_before_index]
    train_last = calendar[train_before_index - 1]
    purged_dates = tuple(calendar[train_before_index:split_index])
    return PurgedHoldoutBounds(
        test_start=calendar[split_index],
        train_before=train_before,
        train_last=train_last,
        label_horizon=horizon,
        embargo_sessions=embargo,
        purge_sessions=purge_sessions,
        purged_dates=purged_dates,
    )


def purged_expanding_walk_forward_folds(
    calendar_dates: Iterable[DateT],
    *,
    label_horizon: int,
    folds: int = 4,
    test_sessions: int = 20,
    min_train_sessions: int = 150,
    embargo_sessions: int = 0,
) -> tuple[PurgedWalkForwardFold, ...]:
    """Build non-overlapping OOS folds with expanding training history.

    The final ``folds * test_sessions`` sessions form fixed-length test windows.
    Training always starts at the first available session and expands as each test
    window rolls forward. Before every fold, ``label_horizon + embargo_sessions``
    sessions are purged so no forward target from training reaches into the OOS
    test window.
    """

    fold_count = int(folds)
    test_count = int(test_sessions)
    minimum_train = int(min_train_sessions)
    horizon = int(label_horizon)
    embargo = int(embargo_sessions)
    if fold_count <= 0:
        raise ValueError("folds must be positive")
    if test_count <= 0:
        raise ValueError("test_sessions must be positive")
    if minimum_train <= 0:
        raise ValueError("min_train_sessions must be positive")
    if horizon <= 0:
        raise ValueError("label_horizon must be positive")
    if embargo < 0:
        raise ValueError("embargo_sessions must be non-negative")

    calendar = sorted(set(calendar_dates))
    if not calendar:
        raise ValueError("calendar_dates cannot be empty")
    required_test = fold_count * test_count
    first_test_index = len(calendar) - required_test
    if first_test_index <= 0:
        raise ValueError("not enough sessions for requested walk-forward test windows")

    result: list[PurgedWalkForwardFold] = []
    for index in range(fold_count):
        test_index = first_test_index + index * test_count
        test_start = calendar[test_index]
        test_end = calendar[test_index + test_count - 1]
        guard = purged_holdout_bounds(
            calendar,
            test_start=test_start,
            label_horizon=horizon,
            embargo_sessions=embargo,
        )
        train_sessions = test_index - guard.purge_sessions
        if train_sessions < minimum_train:
            raise ValueError(
                "not enough leakage-safe training sessions for requested walk-forward configuration"
            )
        result.append(
            PurgedWalkForwardFold(
                fold_index=index + 1,
                train_first=calendar[0],
                train_before=guard.train_before,
                train_last=guard.train_last,
                test_start=test_start,
                test_end=test_end,
                label_horizon=horizon,
                embargo_sessions=embargo,
                purge_sessions=guard.purge_sessions,
                purged_dates=guard.purged_dates,
                train_sessions=train_sessions,
                test_sessions=test_count,
            )
        )
    return tuple(result)

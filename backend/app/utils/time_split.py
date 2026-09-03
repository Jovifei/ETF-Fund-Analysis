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

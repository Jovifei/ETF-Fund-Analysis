"""Point-in-time and out-of-sample gates for 14:30 research observations.

Similarity forecasts in this release match settled daily neighbors. A 14:30
provisional state is a different session kind and must not be treated as an
EOD neighbor or as a calibrated walk-forward result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

SESSION_INTRADAY_1430 = "intraday_1430_provisional"
SESSION_SETTLED_EOD = "settled_eod"


class PitLeakageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WalkForwardGate:
    approved: bool
    actionable: bool
    calibration_status: str
    fold_count: int
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ForecastUseGate:
    actionable: bool
    observation_kind: str
    calibrated_eod: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


def assert_sessions_comparable(query_kind: str, neighbor_kind: str) -> None:
    if query_kind != neighbor_kind:
        raise PitLeakageError("intraday_1430_not_comparable_to_eod_neighbors")
    if query_kind == SESSION_INTRADAY_1430:
        raise PitLeakageError("intraday_1430_neighbor_history_not_qualified")


def assert_point_in_time_rows(cutoff: datetime, feature_rows, label_rows) -> None:
    for row in feature_rows or ():
        stamp = row.trade_time
        if stamp > cutoff:
            raise PitLeakageError("feature_uses_post_cutoff_bar")
    for row in label_rows or ():
        if row.trade_time <= cutoff:
            raise PitLeakageError("label_not_strictly_after_cutoff")


def _fold_leaks(fold) -> bool:
    train_last = getattr(fold, "train_last", None)
    test_start = getattr(fold, "test_start", None)
    purge = getattr(fold, "purge_sessions", None)
    horizon = getattr(fold, "label_horizon", 0)
    if train_last is None or test_start is None:
        return True
    if train_last >= test_start:
        return True
    if purge is not None and int(purge) < int(horizon or 0):
        return True
    return False


def oos_walk_forward_status(folds, *, approved_artifact=None) -> WalkForwardGate:
    reasons: list[str] = []
    fold_list = list(folds or ())
    if not fold_list:
        reasons.append("walk_forward_folds_missing")
    elif any(_fold_leaks(fold) for fold in fold_list):
        reasons.append("walk_forward_train_test_overlap")
    artifact = approved_artifact or {}
    human_approved = bool(artifact.get("approved")) and artifact.get("approved_by") == "human"
    if not human_approved:
        reasons.append("oos_walk_forward_not_approved")
    elif "report_hash" not in artifact:
        reasons.append("oos_walk_forward_report_hash_missing")
    return WalkForwardGate(
        approved=not reasons,
        actionable=False,
        calibration_status="not_calibrated",
        fold_count=len(fold_list),
        reasons=tuple(dict.fromkeys(reasons)),
    )


def evaluate_1430_forecast_use(
    *,
    query_kind: str = SESSION_INTRADAY_1430,
    neighbor_kind: str = SESSION_SETTLED_EOD,
    walk_forward_approved: bool = False,
) -> ForecastUseGate:
    reasons: list[str] = []
    try:
        assert_sessions_comparable(query_kind, neighbor_kind)
    except PitLeakageError as exc:
        reasons.append(str(exc))
    if not walk_forward_approved:
        reasons.append("oos_walk_forward_not_approved")
    return ForecastUseGate(
        actionable=False,
        observation_kind="provisional_1430",
        calibrated_eod=False,
        reasons=tuple(dict.fromkeys(reasons)),
    )

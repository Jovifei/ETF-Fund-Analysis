"""Point-in-time and out-of-sample gates for 14:30 research observations.

Similarity forecasts in this release match settled daily neighbors. A 14:30
provisional state is a different session kind and must not be treated as an
EOD neighbor or as a calibrated walk-forward result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math

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


@dataclass(frozen=True, slots=True)
class PitEvidenceGate:
    """Evidence completeness for a historical 14:30 observation.

    This gate validates the shape and temporal ordering of supplied evidence. It
    never certifies a provider, unit, license, or strategy; callers must retain
    ``qualified=False`` until those independent reviews are complete.
    """

    qualified: bool
    actionable: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)
    causal_order_verified: bool = False


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


def _point_time(row: object, field_name: str) -> datetime | None:
    value = getattr(row, field_name, None)
    return value if isinstance(value, datetime) else None


def _usable_time(stamp: datetime | None, cutoff: datetime) -> bool:
    return (
        stamp is not None
        and stamp.tzinfo is not None and stamp.utcoffset() is not None
        and cutoff.tzinfo is not None and cutoff.utcoffset() is not None
    )


def evaluate_pit_evidence(
    cutoff: datetime,
    *,
    feature_rows=None,
    execution_rows=None,
    news_rows=None,
) -> PitEvidenceGate:
    """Validate timestamp causality only. Never qualify a source or strategy.

    Timestamp values must be timezone-aware; fetching data on a later day
    cannot prove that it was published before this historical decision.
    Bars and first executable prices need separate source-availability evidence.
    """
    reasons: list[str] = []
    features = list(feature_rows or ())
    executions = list(execution_rows or ())
    news = list(news_rows or ())
    if not _usable_time(cutoff, cutoff):
        reasons.append("cutoff_timezone_unverified")
    if not features:
        reasons.append("pit_feature_rows_missing")
    for row in features:
        trade = _point_time(row, "trade_time")
        source = _point_time(row, "source_timestamp")
        if not _usable_time(trade, cutoff):
            reasons.append("feature_trade_time_timezone_missing")
        elif trade > cutoff:
            reasons.append("feature_uses_post_cutoff_bar")
        if not _usable_time(source, cutoff):
            reasons.append("feature_source_timestamp_missing_or_unverified")
        elif source > cutoff:
            reasons.append("feature_source_timestamp_after_cutoff")
    if not executions:
        reasons.append("pit_execution_rows_missing")
    else:
        # Do not silently skip an earlier untradable quote to fabricate a fill.
        stamps = [_point_time(row, "trade_time") for row in executions]
        if not all(_usable_time(stamp, cutoff) for stamp in stamps):
            reasons.append("execution_trade_time_missing_or_unverified")
        else:
            first = min(executions, key=lambda row: row.trade_time)
            stamp = first.trade_time
            if stamp <= cutoff:
                reasons.append("execution_not_strictly_after_cutoff")
            available = _point_time(first, "source_timestamp")
            if not _usable_time(available, cutoff):
                reasons.append("execution_source_timestamp_missing_or_unverified")
            elif available < stamp:
                reasons.append("execution_source_timestamp_precedes_trade")
            price = getattr(first, "price", None)
            if (
                isinstance(price, bool) or not isinstance(price, (int, float))
                or not math.isfinite(price) or price <= 0
            ):
                reasons.append("execution_price_missing_or_invalid")
            if getattr(first, "is_tradable", None) is not True:
                reasons.append("execution_tradability_unverified")
    for row in news:
        published = _point_time(row, "published_at")
        if not _usable_time(published, cutoff):
            reasons.append("news_published_at_missing_or_unverified")
        elif published > cutoff:
            reasons.append("news_published_after_cutoff")
    causal = not reasons
    # Time-ordering by itself does not establish entitlement, retention rights,
    # bar completeness, unaltered source history, PIT revision or honest fills.
    reasons.append("provider_license_storage_and_pit_unverified")
    return PitEvidenceGate(
        qualified=False,
        actionable=False,
        reasons=tuple(dict.fromkeys(reasons)),
        causal_order_verified=causal,
    )


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

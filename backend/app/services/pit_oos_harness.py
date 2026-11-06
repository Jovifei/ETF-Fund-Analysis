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


def evaluate_pit_evidence(
    cutoff: datetime,
    *,
    feature_rows=None,
    execution_rows=None,
    news_rows=None,
) -> PitEvidenceGate:
    """Check minimum temporal evidence needed for a historical 14:30 claim.

    Rows are deliberately duck-typed so this remains usable by provider probes,
    isolated reports, and future persisted evidence models. The function checks
    only causal ordering and presence of an executable price; it does not infer
    missing timestamps, tradability, units, or publication rights.
    """

    reasons: list[str] = []
    features = list(feature_rows or ())
    executions = list(execution_rows or ())
    news = list(news_rows or ())
    if not features:
        reasons.append("pit_feature_rows_missing")
    else:
        try:
            assert_point_in_time_rows(cutoff, features, [])
        except PitLeakageError as exc:
            reasons.append(str(exc))
        for row in features:
            source_stamp = getattr(row, "source_timestamp", None)
            if source_stamp is None:
                reasons.append("feature_source_timestamp_missing")
                break
            if source_stamp > cutoff:
                reasons.append("feature_source_timestamp_after_cutoff")
                break

    if not executions:
        reasons.append("pit_execution_rows_missing")
    else:
        ordered = sorted(executions, key=lambda row: getattr(row, "trade_time", cutoff))
        first = ordered[0]
        stamp = getattr(first, "trade_time", None)
        if stamp is None:
            reasons.append("execution_trade_time_missing")
        elif stamp <= cutoff:
            reasons.append("execution_not_strictly_after_cutoff")
        price = getattr(first, "price", None)
        if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
            reasons.append("execution_price_missing_or_invalid")
        tradable = getattr(first, "is_tradable", None)
        if tradable is not True:
            reasons.append("execution_tradability_unverified")

    for row in news:
        published_at = getattr(row, "published_at", None)
        if published_at is None:
            reasons.append("news_published_at_missing")
            break
        if published_at > cutoff:
            reasons.append("news_published_after_cutoff")
            break

    unique = tuple(dict.fromkeys(reasons))
    return PitEvidenceGate(
        qualified=not unique,
        actionable=False,
        reasons=unique,
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

"""14:30 evidence-inventory and leakage-safe research freeze report.

Pure offline assessment. This module does not fetch a provider, unlock data,
promote calibration or write production state. An attestation is not validated
merely because a caller sets a boolean.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
import re
from typing import Any
from zoneinfo import ZoneInfo

from app.services.pit_oos_harness import evaluate_pit_evidence
from app.utils.hashing import stable_hash
from app.utils.time_split import purged_expanding_walk_forward_folds, purged_holdout_bounds

CN_MARKET_TZ = ZoneInfo("Asia/Shanghai")
REQUIRED_PROVIDER_EVIDENCE = (
    "provider", "endpoint", "coverage_start", "coverage_end",
    "source_timestamp_semantics", "bar_close_time_semantics",
    "five_minute_ohlcva_verified", "fifteen_minute_ohlcva_verified",
    "unit_and_adjustment_verified", "license_storage_verified",
    "retention_scope_verified", "news_publication_pit_verified",
    "first_post_cutoff_executable_price_verified", "first_fill_tradability_verified",
    "independent_provenance_receipt_hash",
)


def _date(value: date) -> str:
    return value.isoformat()


def build_1430_freeze_report(
    *,
    calendar_dates: Sequence[date],
    holdout_start: date,
    label_horizons: Sequence[int],
    cutoff: datetime,
    provider_evidence: Mapping[str, Any],
    strategy: Mapping[str, Any],
    code_sha: str,
    frozen_at: datetime | None,
    holdout_access_count: int | None,
    holdout_tuned: bool | None,
    holdout_access_log_hash: str | None,
    feature_rows: Sequence[object] = (),
    execution_rows: Sequence[object] = (),
    news_rows: Sequence[object] = (),
    fold_count: int = 4,
    fold_test_sessions: int = 20,
    minimum_train_sessions: int = 150,
    embargo_sessions: int = 0,
) -> dict[str, Any]:
    """Create an inspectable candidate gate, never an actionable qualification.

    The fold windows are built entirely on sessions preceding untouched holdout.
    Even complete metadata stays manual-review-only until provider receipts,
    rights and actual historical records are independently validated.
    """
    reasons: list[str] = []
    dates = sorted(set(calendar_dates))
    if not dates:
        reasons.append("exchange_trading_calendar_missing")
    if not label_horizons or any(isinstance(h, bool) or not isinstance(h, int) or h <= 0 for h in label_horizons):
        reasons.append("label_horizons_invalid")
    horizon = max(label_horizons) if label_horizons and "label_horizons_invalid" not in reasons else None
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        reasons.append("decision_cutoff_timezone_missing")
    elif cutoff.astimezone(CN_MARKET_TZ).time() != time(14, 30):
        reasons.append("decision_cutoff_not_1430_shanghai")
    if not re.fullmatch("[0-9a-f]{40}", code_sha or ""):
        reasons.append("frozen_commit_sha_missing_or_invalid")
    config_hash = stable_hash(strategy)
    if frozen_at is None or frozen_at.tzinfo is None or frozen_at.utcoffset() is None:
        reasons.append("version_frozen_at_missing_or_unverified")
    elif frozen_at.astimezone(CN_MARKET_TZ).date() >= holdout_start:
        reasons.append("version_not_frozen_before_holdout")
    if holdout_tuned is True:
        reasons.append("holdout_contaminated_by_tuning")
    if holdout_tuned is not False or holdout_access_count != 0 or not holdout_access_log_hash:
        reasons.append("pristine_holdout_access_evidence_missing")

    provider = dict(provider_evidence)
    missing = []
    for key in REQUIRED_PROVIDER_EVIDENCE:
        value = provider.get(key)
        if key.endswith("_verified"):
            valid = value is True
        else:
            valid = isinstance(value, str) and bool(value.strip())
        if not valid:
            missing.append(key)
            reasons.append("provider_evidence_missing:" + key)
    for label in ("5m", "15m"):
        if label not in str(provider.get("intervals", "")):
            reasons.append("provider_interval_not_verified:" + label)
    if not provider.get("source_record_hashes"):
        reasons.append("historical_source_records_unverified")
    if not provider.get("historical_universe_pit_verified"):
        reasons.append("historical_universe_pit_missing")
    if not provider.get("historical_theme_pit_verified"):
        reasons.append("historical_theme_pit_missing")
    if not provider.get("historical_price_limit_pit_verified"):
        reasons.append("historical_price_limits_pit_missing")
    if provider.get("source") == "mock" or str(provider.get("provider", "")).lower() == "mock":
        reasons.append("mock_provider_not_eligible")

    timing = evaluate_pit_evidence(
        cutoff, feature_rows=feature_rows,
        execution_rows=execution_rows, news_rows=news_rows,
    )
    reasons.extend(item for item in timing.reasons if item != "provider_license_storage_and_pit_unverified")
    # Temporal evidence is distinct from independently reviewed provider rights.
    if not timing.causal_order_verified:
        reasons.append("intraday_causal_order_unproven")
    if not news_rows:
        reasons.append("news_population_or_verified_absence_missing")

    holdout = None
    folds = []
    if dates and horizon is not None:
        try:
            guard = purged_holdout_bounds(
                dates, test_start=holdout_start,
                label_horizon=horizon, embargo_sessions=embargo_sessions,
            )
            holdout = guard.model_dump()
            pre_holdout = [day for day in dates if day < holdout_start]
            folds = [
                fold.model_dump()
                for fold in purged_expanding_walk_forward_folds(
                    pre_holdout, label_horizon=horizon, folds=fold_count,
                    test_sessions=fold_test_sessions,
                    min_train_sessions=minimum_train_sessions,
                    embargo_sessions=embargo_sessions,
                )
            ]
            if any(date.fromisoformat(fold["test_end"]) >= holdout_start for fold in folds):
                reasons.append("walk_forward_fold_overlaps_pristine_holdout")
        except (ValueError, TypeError) as exc:
            reasons.append("walk_forward_or_holdout_bounds_invalid:" + type(exc).__name__)
    else:
        reasons.append("walk_forward_bounds_missing")

    candidate_ready = not reasons
    return {
        "schema_version": "pit-oos-freeze-candidate-v1",
        "mode": "offline_evidence_inventory",
        "as_of_cutoff": cutoff.isoformat(),
        "data_window": {
            "calendar_first": _date(dates[0]) if dates else None,
            "calendar_last": _date(dates[-1]) if dates else None,
            "holdout_start": holdout_start.isoformat(),
            "provider_coverage_start": provider.get("coverage_start"),
            "provider_coverage_end": provider.get("coverage_end"),
        },
        "source": {
            "provider": provider.get("provider"),
            "endpoint": provider.get("endpoint"),
            "intervals": provider.get("intervals"),
            "field_contract": {
                "ohlcva": "5m/15m OHLCV+amount",
                "source_timestamp_semantics": provider.get("source_timestamp_semantics"),
                "bar_close_time_semantics": provider.get("bar_close_time_semantics"),
                "license_storage_verified": provider.get("license_storage_verified") is True,
                "retention_scope_verified": provider.get("retention_scope_verified") is True,
            },
            "record_hashes": provider.get("source_record_hashes"),
            "independent_receipt_hash": provider.get("independent_provenance_receipt_hash"),
            "missing_evidence_fields": missing,
        },
        "frozen_identity": {
            "code_sha": code_sha,
            "strategy_version": strategy.get("version"),
            "strategy_replay_version": strategy.get("strategy_replay_version"),
            "parameter_hash": config_hash,
            "frozen_at": frozen_at.isoformat() if frozen_at else None,
        },
        "purged_walk_forward": {
            "label_horizons": list(label_horizons), "purge_horizon": horizon,
            "embargo_sessions": embargo_sessions, "folds": folds,
        },
        "pristine_holdout": {
            "bounds": holdout, "access_count": holdout_access_count,
            "tuned_on_holdout": holdout_tuned,
            "access_log_hash": holdout_access_log_hash,
            "contaminated": holdout_tuned is True,
        },
        "14_30_causal_gate": {
            "causal_order_verified": timing.causal_order_verified,
            "qualification": "UNKNOWN",
        },
        "comparisons": {
            "previous_version": "NOT_RUN_REAL_PIT_OOS",
            "benchmark_510300.SH": "NOT_RUN_REAL_PIT_OOS",
            "leakage_negative_examples": [
                "future_news_publication", "post_cutoff_feature_bar",
                "holdout_tuning_contamination", "unverified_execution_price",
            ],
        },
        "candidate_seal_ready": candidate_ready,
        "qualification": "UNKNOWN",
        "actionable": False,
        "calibration_status": "not_calibrated",
        "manual_approval_required": True,
        "reasons": sorted(set(reasons)),
    }


__all__ = ["build_1430_freeze_report", "REQUIRED_PROVIDER_EVIDENCE"]

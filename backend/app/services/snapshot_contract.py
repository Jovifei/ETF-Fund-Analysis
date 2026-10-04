"""Read-time snapshot compatibility and provenance contract.

Historical audit paths may inspect old snapshots directly. Current-state consumers
must first select the temporally latest persisted row and then validate that row
against the current strategy identity; they never silently fall back to an older
compatible snapshot.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.utils.hashing import stable_hash

SNAPSHOT_CONTRACT_VERSION = "current-snapshot-v3-temporal"
SIGNAL_INPUT_CONTRACT_VERSION = "signal-snapshot-inputs-v1"
SIGNAL_FORECAST_SCORE_WEIGHTS = {1: 0.5, 5: 0.3}


def formal_forecast_horizons(strategy: dict[str, Any]) -> list[int]:
    return [int(value) for value in strategy.get("forecast", {}).get("horizons", ())]


def signal_forecast_score_weights(strategy: dict[str, Any]) -> dict[int, float]:
    formal = set(formal_forecast_horizons(strategy))
    return {
        horizon: weight
        for horizon, weight in SIGNAL_FORECAST_SCORE_WEIGHTS.items()
        if horizon in formal
    }


def snapshot_issues(
    row,
    settings,
    expected_date,
    *,
    kind="indicator",
    at: datetime | None = None,
) -> list[str]:
    if row is None:
        return [f"{kind}_missing"]
    if kind not in {"indicator", "forecast"}:
        raise ValueError("kind must be indicator or forecast")
    cfg = settings.load_strategy()
    version = getattr(row, "version" if kind == "indicator" else "model_version", None)
    reasons: list[str] = []
    if version != cfg["indicator_version" if kind == "indicator" else "forecast_version"]:
        reasons.append(f"{kind}_version_mismatch")
    if getattr(row, "feature_schema_version", None) != cfg["feature_schema_version"]:
        reasons.append(f"{kind}_schema_mismatch")
    if getattr(row, "config_hash", None) != stable_hash(cfg):
        reasons.append(f"{kind}_config_mismatch")
    if expected_date is not None and getattr(row, "as_of_date", None) != expected_date:
        reasons.append(f"{kind}_date_mismatch")
    reference = _normalize_time(at, settings) if at is not None else None
    if reference is not None:
        row_date = getattr(row, "as_of_date", None)
        if row_date is not None and row_date > reference.date():
            reasons.append(f"{kind}_from_future")
        generated = _normalize_time(getattr(row, "generated_at", None), settings)
        if generated is not None and generated > reference:
            reasons.append(f"{kind}_generated_in_future")
    return reasons


def current_snapshot(
    row,
    settings,
    *,
    kind="indicator",
    expected_date=None,
    at: datetime | None = None,
):
    """Return the latest row only if it is compatible with current identity/time."""
    return row if not snapshot_issues(
        row, settings, expected_date, kind=kind, at=at
    ) else None


def _normalize_time(value: datetime | None, settings) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=settings.timezone) if value.tzinfo is None else value.astimezone(settings.timezone)


def signal_issues(row, settings, *, at: datetime | None = None) -> list[str]:
    if row is None:
        return ["signal_missing"]
    cfg = settings.load_strategy()
    reasons: list[str] = []
    if getattr(row, "strategy_version", None) != cfg["version"]:
        reasons.append("signal_strategy_version_mismatch")
    if getattr(row, "indicator_version", None) != cfg["indicator_version"]:
        reasons.append("signal_indicator_version_mismatch")
    if getattr(row, "forecast_version", None) != cfg["forecast_version"]:
        reasons.append("signal_forecast_version_mismatch")

    evidence = row.evidence_json if isinstance(getattr(row, "evidence_json", None), dict) else {}
    inputs = evidence.get("snapshot_inputs") if isinstance(evidence.get("snapshot_inputs"), dict) else None
    if inputs is None:
        reasons.append("signal_snapshot_input_provenance_missing")
    else:
        if inputs.get("contract_version") != SIGNAL_INPUT_CONTRACT_VERSION:
            reasons.append("signal_snapshot_input_contract_mismatch")
        formal = formal_forecast_horizons(cfg)
        if [int(value) for value in inputs.get("formal_forecast_horizons", [])] != formal:
            reasons.append("signal_forecast_horizon_contract_mismatch")
        expected_weights = {
            str(key): value for key, value in signal_forecast_score_weights(cfg).items()
        }
        if inputs.get("forecast_score_horizon_weights") != expected_weights:
            reasons.append("signal_forecast_score_weight_contract_mismatch")

        indicator = inputs.get("indicator")
        if indicator is not None:
            if not isinstance(indicator, dict):
                reasons.append("signal_indicator_provenance_invalid")
            else:
                if indicator.get("version") != cfg["indicator_version"]:
                    reasons.append("signal_indicator_provenance_version_mismatch")
                if indicator.get("feature_schema_version") != cfg["feature_schema_version"]:
                    reasons.append("signal_indicator_provenance_schema_mismatch")
                if indicator.get("config_hash") != stable_hash(cfg):
                    reasons.append("signal_indicator_provenance_config_mismatch")

        forecasts = inputs.get("forecasts")
        if not isinstance(forecasts, dict):
            reasons.append("signal_forecast_provenance_invalid")
        else:
            for identity in forecasts.values():
                if not isinstance(identity, dict):
                    reasons.append("signal_forecast_provenance_invalid")
                    break
                if identity.get("model_version") != cfg["forecast_version"]:
                    reasons.append("signal_forecast_provenance_version_mismatch")
                    break
                if identity.get("feature_schema_version") != cfg["feature_schema_version"]:
                    reasons.append("signal_forecast_provenance_schema_mismatch")
                    break
                if identity.get("config_hash") != stable_hash(cfg):
                    reasons.append("signal_forecast_provenance_config_mismatch")
                    break

        expected_hash = stable_hash({"snapshot_inputs": inputs, "strategy": cfg})
        if getattr(row, "input_hash", None) != expected_hash:
            reasons.append("signal_input_hash_mismatch")

    reference = _normalize_time(at, settings)
    signal_time = _normalize_time(getattr(row, "as_of_time", None), settings)
    expiry = _normalize_time(getattr(row, "expires_at", None), settings)
    if reference is not None and signal_time is not None and signal_time > reference:
        reasons.append("signal_from_future")
    if reference is not None and expiry is not None and expiry <= reference:
        reasons.append("signal_expired")
    return list(dict.fromkeys(reasons))


def current_signal(row, settings, *, at: datetime | None = None):
    return row if not signal_issues(row, settings, at=at) else None


def quote_issues(row, settings, *, at: datetime | None = None) -> list[str]:
    if row is None:
        return ["quote_missing"]
    reference = _normalize_time(
        at or datetime.now(settings.timezone), settings
    )
    reasons: list[str] = []
    quote_time = _normalize_time(getattr(row, "quote_time", None), settings)
    fetched_at = _normalize_time(getattr(row, "fetched_at", None), settings)
    if quote_time is None:
        reasons.append("quote_time_missing")
    elif quote_time > reference:
        reasons.append("quote_from_future")
    if fetched_at is not None and fetched_at > reference:
        reasons.append("quote_fetched_in_future")
    return reasons


def current_quote(row, settings, *, at: datetime | None = None):
    return row if not quote_issues(row, settings, at=at) else None


def snapshot_issue_map(
    rows: dict[int, Any],
    settings,
    *,
    kind: str,
    at: datetime | None = None,
) -> tuple[dict[int, Any], dict[int, list[str]]]:
    """Filter a latest-row map without falling back to older snapshots."""
    current: dict[int, Any] = {}
    issues: dict[int, list[str]] = {}
    for ident, row in rows.items():
        problem = snapshot_issues(row, settings, None, kind=kind, at=at)
        if problem:
            issues[ident] = problem
        else:
            current[ident] = row
    return current, issues

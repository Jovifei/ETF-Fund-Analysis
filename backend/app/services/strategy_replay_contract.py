"""Shared identity and qualification contract for runtime/backtest strategy evidence.

The contract makes the current mismatch explicit: runtime observations and the
factor-rotation backtest share strategy identity metadata, while the backtest
continues to report that it is not an exact replay until its selector is
switched to the runtime family evaluator.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.utils.hashing import stable_hash


STRATEGY_REPLAY_CONTRACT_VERSION = "strategy-replay-contract-v2"
STRATEGY_FAMILIES = (
    "trend",
    "momentum",
    "volume_flow",
    "breakout",
    "pullback",
    "structure",
    "relative_strength",
    "reversal",
)


def _strategy_identity(strategy: Mapping[str, Any]) -> dict[str, Any]:
    """Bind every input that can change the runtime decision or replay ledger.

    A family-weight-only digest was unsafe: an indicator window, risk gate,
    target cap, forecast weight or execution rule could change invisibly.
    The digest is of frozen configuration data, not a claim of PIT provenance.
    """
    engine = strategy.get("strategy_engine") or {}
    weights = {
        family: float((engine.get("family_weights") or {}).get(family, 0.0))
        for family in STRATEGY_FAMILIES
    }
    relevant = {
        key: strategy.get(key)
        for key in (
            "market_data_contract_version", "version", "indicator_version",
            "forecast_version", "backtest_version", "strategy_replay_version",
            "feature_schema_version", "indicator", "strategy_engine", "signal",
            "forecast", "backtest", "intervals",
        )
    }
    identity = {
        "contract_version": STRATEGY_REPLAY_CONTRACT_VERSION,
        "strategy_version": strategy.get("version"),
        "strategy_engine_version": engine.get("version"),
        "strategy_replay_version": strategy.get("strategy_replay_version"),
        "family_order": list(STRATEGY_FAMILIES),
        "family_weights": weights,
        "signal_thresholds": {
            key: (strategy.get("signal") or {}).get(key)
            for key in ("entry_score", "probe_score", "reduce_score", "hard_reduce_score")
        },
        "decision_config_hash": stable_hash(relevant),
    }
    identity["identity_hash"] = stable_hash(identity)
    return identity


def build_strategy_replay_contract(
    strategy: Mapping[str, Any],
    *,
    status: str,
    source: str,
    feature_basis: str,
    as_of: str | None = None,
    family_scores: Mapping[str, Any] | None = None,
    composite_score: float | None = None,
    reason: str | None = None,
    not_replayed: list[str] | tuple[str, ...] | None = None,
    action: str | None = None,
    target_weight: float | None = None,
    first_step_target_weight: float | None = None,
    market_regime: str | None = None,
) -> dict[str, Any]:
    """Return a stable, fail-closed identity for strategy evidence."""

    identity = _strategy_identity(strategy)
    payload: dict[str, Any] = {
        **identity,
        "status": status,
        "source": source,
        "feature_basis": feature_basis,
        "as_of": as_of,
        "family_scores": (
            {family: family_scores.get(family) for family in STRATEGY_FAMILIES}
            if family_scores is not None
            else None
        ),
        "composite_score": composite_score,
        "qualification": "UNKNOWN",
        "actionable": False,
        "calibration_status": "not_calibrated",
        "not_replayed": sorted(set(not_replayed or ())),
        "action": action,
        "target_weight": target_weight,
        "first_step_target_weight": first_step_target_weight,
        "market_regime": market_regime,
    }
    if reason:
        payload["reason"] = reason
    return payload


__all__ = [
    "STRATEGY_FAMILIES",
    "STRATEGY_REPLAY_CONTRACT_VERSION",
    "build_strategy_replay_contract",
]

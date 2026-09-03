from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

DEFAULT_RESEARCH_HORIZONS: tuple[int, ...] = (1, 3, 5, 10)


def normalize_horizons(
    values: Sequence[object] | None,
    *,
    default: tuple[int, ...] = DEFAULT_RESEARCH_HORIZONS,
) -> tuple[int, ...]:
    """Normalize a configured prediction-horizon list without silently reordering it."""
    source = values if values is not None else default
    result: list[int] = []
    for raw in source:
        value = int(raw)
        if value <= 0:
            raise ValueError("prediction horizons must be positive")
        if value not in result:
            result.append(value)
    if not result:
        raise ValueError("at least one prediction horizon is required")
    return tuple(result)


def section_horizons(
    strategy: Mapping[str, Any],
    section: str,
    *,
    default: tuple[int, ...] = DEFAULT_RESEARCH_HORIZONS,
) -> tuple[int, ...]:
    config = strategy.get(section, {})
    values = config.get("horizons") if isinstance(config, Mapping) else None
    return normalize_horizons(values, default=default)


def aligned_research_horizons(strategy: Mapping[str, Any]) -> tuple[int, ...]:
    """Return the shared forecast/factor horizon contract or fail on configuration drift."""
    forecast = section_horizons(strategy, "forecast")
    factors = section_horizons(strategy, "factor_analysis")
    if forecast != factors:
        raise ValueError(
            "forecast.horizons and factor_analysis.horizons must match; "
            f"got forecast={forecast}, factor_analysis={factors}"
        )
    return forecast

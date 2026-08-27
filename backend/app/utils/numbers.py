from __future__ import annotations

import math
from typing import Any


def finite_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def percentile_rank(values: list[float], current: float) -> float:
    clean = sorted(v for v in values if math.isfinite(v))
    if not clean:
        return 50.0
    below = sum(1 for v in clean if v < current)
    equal = sum(1 for v in clean if v == current)
    return 100.0 * (below + 0.5 * equal) / len(clean)

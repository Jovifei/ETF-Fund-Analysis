"""Research-only structure_v1 fill from OHLCV history.

Soft-imports the in-repo package under research/etf_structure_features.
Never calls assign_grade; missing/insufficient bars → None (UI shows —).
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

# Repo root: backend/app/research/structure_v1.py → parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PKG_PARENT = _REPO_ROOT / "research" / "etf_structure_features"


@lru_cache(maxsize=1)
def _load_build_structure_row():
    if not _PKG_PARENT.is_dir():
        return None
    path = str(_PKG_PARENT)
    if path not in sys.path:
        sys.path.insert(0, path)
    try:
        from etf_structure_features import build_structure_row  # type: ignore

        return build_structure_row
    except Exception:
        return None


def structure_v1_from_history(
    *,
    ts_code: str,
    history: list[dict[str, Any]] | None,
    name: str | None = None,
    min_bars: int = 20,
) -> dict[str, Any] | None:
    """Build structure_v1 from board history bars. Soft-fail → None."""
    build = _load_build_structure_row()
    if build is None or not history:
        return None
    bars = [
        b
        for b in history
        if isinstance(b, dict)
        and not b.get("is_forecast")
        and b.get("close") is not None
        and b.get("high") is not None
        and b.get("low") is not None
    ]
    if len(bars) < min_bars:
        return None
    try:
        opens = [float(b.get("open") if b.get("open") is not None else b["close"]) for b in bars]
        highs = [float(b["high"]) for b in bars]
        lows = [float(b["low"]) for b in bars]
        closes = [float(b["close"]) for b in bars]
        volumes = [float(b["volume"]) if b.get("volume") is not None else 0.0 for b in bars]
        as_of = str(bars[-1].get("date") or "")[:10]
        if not as_of:
            return None
        row = build(
            ts_code=ts_code,
            as_of=as_of,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            name=name,
        )
        if not isinstance(row, dict) or row.get("schema_version") != "structure_v1":
            return None
        return row
    except Exception:
        return None


# Keys the structure_fund_row schema marks as required; a block that claims
# schema_version "structure_v1" without them is incomplete and must be
# refilled from bars rather than passed through to the board.
_STRUCTURE_V1_REQUIRED = frozenset(
    {
        "schema_version",
        "ts_code",
        "as_of",
        "wyckoff_phase",
        "wyckoff_score",
        "wyckoff_confidence",
        "dow_phase",
        "dow_score",
        "dow_confidence",
        "atr14",
        "atr_pct",
        "atr_risk_bucket",
        "evidence",
        "research_only",
    }
)


def resolve_structure_v1(
    *,
    existing: Any,
    ts_code: str,
    history: list[dict[str, Any]] | None,
    name: str | None = None,
) -> dict[str, Any] | None:
    """Prefer an already-attached structure_v1 block; else fill from bars."""
    if isinstance(existing, dict):
        if existing.get("schema_version") == "structure_v1":
            if _STRUCTURE_V1_REQUIRED <= existing.keys():
                return existing
        elif existing.get("schema_version") is None and "wyckoff_phase" in existing:
            return existing
    return structure_v1_from_history(ts_code=ts_code, history=history, name=name)

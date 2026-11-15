"""Research-only structure_v1 fill from OHLCV history.

Soft-imports the in-repo package under research/etf_structure_features.
Never calls assign_grade; missing/insufficient bars → None (UI shows —).
"""

from __future__ import annotations

import math
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


def _is_finite_num(v: Any) -> bool:
    if v is None or isinstance(v, bool):
        return False
    try:
        f = float(v)
        return math.isfinite(f)
    except (TypeError, ValueError, OverflowError):
        return False


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
        and _is_finite_num(b.get("close"))
        and _is_finite_num(b.get("high"))
        and _is_finite_num(b.get("low"))
    ]
    if len(bars) < min_bars:
        return None
    try:
        opens = [
            float(b.get("open"))
            if _is_finite_num(b.get("open"))
            else float(b["close"])
            for b in bars
        ]
        highs = [float(b["high"]) for b in bars]
        lows = [float(b["low"]) for b in bars]
        closes = [float(b["close"]) for b in bars]
        volumes = [
            float(b["volume"])
            if _is_finite_num(b.get("volume")) and float(b["volume"]) >= 0
            else 0.0
            for b in bars
        ]
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
    target_code = str(ts_code or "").strip().upper()
    if isinstance(existing, dict):
        existing_code = str(existing.get("ts_code") or "").strip().upper()
        if existing_code and existing_code == target_code:
            # Check period / interval if specified
            if existing.get("period") in (None, "1d") and existing.get("interval") in (None, "1d"):
                # If history has valid settled bars, check as_of date alignment
                valid_bars = [
                    b
                    for b in (history or [])
                    if isinstance(b, dict) and not b.get("is_forecast") and _is_finite_num(b.get("close"))
                ]
                stale = False
                if valid_bars:
                    last_date = str(valid_bars[-1].get("date") or "")[:10]
                    existing_date = str(existing.get("as_of") or "")[:10]
                    if last_date and existing_date and last_date != existing_date:
                        stale = True

                if not stale:
                    if existing.get("schema_version") == "structure_v1":
                        if _STRUCTURE_V1_REQUIRED <= existing.keys():
                            return existing
                    elif existing.get("schema_version") is None and "wyckoff_phase" in existing:
                        return existing

    return structure_v1_from_history(ts_code=ts_code, history=history, name=name)

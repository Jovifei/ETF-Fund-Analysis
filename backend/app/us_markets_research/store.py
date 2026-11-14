"""Load a built snapshot for display (bundle producer or local file view).

The snapshot file is produced by ``scripts/build_us_markets_research.py``.
Loading is opt-in via ``US_MARKETS_RESEARCH_SNAPSHOT_PATH``; when it is not set
nothing is attached anywhere and bundles stay byte-identical to before.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.us_markets_research.contracts import validate_part

ENV_SNAPSHOT_PATH = "US_MARKETS_RESEARCH_SNAPSHOT_PATH"
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
# A Friday US close is still current on Monday morning in Asia; allow a long weekend.
FRESH_MAX_AGE_DAYS = 5


def configured_path(env: Mapping[str, str] | None = None) -> Path | None:
    value = (env if env is not None else os.environ).get(ENV_SNAPSHOT_PATH, "").strip()
    return Path(value) if value else None


def load_snapshot_file(path: Path | str) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(part, None)`` or ``(None, reason_code)``; never raises."""
    target = Path(path)
    try:
        if not target.is_file():
            return None, "us_markets_research_file_missing"
        if target.stat().st_size > MAX_SNAPSHOT_BYTES:
            return None, "us_markets_research_file_too_large"
        part = json.loads(target.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None, "us_markets_research_file_unreadable"
    if validate_part(part):
        return None, "us_markets_research_contract_invalid"
    return part, None


def load_for_bundle(env: Mapping[str, str] | None = None) -> dict[str, Any] | None:
    """Part to attach to a local-display bundle, or ``None`` (default: not configured)."""
    path = configured_path(env)
    if path is None:
        return None
    part, _reason = load_snapshot_file(path)
    return part


def source_age_days(part: Mapping[str, Any], now: datetime | None = None) -> int | None:
    as_of = part.get("as_of")
    if not isinstance(as_of, str):
        return None
    try:
        day = date.fromisoformat(as_of[:10])
    except ValueError:
        return None
    return (((now or datetime.now(timezone.utc))).date() - day).days


def read_envelope(part: dict[str, Any] | None, reason: str | None, *, now: datetime | None = None,
                  extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Versioned read model shared by the bundle reader and the file view."""
    now = now or datetime.now(timezone.utc)
    age = source_age_days(part, now) if part else None
    availability = (part or {}).get("availability") if part else "unpublished"
    return {
        "read_contract": "us-markets-research-read-v1",
        "availability": availability,
        "available": part is not None and availability in {"available", "partial"},
        "reason": reason,
        "research": part,
        "source_age_days": age,
        "source_stale": age is None or age > FRESH_MAX_AGE_DAYS if part else None,
        "read_at": now.isoformat(),
        "provider_called": False,
        "research_only": True,
        "actionable": False,
        "changes_grade": False,
        "calibration_status": "not_calibrated",
        **(extra or {}),
    }

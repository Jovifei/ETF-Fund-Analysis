from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import ReportArtifact
from app.utils.hashing import stable_hash

MAX_JSON_REPORT_BYTES = 4_000_000


def latest_system_report(db: Session, report_type: str) -> ReportArtifact | None:
    """Return the most recently appended global report of one type.

    ReportArtifact.as_of_time is semantic report time and may be timezone-stripped
    by SQLite. Calculation-grade consumers use monotonic append identity instead.
    User-owned reports are never eligible for system calculations.
    """
    return db.scalars(
        select(ReportArtifact)
        .where(
            ReportArtifact.report_type == str(report_type),
            ReportArtifact.user_id.is_(None),
        )
        .order_by(ReportArtifact.id.desc())
        .limit(1)
    ).first()


def read_system_json_report(
    artifact: ReportArtifact,
    settings: Settings,
    *,
    expected_type: str | None = None,
    max_bytes: int = MAX_JSON_REPORT_BYTES,
) -> dict[str, Any]:
    """Read and authenticate one persisted system JSON report.

    The artifact must be global, live under the configured reports root, remain
    below the bounded size, be a JSON object of the expected type, and match the
    persisted content hash.
    """
    if artifact.user_id is not None:
        raise ValueError("user_owned_report_not_eligible_for_system_calculation")
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")

    root = settings.reports_dir.resolve()
    path = Path(artifact.file_path).resolve(strict=True)
    path.relative_to(root)
    if path.suffix.lower() != ".json":
        raise ValueError("system calculation report must be JSON")

    with path.open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("report too large")

    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("report must be a JSON object")
    if expected_type is not None and payload.get("report_type") != expected_type:
        raise ValueError("report type mismatch")
    if stable_hash(payload) != artifact.content_hash:
        raise ValueError("report content hash mismatch")
    return payload

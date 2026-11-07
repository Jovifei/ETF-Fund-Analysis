"""Write-once, research-only 14:30 shadow evidence, never a trading instruction."""
from __future__ import annotations

from datetime import date, datetime, time
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from app.utils.hashing import stable_hash


MARKET_TZ = ZoneInfo("Asia/Shanghai")


def _validate_evidence_dates(record: Mapping[str, Any], cutoff: datetime) -> None:
    for key in ("feature_available_at", "news_published_at", "quote_source_at"):
        raw = record.get(key)
        if raw is None:
            continue
        if not isinstance(raw, str):
            raise ValueError("shadow_timestamp_invalid:" + key)
        try:
            stamp = datetime.fromisoformat(raw)
        except ValueError:
            raise ValueError("shadow_timestamp_invalid:" + key) from None
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("shadow_timestamp_timezone_missing:" + key)
        if stamp > cutoff:
            raise ValueError("shadow_post_cutoff_input:" + key)


def write_1430_shadow_snapshot(
    *,
    reports_dir: Path,
    target_date: date,
    market_cutoff: datetime,
    code_sha: str,
    parameters_hash: str,
    observations: Mapping[str, Mapping[str, Any]],
    source_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist a single immutable daily snapshot using atomic exclusive creation.

    The directory is a *research* output folder. A duplicate decision date is
    rejected even for identical content, making backfills and retuning visible.
    Offline fixtures never count as a real historical session acceptance.
    """
    if (
        market_cutoff.tzinfo is None or market_cutoff.utcoffset() is None
        or market_cutoff.astimezone(MARKET_TZ).date() != target_date
        or market_cutoff.astimezone(MARKET_TZ).time() != time(14, 30)
    ):
        raise ValueError("shadow_requires_market_1430_cutoff")
    if not re.fullmatch(r"[a-f0-9]{40}", code_sha):
        raise ValueError("shadow_commit_sha_missing")
    if not re.fullmatch(r"[a-f0-9]{64}", parameters_hash):
        raise ValueError("shadow_parameter_hash_missing")
    if not observations:
        raise ValueError("shadow_observations_missing")
    for code, record in observations.items():
        if not re.fullmatch(r"[A-Za-z0-9_.-]{4,32}", code):
            raise ValueError("shadow_instrument_identifier_invalid")
        if not isinstance(record, Mapping):
            raise ValueError("shadow_record_invalid")
        _validate_evidence_dates(record, market_cutoff)
        if (record.get("actionable") not in (None, False)
                or record.get("calibration_status") not in (None, "not_calibrated")
                or record.get("qualification") not in (None, "UNKNOWN")):
            raise ValueError("shadow_snapshot_must_be_research_only")

    payload = {
        "schema_version": "shadow-1430-daily-v1",
        "target_date": target_date.isoformat(),
        "market_cutoff": market_cutoff.isoformat(),
        "git_commit_sha": code_sha,
        "parameters_hash": parameters_hash,
        "source_evidence": dict(source_evidence),
        "observations": {
            code: {**dict(record), "qualification": "UNKNOWN",
                   "actionable": False, "calibration_status": "not_calibrated"}
            for code, record in sorted(observations.items())
        },
        "qualification": "UNKNOWN",
        "actionable": False,
        "calibration_status": "not_calibrated",
        "promotion_policy": "at_least_20_natural_trading_days_and_human_approval",
        "mutable_thresholds": False,
    }
    digest = stable_hash(payload)
    envelope = {"content_hash": digest, "payload": payload}
    data = (json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    root = Path(reports_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"shadow_1430_{target_date:%Y%m%d}.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    # 0600 avoids exposing personal research observations to other local users.
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        # Keep partial file as a blocked/inspectable artifact; no silent retry or overwrite.
        raise
    return {
        "path": str(path), "target_date": target_date.isoformat(),
        "content_hash": digest, "qualification": "UNKNOWN",
        "actionable": False, "calibration_status": "not_calibrated",
        "write_policy": "exclusive_create_no_overwrite",
    }


def verify_shadow_snapshot(path: Path) -> bool:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return (
            isinstance(doc, dict)
            and isinstance(doc.get("payload"), dict)
            and doc.get("content_hash") == stable_hash(doc["payload"])
            and doc["payload"].get("actionable") is False
        )
    except (OSError, ValueError, TypeError, KeyError):
        return False

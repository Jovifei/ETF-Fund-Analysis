"""Contracts and integrity checks for local-display-v2 bundles."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.workspace.shadow_bundle import digest

CONTRACT_VERSION = "local-display-v2"
MAX_BUNDLE_BYTES = 64 * 1024 * 1024  # 64 MiB bounded quota
REQUIRED_PARTS = {"overview", "details", "charts", "sectors"}
FORBIDDEN_PRIVATE_FIELDS = {"avg_cost", "holdings", "cost", "trades", "account_id", "user_id"}


@dataclass
class LocalDisplayManifest:
    contract_version: str
    code_sha: str
    config_hash: str
    sequence: int
    generated_at: str
    expires_at: str
    actionable: bool
    data_origin: str
    universe: list[str]
    parts_hashes: dict[str, str]


def _parse_iso(ts_str: str) -> datetime:
    if not isinstance(ts_str, str) or not ts_str:
        raise ValueError("invalid timestamp string")
    dt = datetime.fromisoformat(ts_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def validate_bundle_manifest(manifest_dict: dict[str, Any]) -> LocalDisplayManifest:
    if not isinstance(manifest_dict, dict):
        raise ValueError("manifest must be a dictionary")
    if manifest_dict.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(f"contract_version must be {CONTRACT_VERSION}")
    if manifest_dict.get("actionable") is not False:
        raise ValueError("actionable must be false in local display contract")
    code_sha = manifest_dict.get("code_sha")
    if not isinstance(code_sha, str) or len(code_sha) < 7:
        raise ValueError("valid code_sha is required")
    if not isinstance(manifest_dict.get("config_hash"), str) or not manifest_dict.get("config_hash"):
        raise ValueError("config_hash is required")
    sequence = manifest_dict.get("sequence")
    if not isinstance(sequence, int) or sequence <= 0:
        raise ValueError("positive sequence integer is required")
    
    generated_at_str = manifest_dict.get("generated_at")
    expires_at_str = manifest_dict.get("expires_at")
    if not generated_at_str or not expires_at_str:
        raise ValueError("generated_at and expires_at are required")
    
    gen_dt = _parse_iso(generated_at_str)
    exp_dt = _parse_iso(expires_at_str)
    if exp_dt <= gen_dt:
        raise ValueError("expires_at must be strictly greater than generated_at")

    universe = manifest_dict.get("universe")
    if not isinstance(universe, list) or len(universe) == 0:
        raise ValueError("universe must be a non-empty list of symbols")
    if not all(isinstance(s, str) and s.strip() for s in universe):
        raise ValueError("all universe items must be non-empty strings")

    parts_hashes = manifest_dict.get("parts_hashes")
    if not isinstance(parts_hashes, dict) or not parts_hashes:
        raise ValueError("parts_hashes must be a non-empty dictionary")
    
    missing_parts = REQUIRED_PARTS - set(parts_hashes.keys())
    if missing_parts:
        raise ValueError(f"parts_hashes missing required parts: {missing_parts}")

    for part_name, phash in parts_hashes.items():
        if not isinstance(phash, str) or len(phash) != 64:
            raise ValueError(f"part {part_name} has invalid sha256 hash")

    return LocalDisplayManifest(
        contract_version=manifest_dict["contract_version"],
        code_sha=code_sha,
        config_hash=manifest_dict["config_hash"],
        sequence=sequence,
        generated_at=generated_at_str,
        expires_at=expires_at_str,
        actionable=False,
        data_origin=manifest_dict.get("data_origin", "local_research"),
        universe=universe,
        parts_hashes=parts_hashes,
    )


def compute_parts_hashes(parts: dict[str, Any]) -> dict[str, str]:
    return {k: digest(v) for k, v in parts.items()}


def verify_bundle_integrity(bundle: dict[str, Any], *, now: datetime | None = None) -> bool:
    if not isinstance(bundle, dict):
        return False
    manifest_dict = bundle.get("manifest")
    parts = bundle.get("parts")
    if not isinstance(manifest_dict, dict) or not isinstance(parts, dict):
        return False

    try:
        manifest = validate_bundle_manifest(manifest_dict)
    except Exception:
        return False

    # Check expiration only when now is explicitly provided
    if now is not None:
        try:
            exp_dt = _parse_iso(manifest.expires_at)
            if exp_dt <= now:
                return False
        except Exception:
            return False

    # Check required parts existence
    missing_parts = REQUIRED_PARTS - set(parts.keys())
    if missing_parts:
        return False

    # Check parts hashes match manifest
    computed_hashes = compute_parts_hashes(parts)
    if set(computed_hashes.keys()) != set(manifest.parts_hashes.keys()):
        return False
    for part_name, expected_hash in manifest.parts_hashes.items():
        if computed_hashes.get(part_name) != expected_hash:
            return False

    # Validate privacy boundary and actionable flag across parts: reject actionable=True
    ov = parts.get("overview", {})
    if isinstance(ov, dict):
        if ov.get("actionable") is True:
            return False
        for row in ov.get("rows", []):
            if isinstance(row, dict):
                if row.get("actionable") is True:
                    return False
                if any(field in row for field in FORBIDDEN_PRIVATE_FIELDS):
                    return False

    details = parts.get("details", {})
    if isinstance(details, dict):
        for code, det in details.items():
            if isinstance(det, dict):
                if det.get("actionable") is True:
                    return False
                if any(field in det for field in FORBIDDEN_PRIVATE_FIELDS):
                    return False

    charts = parts.get("charts", {})
    if isinstance(charts, dict):
        for code, ch in charts.items():
            if isinstance(ch, dict):
                if ch.get("actionable") is True:
                    return False
                if any(field in ch for field in FORBIDDEN_PRIVATE_FIELDS):
                    return False

    return True

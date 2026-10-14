"""Contracts and integrity checks for local-display-v2 bundles."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.workspace.shadow_bundle import digest
from app.workspace.shadow_projection import CODE_RE, validate_public_chart

CONTRACT_VERSION = "local-display-v2"
VALIDATION_VERSION = "local-display-validation-v2.1"
MAX_BUNDLE_BYTES = 64 * 1024 * 1024  # 64 MiB bounded quota
REQUIRED_PARTS = {"overview", "details", "charts", "sectors"}
FORBIDDEN_PRIVATE_FIELDS = {"avg_cost", "holdings", "cost", "trades", "account_id", "user_id", "accounts", "cookie", "cookies", "token", "password", "authorization"}
HEX_HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


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


def _scan_deep_privacy_and_actionable(obj: Any) -> bool:
    """Recursively verify no forbidden fields exist and actionable is never truthy/non-False."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in FORBIDDEN_PRIVATE_FIELDS:
                return False
            if k == "actionable" and v is not False:
                return False
            if not _scan_deep_privacy_and_actionable(v):
                return False
    elif isinstance(obj, (list, tuple, set)):
        for item in obj:
            if not _scan_deep_privacy_and_actionable(item):
                return False
    return True


def validate_bundle_manifest(manifest_dict: dict[str, Any]) -> LocalDisplayManifest:
    if not isinstance(manifest_dict, dict):
        raise ValueError("manifest must be a dictionary")
    if manifest_dict.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(f"contract_version must be {CONTRACT_VERSION}")
    if manifest_dict.get("actionable") is not False:
        raise ValueError("actionable must be false in local display contract")
    code_sha = manifest_dict.get("code_sha")
    if not isinstance(code_sha, str) or not SHA_RE.fullmatch(code_sha) or set(code_sha) == {"0"}:
        raise ValueError("valid non-zero code_sha is required")
    config_hash = manifest_dict.get("config_hash")
    if not isinstance(config_hash, str) or not HEX_HASH_RE.fullmatch(config_hash):
        raise ValueError("valid 64-char hex config_hash is required")
    sequence = manifest_dict.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
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
    if not all(isinstance(s, str) and CODE_RE.fullmatch(s) for s in universe) or len(set(universe)) != len(universe):
        raise ValueError("all universe items must be non-empty strings")

    parts_hashes = manifest_dict.get("parts_hashes")
    if not isinstance(parts_hashes, dict) or not parts_hashes:
        raise ValueError("parts_hashes must be a non-empty dictionary")
    
    missing_parts = REQUIRED_PARTS - set(parts_hashes.keys())
    if missing_parts:
        raise ValueError(f"parts_hashes missing required parts: {missing_parts}")

    for part_name, phash in parts_hashes.items():
        if not isinstance(phash, str) or not HEX_HASH_RE.fullmatch(phash):
            raise ValueError(f"part {part_name} has invalid sha256 hash")

    return LocalDisplayManifest(
        contract_version=manifest_dict["contract_version"],
        code_sha=code_sha,
        config_hash=config_hash,
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
    """Validate v2.1 content rules; historical/short-source-SHA policies are unchanged."""
    try:
        if not isinstance(bundle, dict):
            return False
        manifest_dict = bundle.get("manifest")
        parts = bundle.get("parts")
        if not isinstance(manifest_dict, dict) or not isinstance(parts, dict):
            return False
        manifest = validate_bundle_manifest(manifest_dict)
        if now is not None and _parse_iso(manifest.expires_at) <= now:
            return False
        if REQUIRED_PARTS - set(parts) or any(not isinstance(parts[key], dict) for key in REQUIRED_PARTS):
            return False
        if compute_parts_hashes(parts) != manifest.parts_hashes:
            return False
        if not _scan_deep_privacy_and_actionable(bundle):
            return False
        generated = _parse_iso(manifest.generated_at)
        universe = set(manifest.universe)
        for code, chart in parts["charts"].items():
            if code not in universe:
                return False
            validate_public_chart(chart, code=code, generated_at=generated, partial=True)
        for code, detail in parts["details"].items():
            if code not in universe or not isinstance(detail, dict):
                return False
            instrument = detail.get("instrument")
            if instrument is not None:
                if not isinstance(instrument, dict) or ("ts_code" in instrument and instrument["ts_code"] != code):
                    return False
        return True
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False

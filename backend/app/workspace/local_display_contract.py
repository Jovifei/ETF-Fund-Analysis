"""Contracts and integrity checks for local-display-v2 bundles."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.workspace.shadow_bundle import digest

CONTRACT_VERSION = "local-display-v2"
MAX_BUNDLE_BYTES = 64 * 1024 * 1024  # 64 MiB bounded quota


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


def validate_bundle_manifest(manifest_dict: dict[str, Any]) -> LocalDisplayManifest:
    if manifest_dict.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(f"contract_version must be {CONTRACT_VERSION}")
    if manifest_dict.get("actionable") is not False:
        raise ValueError("actionable must be false in local display contract")
    if not manifest_dict.get("code_sha"):
        raise ValueError("code_sha is required")
    if not manifest_dict.get("config_hash"):
        raise ValueError("config_hash is required")
    if not isinstance(manifest_dict.get("sequence"), int):
        raise ValueError("sequence integer is required")
    if not manifest_dict.get("generated_at"):
        raise ValueError("generated_at is required")
    if not manifest_dict.get("expires_at"):
        raise ValueError("expires_at is required")
    if not isinstance(manifest_dict.get("universe"), list):
        raise ValueError("universe list is required")

    return LocalDisplayManifest(
        contract_version=manifest_dict["contract_version"],
        code_sha=manifest_dict["code_sha"],
        config_hash=manifest_dict["config_hash"],
        sequence=manifest_dict["sequence"],
        generated_at=manifest_dict["generated_at"],
        expires_at=manifest_dict["expires_at"],
        actionable=False,
        data_origin=manifest_dict.get("data_origin", "local_research"),
        universe=manifest_dict["universe"],
        parts_hashes=manifest_dict.get("parts_hashes", {}),
    )


def compute_parts_hashes(parts: dict[str, Any]) -> dict[str, str]:
    return {k: digest(v) for k, v in parts.items()}


def verify_bundle_integrity(bundle: dict[str, Any]) -> bool:
    manifest_dict = bundle.get("manifest", {})
    parts = bundle.get("parts", {})
    try:
        manifest = validate_bundle_manifest(manifest_dict)
    except Exception:
        return False

    computed_hashes = compute_parts_hashes(parts)
    for part_name, expected_hash in manifest.parts_hashes.items():
        if computed_hashes.get(part_name) != expected_hash:
            return False
    return True

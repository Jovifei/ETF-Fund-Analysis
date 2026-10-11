import pytest
from app.workspace.local_display_contract import (
    CONTRACT_VERSION,
    LocalDisplayManifest,
    validate_bundle_manifest,
    compute_parts_hashes,
    verify_bundle_integrity,
)


def test_contract_manifest_validation():
    manifest_dict = {
        "contract_version": CONTRACT_VERSION,
        "code_sha": "a" * 40,
        "config_hash": "c" * 64,
        "sequence": 1,
        "generated_at": "2026-10-12T06:30:00Z",
        "expires_at": "2026-10-12T08:30:00Z",
        "actionable": False,
        "data_origin": "local_research",
        "universe": ["510300.SH", "512480.SH"],
        "parts_hashes": {
            "overview": "1" * 64,
            "details": "2" * 64,
            "charts": "3" * 64,
            "sectors": "4" * 64,
        },
    }
    manifest = validate_bundle_manifest(manifest_dict)
    assert manifest.contract_version == CONTRACT_VERSION
    assert manifest.actionable is False


def test_contract_rejects_actionable_true():
    manifest_dict = {
        "contract_version": CONTRACT_VERSION,
        "code_sha": "a" * 40,
        "config_hash": "c" * 64,
        "sequence": 1,
        "generated_at": "2026-10-12T06:30:00Z",
        "expires_at": "2026-10-12T08:30:00Z",
        "actionable": True,  # Boundary violation
        "data_origin": "local_research",
        "universe": ["510300.SH"],
        "parts_hashes": {},
    }
    with pytest.raises(ValueError, match="actionable must be false"):
        validate_bundle_manifest(manifest_dict)


def test_verify_bundle_integrity():
    parts = {
        "overview": {"rows": [{"ts_code": "510300.SH", "price": 4.12}]},
        "details": {"510300.SH": {"quote": {"price": 4.12}}},
        "charts": {"510300.SH": {"bars": []}},
        "sectors": {"sectors": []},
    }
    hashes = compute_parts_hashes(parts)
    bundle = {
        "manifest": {
            "contract_version": CONTRACT_VERSION,
            "code_sha": "a" * 40,
            "config_hash": "c" * 64,
            "sequence": 1,
            "generated_at": "2026-10-12T06:30:00Z",
            "expires_at": "2026-10-12T08:30:00Z",
            "actionable": False,
            "data_origin": "local_research",
            "universe": ["510300.SH"],
            "parts_hashes": hashes,
        },
        "parts": parts,
    }
    assert verify_bundle_integrity(bundle) is True

    # Tampered part
    tampered_bundle = {
        **bundle,
        "parts": {**parts, "overview": {"rows": [{"ts_code": "510300.SH", "price": 9.99}]}},
    }
    assert verify_bundle_integrity(tampered_bundle) is False

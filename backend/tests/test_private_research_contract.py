import pytest

from app.workspace.local_display_contract import compute_parts_hashes, verify_bundle_integrity


def bundle():
    parts = {"overview": {"rows": []}, "details": {}, "charts": {}, "sectors": {}}
    return {"manifest": {"contract_version": "local-display-v2", "code_sha": "a" * 40,
                         "config_hash": "b" * 64, "sequence": 1,
                         "generated_at": "2026-10-15T01:00:00Z", "expires_at": "2026-10-15T03:00:00Z",
                         "universe": ["510300.SH"], "parts_hashes": compute_parts_hashes(parts),
                         "usage_scope": "owner_private_research", "source_qualification": "UNKNOWN",
                         "license_status": "UNKNOWN", "calibration_status": "not_calibrated",
                         "research_only": True, "actionable": False}, "parts": parts}


@pytest.mark.parametrize("key,value", [("source_qualification", "VERIFIED"), ("license_status", "VERIFIED"),
                                      ("calibration_status", "calibrated"), ("research_only", False)])
def test_private_execution_is_never_source_or_prediction_qualification(key, value):
    value_bundle = bundle()
    value_bundle["manifest"][key] = value
    assert not verify_bundle_integrity(value_bundle)


def test_nested_forecast_cannot_claim_calibrated_in_private_scope():
    value = bundle()
    value["parts"]["details"]["510300.SH"] = {"forecasts": {"1": {"calibration_status": "calibrated"}}}
    value["manifest"]["parts_hashes"] = compute_parts_hashes(value["parts"])
    assert not verify_bundle_integrity(value)


def test_private_unknown_metadata_is_valid_without_granting_rights():
    assert verify_bundle_integrity(bundle())

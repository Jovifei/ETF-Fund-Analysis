from app.workspace.detail_availability import build_detail_availability


def test_sr_requires_explicit_overlay_permission_and_does_not_mutate_input():
    existing = {
        "forecasts": {"status": "blocked", "reason_code": "forecast_snapshot_after_read_time"},
        "volume": {"status": "blocked", "reason_code": "feature_shortage"},
    }
    original = dict(existing)

    allowed = build_detail_availability(
        existing,
        support_resistance={"levels": [1]},
        chart={"sr_overlay_allowed": True},
    )
    blocked = build_detail_availability(
        existing,
        support_resistance={"levels": [1]},
        chart={"sr_overlay_allowed": False, "raw_overlay_reason": "price_basis_mismatch"},
    )
    missing = build_detail_availability(existing, support_resistance=None, chart={})

    assert existing == original
    assert allowed["modules"]["support_resistance"]["status"] == "available"
    assert blocked["modules"]["support_resistance"]["reason_code"] == "price_basis_mismatch"
    assert missing["modules"]["support_resistance"]["reason_code"] == "support_resistance_not_generated"
    assert allowed["modules"]["forecasts"]["reason_code"] == "forecast_snapshot_after_read_time"
    assert allowed["modules"]["volume"]["reason_code"] == "feature_shortage"

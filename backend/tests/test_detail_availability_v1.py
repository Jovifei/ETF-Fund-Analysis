from app.workspace.detail_availability import build_detail_availability


def test_detail_availability_keeps_existing_modules_and_adds_sr():
    result = build_detail_availability(
        {
            "instrument": {"status": "active", "reason_code": None},
            "forecasts": {"status": "unavailable", "reason_code": "forecast_not_generated"},
            "volume": {"status": "unavailable", "reason_code": "volume_missing_or_unverified"},
        },
        support_resistance={"levels": []},
    )

    assert result["contract_version"] == "detail-availability-v1"
    assert result["actionable"] is False
    assert result["modules"]["instrument"]["status"] == "active"
    assert result["modules"]["forecasts"]["reason_code"] == "forecast_not_generated"
    assert result["modules"]["volume"]["reason_code"] == "volume_missing_or_unverified"
    assert set(result["modules"]) == {
        "instrument", "price", "history", "price_basis", "indicators",
        "volume", "forecasts", "decision", "support_resistance",
    }


def test_support_resistance_overlay_block_is_not_snapshot_missing():
    blocked = build_detail_availability(
        {},
        support_resistance={"levels": [{"price": 1}]},
        chart={"sr_overlay_allowed": False, "raw_overlay_reason": "price_basis_mismatch"},
    )
    missing = build_detail_availability({}, support_resistance=None)

    assert blocked["modules"]["support_resistance"] == {
        "status": "blocked",
        "reason_code": "price_basis_mismatch",
    }
    assert missing["modules"]["support_resistance"]["reason_code"] == "support_resistance_not_generated"


def test_feature_shortage_is_not_translated_to_measurement_missing():
    result = build_detail_availability({"volume": {"status": "blocked", "reason_code": "feature_shortage"}})
    assert result["modules"]["volume"]["reason_code"] == "feature_shortage"

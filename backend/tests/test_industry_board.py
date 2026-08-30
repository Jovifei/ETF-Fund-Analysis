from __future__ import annotations

import json
from pathlib import Path

from app.services.industry_board_service import IndustryBoardService


def test_industry_registry_contains_exact_31_unique_level1_industries():
    payload = json.loads(Path("config/industry_board.json").read_text(encoding="utf-8"))
    IndustryBoardService._validate(payload)
    assert payload["classification"]["expected_count"] == 31
    assert len(payload["industries"]) == 31
    assert len({item["industry_id"] for item in payload["industries"]}) == 31
    assert len({item["name"] for item in payload["industries"]}) == 31


def test_market_anchors_and_proxy_boundaries_are_explicit():
    payload = json.loads(Path("config/industry_board.json").read_text(encoding="utf-8"))
    anchors = {item["id"]: item for item in payload["market_anchors"]}
    assert set(anchors) == {"china_core", "sp500", "nasdaq", "gold"}
    assert anchors["sp500"]["proxy_ts_code"] == "513500.SH"
    assert anchors["nasdaq"]["kind"] == "qdii_etf_proxy"
    assert "不等同" in anchors["nasdaq"]["note"]
    assert anchors["gold"]["proxy_ts_code"] == "518880.SH"


def test_unmapped_industries_do_not_claim_a_fund():
    payload = json.loads(Path("config/industry_board.json").read_text(encoding="utf-8"))
    unmapped = [
        item
        for item in payload["industries"]
        if item["coverage_status"] == "unmapped_pending_qualification"
    ]
    assert unmapped
    assert all(item["proxy_ts_code"] is None for item in unmapped)

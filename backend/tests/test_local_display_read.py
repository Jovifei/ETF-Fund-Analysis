import json
import pytest
from app.workspace.local_display_read import LocalDisplayStore, LocalDisplayReader
from app.workspace.local_display_contract import CONTRACT_VERSION, compute_parts_hashes


def test_local_display_reader_overview_and_detail(tmp_path):
    store_dir = tmp_path / "store"
    store = LocalDisplayStore(store_dir)

    parts = {
        "overview": {
            "rows": [
                {"ts_code": "510300.SH", "name": "300ETF", "price": 4.12, "theme_l1": "宽基", "actionable": False},
                {"ts_code": "512480.SH", "name": "半导体", "price": 0.88, "theme_l1": "科技", "actionable": False},
            ],
            "total": 2,
            "snapshot_id": "snap-1",
            "generated_at": "2026-10-12T06:30:00Z",
            "sector_timing": {"summary": "偏强观察"},
        },
        "details": {
            "510300.SH": {
                "instrument": {"ts_code": "510300.SH", "name": "300ETF"},
                "quote": {"price": 4.12},
                "indicators": {"ma": {"ma5": 4.10}},
                "forecasts": {1: {"horizon": 1, "value": 4.15}},
                "availability": {"daily_bars": True},
            }
        },
        "charts": {
            "510300.SH": {
                "bars": [{"date": "2026-10-12", "open": 4.10, "close": 4.12}],
                "studies": {},
            }
        },
        "sectors": {"sectors": [{"sector_name": "半导体", "pct_change": 2.1}]},
        "market_context": {"items": [{"context_id": "cn-csi300", "today_pct_change": 1.25, "actionable": False}]},
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
            "universe": ["510300.SH", "512480.SH"],
            "parts_hashes": hashes,
        },
        "parts": parts,
    }

    # Publish bundle to store
    receipt = store.publish(bundle)
    assert receipt["status"] == "accepted"

    reader = LocalDisplayReader(store)
    # Read overview
    ov = reader.read_overview()
    assert len(ov["rows"]) == 2
    assert ov["snapshot_id"] == "snap-1"

    # Filter by theme
    ov_tech = reader.read_overview(theme="科技")
    assert len(ov_tech["rows"]) == 1
    assert ov_tech["rows"][0]["ts_code"] == "512480.SH"

    # Read detail
    det = reader.read_instrument_detail("510300.SH")
    assert det is not None
    assert det["instrument"]["name"] == "300ETF"

    # Non-existent detail
    assert reader.read_instrument_detail("999999.SH") is None

    # Read chart
    chart = reader.read_chart_data("510300.SH", interval="1d")
    assert chart is not None
    assert len(chart["bars"]) == 1

    # Read market context
    mc = reader.read_market_context()
    assert mc is not None
    assert len(mc) == 1
    assert mc[0]["context_id"] == "cn-csi300"

    # Unsupported interval
    with pytest.raises(ValueError, match="unsupported_chart_interval"):
        reader.read_chart_data("510300.SH", interval="5m")


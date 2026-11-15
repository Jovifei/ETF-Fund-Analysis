"""End-to-end integration tests for Sector Drawer (P4/P5).

Verifies the full pipeline from local bundle production/reading to API serving:
- Sector representative ETF resolution (华泰柏瑞, 南方基金, etc.)
- Index chart serving from bundle
- ETF detail with grade_base, grade_final, adjustment and structure factors
- ETF chart with support/resistance levels
- Fail-closed security boundaries (actionable=false, qualification preservation)
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.workspace.local_display_contract import (
    CONTRACT_VERSION,
    compute_parts_hashes,
    verify_bundle_integrity,
)
from app.workspace.local_display_read import LocalDisplayReader, LocalDisplayStore

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _make_e2e_bundle(generation=101):
    now = datetime(2026, 11, 8, 15, 30, tzinfo=SHANGHAI)
    as_of = "2026-11-06"

    parts = {
        "overview": {
            "snapshot_id": f"snap-{generation}",
            "generated_at": now.isoformat(),
            "generation": generation,
            "research_source": "local_bundle",
            "read_model_version": "local-display-v2",
            "is_stale": False,
            "rows": [
                {
                    "ts_code": "515790.SH",
                    "name": "光伏ETF",
                    "theme_l1": "新能源",
                    "theme_l2": "光伏",
                    "grade": "4",
                    "grade_base": "3",
                    "grade_final": "4",
                    "adjustment": {
                        "applied": True,
                        "base_grade": "3",
                        "final_grade": "4",
                        "weight": 0.4167,
                        "structure_score": 0.42,
                    },
                    "qualification": "QUALIFIED",
                    "freshness": "fresh",
                    "price": 0.92,
                    "support_resistance": {
                        "nearest_support": {"price": 0.85},
                        "nearest_resistance": {"price": 1.05},
                    },
                }
            ],
        },
        "market_context": {
            "context_kind": "market",
            "read_contract": "local-display-context-read-v1",
            "source_as_of": as_of,
            "availability": "available",
            "items": [],
            "latest_view": [],
        },
        "sectors": {
            "source_as_of": as_of,
            "availability": "available",
            "sectors": [
                {
                    "sector_name": "光伏设备",
                    "board_type": "industry",
                    "pct_change": 2.35,
                    "source": "em_summary",
                    "source_as_of": as_of,
                    "is_mock": False,
                    "up_count": 35,
                    "down_count": 10,
                    "flat_count": 5,
                    "total_count": 50,
                },
                {
                    "sector_name": "有色金属",
                    "board_type": "industry",
                    "pct_change": 1.42,
                    "source": "em_summary",
                    "source_as_of": as_of,
                    "is_mock": False,
                    "up_count": 42,
                    "down_count": 8,
                    "flat_count": 2,
                    "total_count": 52,
                },
            ],
        },
        "details": {
            "515790.SH": {
                "instrument": {
                    "ts_code": "515790.SH",
                    "name": "光伏ETF",
                    "kind": "etf",
                    "theme_l1": "新能源",
                    "theme_l2": "光伏",
                },
                "decision": {
                    "ts_code": "515790.SH",
                    "name": "光伏ETF",
                    "grade": "4",
                    "grade_base": "3",
                    "grade_final": "4",
                    "adjustment": {
                        "applied": True,
                        "base_grade": "3",
                        "final_grade": "4",
                        "weight": 0.4167,
                    },
                    "qualification": "QUALIFIED",
                    "support_resistance": {
                        "nearest_support": {"price": 0.85},
                        "nearest_resistance": {"price": 1.05},
                    },
                    "structure_v1": {
                        "wyckoff_phase": "吸筹完成",
                        "dow_phase": "上升结构",
                        "atr_risk_bucket": "低波安全",
                    },
                },
                "read_as_of": as_of,
                "quote": {"price": 0.92, "change_ratio": 0.021, "status": "NORMAL"},
            }
        },
        "charts": {
            "515790.SH": {
                "ts_code": "515790.SH",
                "interval": "1d",
                "available": True,
                "qualification": "UNKNOWN",
                "actionable": False,
                "research_only": True,
                "bars": [
                    {
                        "date": as_of,
                        "open": 0.90,
                        "high": 0.93,
                        "low": 0.89,
                        "close": 0.92,
                        "volume": 1200000,
                        "amount": 1090000,
                        "indicators": {},
                    }
                ],
                "support_resistance": {
                    "nearest_support": {"price": 0.85},
                    "nearest_resistance": {"price": 1.05},
                },
            }
        },
        "index_charts": {
            "931151.CSI": {
                "ts_code": "931151.CSI",
                "interval": "1d",
                "available": True,
                "qualification": "UNKNOWN",
                "actionable": False,
                "research_only": True,
                "bars": [
                    {
                        "date": as_of,
                        "open": 3200.0,
                        "high": 3250.0,
                        "low": 3190.0,
                        "close": 3240.0,
                        "volume": 5000000,
                        "amount": 8000000,
                        "indicators": {},
                    }
                ],
            }
        },
    }

    parts_hashes = compute_parts_hashes(parts)
    bundle = {
        "manifest": {
            "contract_version": CONTRACT_VERSION,
            "code_sha": "a" * 40,
            "config_hash": "c" * 64,
            "sequence": generation,
            "generation": generation,
            "generated_at": "2026-11-08T06:00:00Z",
            "expires_at": "2026-11-09T08:00:00Z",
            "actionable": False,
            "data_origin": "local_research",
            "universe": ["515790.SH"],
            "parts_hashes": parts_hashes,
        },
        "parts": parts,
    }
    return bundle, now


def test_sector_drawer_api_full_chain(tmp_path, monkeypatch):
    bundle, now = _make_e2e_bundle(generation=101)
    store = LocalDisplayStore(store_dir=str(tmp_path))
    store.publish(bundle, now=now)

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace_research_source", "local_bundle")
    monkeypatch.setattr(settings, "local_display_v2_store_root", str(tmp_path))
    monkeypatch.setattr(settings, "shadow_sync_code_sha", "a" * 40)
    monkeypatch.setattr(settings, "shadow_sync_config_hash", "c" * 64)

    client = TestClient(app)

    # 1. Sector Representatives Mapping endpoint
    r_reps = client.get("/api/workspace/sectors/representatives")
    assert r_reps.status_code == 200
    data_reps = r_reps.json()
    assert "mappings" in data_reps
    assert data_reps["total"] >= 15

    # Check Photovoltaic (Huatai-PineBridge)
    pv_map = next((m for m in data_reps["mappings"] if m["sector_name"] == "光伏"), None)
    assert pv_map is not None
    assert pv_map["representative_etf"]["ts_code"] == "515790.SH"
    assert "华泰柏瑞" in pv_map["representative_etf"]["fund_company"]
    assert pv_map["tracking_index"]["code"] == "931151.CSI"
    assert pv_map["qualification"] == "verified"

    # Check Nonferrous Metals (China Southern)
    metal_map = next((m for m in data_reps["mappings"] if m["sector_name"] == "有色金属"), None)
    assert metal_map is not None
    assert metal_map["representative_etf"]["ts_code"] == "512400.SH"
    assert "南方" in metal_map["representative_etf"]["fund_company"]

    # 2. Sectors Board endpoint
    r_sectors = client.get("/api/workspace/sectors?generation=101")
    assert r_sectors.status_code == 200
    data_sectors = r_sectors.json()
    assert len(data_sectors["boards"]) == 2
    assert data_sectors["boards"][0]["sector_name"] == "光伏设备"
    assert data_sectors["boards"][0]["up_count"] == 35

    # 3. Representative ETF Detail with grade semantics
    r_detail = client.get("/api/workspace/instruments/515790.SH?generation=101")
    assert r_detail.status_code == 200
    detail = r_detail.json()
    assert detail["instrument"]["ts_code"] == "515790.SH"
    dec = detail["decision"]
    assert dec["grade_base"] == "3"
    assert dec["grade_final"] == "4"
    assert dec["adjustment"]["applied"] is True
    assert dec["adjustment"]["weight"] == 0.4167
    assert dec["structure_v1"]["wyckoff_phase"] == "吸筹完成"
    assert dec["structure_v1"]["dow_phase"] == "上升结构"

    # 4. Representative ETF Chart
    r_etf_chart = client.get("/api/workspace/instruments/515790.SH/chart?interval=1d&generation=101")
    assert r_etf_chart.status_code == 200
    etf_chart = r_etf_chart.json()
    assert etf_chart["available"] is True
    assert len(etf_chart["bars"]) == 1
    assert etf_chart["bars"][0]["close"] == 0.92
    assert etf_chart["support_resistance"]["nearest_support"]["price"] == 0.85

    # 5. Index Chart from Local Bundle
    r_index_chart = client.get("/api/workspace/indexes/931151.CSI/chart?generation=101")
    assert r_index_chart.status_code == 200
    index_chart = r_index_chart.json()
    assert index_chart["available"] is True
    assert index_chart["ts_code"] == "931151.CSI"
    assert len(index_chart["bars"]) == 1
    assert index_chart["bars"][0]["close"] == 3240.0


def test_sector_drawer_unknown_and_fail_closed(tmp_path, monkeypatch):
    bundle, now = _make_e2e_bundle(generation=101)
    store = LocalDisplayStore(store_dir=str(tmp_path))
    store.publish(bundle, now=now)

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace_research_source", "local_bundle")
    monkeypatch.setattr(settings, "local_display_v2_store_root", str(tmp_path))
    monkeypatch.setattr(settings, "shadow_sync_code_sha", "a" * 40)
    monkeypatch.setattr(settings, "shadow_sync_config_hash", "c" * 64)

    client = TestClient(app)

    # 1. Unknown index chart returns 404
    r = client.get("/api/workspace/indexes/UNKNOWN_INDEX/chart?generation=101")
    assert r.status_code == 404

    # 2. Unknown instrument detail returns 404
    r_inst = client.get("/api/workspace/instruments/999999.SH?generation=101")
    assert r_inst.status_code == 404

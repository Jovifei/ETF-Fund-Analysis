"""Tests for P2 (Representative ETF mappings & grade semantics) and P3 (local_bundle index/minute charts)."""
from datetime import datetime, timezone
import pytest
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.services.sector_representative_service import SectorRepresentativeService, load_representative_etf_config
from app.workspace.local_display_contract import (
    CONTRACT_VERSION,
    OPTIONAL_PARTS,
    compute_parts_hashes,
    verify_bundle_integrity,
)
from app.workspace.local_display_read import LocalDisplayReader, LocalDisplayStore
from app.workspace.shadow_projection import validate_public_chart

SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_representative_etf_config_and_service():
    service = SectorRepresentativeService()
    mappings = service.list_mappings(as_of="2026-11-08")
    assert len(mappings) >= 15

    # 1. Huatai-PineBridge (华泰柏瑞) coverage
    hs300 = service.resolve_representative(sector_name="沪深300", as_of="2026-11-08")
    assert hs300 is not None
    assert hs300["representative_etf"]["ts_code"] == "510300.SH"
    assert "华泰柏瑞" in hs300["representative_etf"]["fund_company"]
    assert hs300["mapping_type"] == "primary_tracker"
    assert hs300["qualification"] == "verified"
    assert len(hs300["basis"]) > 5

    pv = service.resolve_representative(sector_name="光伏", as_of="2026-11-08")
    assert pv is not None
    assert pv["representative_etf"]["ts_code"] == "515790.SH"
    assert "华泰柏瑞" in pv["representative_etf"]["fund_company"]

    # 2. China Southern (南方基金) coverage
    metal = service.resolve_representative(sector_name="有色金属", as_of="2026-11-08")
    assert metal is not None
    assert metal["representative_etf"]["ts_code"] == "512400.SH"
    assert "南方" in metal["representative_etf"]["fund_company"]

    oil = service.resolve_representative(sector_name="原油", as_of="2026-11-08")
    assert oil is not None
    assert oil["representative_etf"]["ts_code"] == "159980.SZ"
    assert "南方" in oil["representative_etf"]["fund_company"]

    estate = service.resolve_representative(sector_name="房地产", as_of="2026-11-08")
    assert estate is not None
    assert estate["representative_etf"]["ts_code"] == "512200.SH"
    assert "南方" in estate["representative_etf"]["fund_company"]

    # 3. Validity range enforcement
    past_mapping = service.resolve_representative(sector_name="光伏", as_of="2020-01-01")
    assert past_mapping is None, "Should not return mapping before effective_from"

    future_mapping = service.resolve_representative(sector_name="光伏", as_of="2035-01-01")
    assert future_mapping is None, "Should not return mapping after effective_to"


def test_row_fields_v2_preserves_grade_semantics():
    from app.workspace.local_compute import ROW_FIELDS_V2, _display_row

    required_keys = {"grade_base", "grade_final", "adjustment", "qualification"}
    for k in required_keys:
        assert k in ROW_FIELDS_V2, f"{k} must be in ROW_FIELDS_V2 to prevent stripping"

    sample_row = {
        "ts_code": "510300.SH",
        "name": "300ETF",
        "grade": "可加仓",
        "grade_base": "可入场",
        "grade_final": "可加仓",
        "adjustment": {
            "applied": True,
            "shift": 1,
            "weight": 0.4167,
            "base_grade": "可入场",
            "final_grade": "可加仓",
            "reason": "structure_decision",
            "rule_version": "structure_decision_v1",
        },
        "qualification": "verified",
        "price": 4.12,
        "actionable": True,  # should be forced False by _display_row
    }
    projected = _display_row(sample_row)
    assert projected["grade_base"] == "可入场"
    assert projected["grade_final"] == "可加仓"
    assert projected["adjustment"]["applied"] is True
    assert projected["qualification"] == "verified"
    assert projected["actionable"] is False
    assert projected["research_only"] is True


def test_local_display_contract_accepts_index_charts_and_minute_periods():
    assert "index_charts" in OPTIONAL_PARTS

    parts = {
        "overview": {"rows": [{"ts_code": "510300.SH", "price": 4.12, "actionable": False}]},
        "details": {"510300.SH": {"instrument": {"ts_code": "510300.SH"}}},
        "charts": {"510300.SH": {"interval": "1d", "bars": []}},
        "sectors": {"sectors": []},
        "index_charts": {
            "000300.SH": {
                "ts_code": "000300.SH",
                "interval": "1d",
                "bars": [{"date": "2026-11-06", "open": 3900.0, "high": 3950.0, "low": 3890.0, "close": 3920.0}],
                "actionable": False,
                "research_only": True,
            }
        },
        "chart_periods": {
            "510300.SH": {
                "30m": {
                    "ts_code": "510300.SH",
                    "interval": "30m",
                    "bars": [{"date": "2026-11-08T10:00:00+08:00", "open": 4.10, "high": 4.15, "low": 4.09, "close": 4.12}],
                    "actionable": False,
                    "research_only": True,
                }
            }
        },
    }
    hashes = compute_parts_hashes(parts)
    bundle = {
        "manifest": {
            "contract_version": CONTRACT_VERSION,
            "code_sha": "a" * 40,
            "config_hash": "c" * 64,
            "sequence": 1,
            "generated_at": "2026-11-08T06:00:00Z",
            "expires_at": "2026-11-08T08:00:00Z",
            "actionable": False,
            "data_origin": "local_research",
            "universe": ["510300.SH"],
            "parts_hashes": hashes,
        },
        "parts": parts,
    }
    assert verify_bundle_integrity(bundle) is True


def test_local_display_reader_reads_index_chart_and_minute_chart(tmp_path):
    store_dir = tmp_path / "store"
    store = LocalDisplayStore(store_dir)
    reader = LocalDisplayReader(store, code_sha="a" * 40, config_hash="c" * 64)

    parts = {
        "overview": {"rows": [{"ts_code": "510300.SH", "price": 4.12, "actionable": False}]},
        "details": {"510300.SH": {"instrument": {"ts_code": "510300.SH"}}},
        "charts": {"510300.SH": {"interval": "1d", "bars": []}},
        "sectors": {"sectors": []},
        "index_charts": {
            "000300.SH": {
                "ts_code": "000300.SH",
                "interval": "1d",
                "bars": [{"date": "2026-11-06", "open": 3900.0, "high": 3950.0, "low": 3890.0, "close": 3920.0}],
                "actionable": False,
                "research_only": True,
            }
        },
        "chart_periods": {
            "510300.SH": {
                "30m": {
                    "ts_code": "510300.SH",
                    "interval": "30m",
                    "bars": [{"date": "2026-11-08T10:00:00+08:00", "open": 4.10, "high": 4.15, "low": 4.09, "close": 4.12}],
                    "actionable": False,
                    "research_only": True,
                }
            }
        },
    }
    bundle = {
        "manifest": {
            "contract_version": CONTRACT_VERSION,
            "code_sha": "a" * 40,
            "config_hash": "c" * 64,
            "sequence": 1,
            "generated_at": "2026-11-08T06:00:00Z",
            "expires_at": "2026-11-08T08:00:00Z",
            "actionable": False,
            "data_origin": "local_research",
            "universe": ["510300.SH"],
            "parts_hashes": compute_parts_hashes(parts),
        },
        "parts": parts,
    }
    now = datetime(2026, 11, 8, 7, tzinfo=timezone.utc)
    store.publish(bundle, now=now)

    # 1. Index chart reading
    idx_chart = reader.read_index_chart("000300.SH")
    assert idx_chart is not None
    assert idx_chart["ts_code"] == "000300.SH"
    assert len(idx_chart["bars"]) == 1

    # Alias / context_id lookup (sh000300 -> 000300.SH)
    idx_alias = reader.read_index_chart("sh000300")
    assert idx_alias is not None
    assert idx_alias["ts_code"] == "000300.SH"

    # 2. Minute chart reading via read_chart_data
    m30_chart = reader.read_chart_data("510300.SH", interval="30m")
    assert m30_chart is not None
    assert m30_chart["interval"] == "30m"
    assert len(m30_chart["bars"]) == 1

    # 3. Unavailable interval returns None
    m60_chart = reader.read_chart_data("510300.SH", interval="60m")
    assert m60_chart is None


def test_api_sector_representatives_endpoint():
    client = TestClient(app)
    response = client.get("/api/workspace/sectors/representatives")
    assert response.status_code == 200
    data = response.json()
    assert "mappings" in data
    assert data["total"] >= 15
    assert data["actionable"] is False
    assert data["research_only"] is True

    # Filter by as_of
    resp_filtered = client.get("/api/workspace/sectors/representatives?as_of=2026-11-08")
    assert resp_filtered.status_code == 200
    assert resp_filtered.json()["total"] >= 15


def test_api_index_chart_from_local_bundle(tmp_path, monkeypatch):
    settings = get_settings()
    store_dir = tmp_path / "store"
    store = LocalDisplayStore(store_dir)

    parts = {
        "overview": {"rows": [{"ts_code": "510300.SH", "price": 4.12, "actionable": False}]},
        "details": {"510300.SH": {"instrument": {"ts_code": "510300.SH"}}},
        "charts": {"510300.SH": {"interval": "1d", "bars": []}},
        "sectors": {"sectors": []},
        "index_charts": {
            "000300.SH": {
                "ts_code": "000300.SH",
                "interval": "1d",
                "bars": [{"date": "2026-11-06", "open": 3900.0, "high": 3950.0, "low": 3890.0, "close": 3920.0}],
                "actionable": False,
                "research_only": True,
            }
        },
    }
    test_sha = "a" * 40
    test_cfg = "c" * 64
    bundle = {
        "manifest": {
            "contract_version": CONTRACT_VERSION,
            "code_sha": test_sha,
            "config_hash": test_cfg,
            "sequence": 1,
            "generated_at": "2026-11-08T06:00:00Z",
            "expires_at": "2026-11-08T08:00:00Z",
            "actionable": False,
            "data_origin": "local_research",
            "universe": ["510300.SH"],
            "parts_hashes": compute_parts_hashes(parts),
        },
        "parts": parts,
    }
    now = datetime(2026, 11, 8, 7, tzinfo=timezone.utc)
    store.publish(bundle, now=now)

    monkeypatch.setattr(settings, "workspace_research_source", "local_bundle")
    monkeypatch.setattr(settings, "local_display_v2_store_root", str(store_dir))
    monkeypatch.setattr(settings, "shadow_sync_code_sha", test_sha)
    monkeypatch.setattr(settings, "shadow_sync_config_hash", test_cfg)

    client = TestClient(app)
    # Test index chart lookup by context_id (e.g. sh000300)
    resp = client.get("/api/workspace/indexes/sh000300/chart")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ts_code"] == "000300.SH"
    assert len(data["bars"]) == 1
    assert data["provider_called"] is False

    # Test unknown index returns 404
    resp_unknown = client.get("/api/workspace/indexes/sh999999/chart")
    assert resp_unknown.status_code == 404

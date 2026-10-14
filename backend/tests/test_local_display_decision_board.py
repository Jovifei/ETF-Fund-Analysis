import pytest
from datetime import datetime, timezone, date
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.workspace.local_display_contract import CONTRACT_VERSION, compute_parts_hashes
from app.workspace.local_display_read import LocalDisplayStore, LocalDisplayReader
from app.providers.corporate_action_contract import official_corporate_actions


def test_local_display_reader_decision_board(tmp_path):
    store = LocalDisplayStore(tmp_path)
    reader = LocalDisplayReader(store)

    # Empty store
    assert reader.read_decision_board() is None

    # Publish bundle
    parts = {
        "overview": {
            "snapshot_id": "snap-1013",
            "generated_at": "2026-10-13T16:12:57+08:00",
            "rows": [
                {
                    "ts_code": "510300.SH",
                    "name": "300ETF",
                    "grade": "可入场",
                    "grade_reason": "健康",
                    "price": 4.345,
                    "returns": {"today": 0.012},
                    "quote": {"price": 4.345, "change_ratio": 0.012},
                }
            ],
            "sector_timing": {},
        },
        "details": {
            "510300.SH": {
                "decision": {"grade": "可入场"},
                "quote": {"price": 4.345},
            }
        },
        "charts": {"510300.SH": {"bars": []}},
        "sectors": {"sectors": []},
    }
    from datetime import datetime, timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    bundle = {
        "manifest": {
            "contract_version": CONTRACT_VERSION,
            "code_sha": "a" * 40,
            "config_hash": "c" * 64,
            "sequence": 1791879195447,
            "generated_at": now_utc.isoformat(),
            "expires_at": (now_utc + timedelta(hours=2)).isoformat(),
            "actionable": False,
            "data_origin": "local_research",
            "universe": ["510300.SH"],
            "parts_hashes": compute_parts_hashes(parts),
        },
        "parts": parts,
    }
    store.publish(bundle, now=now_utc)

    # Read decision board
    board = reader.read_decision_board(horizon=1)
    assert board is not None
    assert board["snapshot_id"] == "snap-1013"
    assert board["generated_at"] == "2026-10-13T16:12:57+08:00"
    assert board["target_trade_date"] == "2026-10-13"
    assert board["freshness"] == "fresh"
    assert len(board["rows"]) == 1
    assert board["rows"][0]["grade"] == "可入场"
    assert board["rows"][0]["price"] == 4.345
    assert board["counts"] == {"可入场": 1}


def test_corporate_action_splits_registered():
    for code in ["159995.SZ", "512760.SH", "515050.SH", "516780.SH"]:
        actions = official_corporate_actions(code)
        assert len(actions) >= 1
        assert actions[0].ts_code == code
        assert actions[0].ratio > 0

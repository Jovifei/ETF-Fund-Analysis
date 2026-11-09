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


def _publish_board_bundle(tmp_path, row):
    from datetime import timedelta
    store = LocalDisplayStore(tmp_path)
    parts = {
        "overview": {"snapshot_id": "snap-struct", "generated_at": "2026-11-06T16:12:57+08:00",
                     "rows": [row], "sector_timing": {}},
        "details": {"510300.SH": {"decision": {"grade": row.get("grade")}, "quote": {"price": 4.345}}},
        "charts": {"510300.SH": {"bars": []}},
        "sectors": {"sectors": []},
    }
    now_utc = datetime.now(timezone.utc)
    bundle = {"manifest": {"contract_version": CONTRACT_VERSION, "code_sha": "a" * 40,
                           "config_hash": "c" * 64, "sequence": 1793958321240,
                           "generated_at": now_utc.isoformat(),
                           "expires_at": (now_utc + timedelta(hours=2)).isoformat(),
                           "actionable": False, "data_origin": "local_research",
                           "universe": ["510300.SH"], "parts_hashes": compute_parts_hashes(parts)},
              "parts": parts}
    store.publish(bundle, now=now_utc)
    return LocalDisplayReader(store)


def test_decision_board_rows_carry_structure_v1_and_per_horizon_forecasts(tmp_path):
    """A bundle whose overview rows carry structure_v1 must surface it through
    the reader for every research horizon, with the matching per-horizon
    forecast selected (1/3/7/20/60 chain consistency)."""
    forecasts = {str(h): {"q50": h / 1000.0} for h in (1, 3, 7, 20, 60)}
    row = {"ts_code": "510300.SH", "name": "300ETF", "grade": "观望", "grade_reason": "健康",
           "price": 4.345, "forecasts": forecasts,
           "structure_v1": {"schema_version": "structure_v1", "ts_code": "510300.SH",
                            "as_of": "2026-11-06", "wyckoff_phase": "markup",
                            "dow_phase": "uptrend", "atr14": 0.096, "atr_pct": 0.0221,
                            "atr_risk_bucket": "high", "research_only": True}}
    reader = _publish_board_bundle(tmp_path, row)
    for horizon in (1, 3, 7, 20, 60):
        board = reader.read_decision_board(horizon=horizon)
        assert board is not None and board["selected_horizon"] == horizon
        out = board["rows"][0]
        assert out["structure_v1"]["wyckoff_phase"] == "markup"
        assert out["structure_v1"]["atr_risk_bucket"] == "high"
        assert out["forecast"] == forecasts[str(horizon)]


def test_decision_board_rows_without_structure_v1_stay_absent(tmp_path):
    """Historical bundles without structure_v1 remain readable and the field
    stays absent (the UI renders —), never a fabricated neutral value."""
    row = {"ts_code": "510300.SH", "name": "300ETF", "grade": "观望", "grade_reason": "健康",
           "price": 4.345, "forecasts": {"1": {"q50": 0.001}}}
    reader = _publish_board_bundle(tmp_path, row)
    board = reader.read_decision_board(horizon=1)
    assert board is not None
    assert "structure_v1" not in board["rows"][0]

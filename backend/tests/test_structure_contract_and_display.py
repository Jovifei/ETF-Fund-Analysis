import math
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PKG_PARENT = REPO_ROOT / "research" / "etf_structure_features"
if str(PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(PKG_PARENT))

from app.workspace.local_compute import ROW_FIELDS_V2, _display_row
from app.workspace.read_model import compact_row
from app.workspace.local_display_read import LocalDisplayReader
from app.workspace.local_display_contract import verify_bundle_integrity
from etf_structure_features.atr_risk import wilder_atr14, bucket_from_pct, atr_features, RISK_BUCKET_RULE_VERSION
from etf_structure_features.wyckoff_proxy import wyckoff_from_ohlcv
from etf_structure_features.dow_proxy import confirmed_pivots, dow_phase_from_pivots
from etf_structure_features.pipeline import build_structure_row


def test_row_fields_v2_and_compact_row_contain_structure_fields():
    assert "structure_v1" in ROW_FIELDS_V2
    assert "structure_shadow" in ROW_FIELDS_V2

    sample_row = {
        "ts_code": "510300.SH",
        "name": "300ETF",
        "grade": "观望",
        "structure_v1": {"schema_version": "structure_v1", "wyckoff_phase": "range"},
        "structure_shadow": {"signal": "flat", "score": 0.0},
    }
    projected = _display_row(sample_row)
    assert projected["structure_v1"] == {"schema_version": "structure_v1", "wyckoff_phase": "range"}
    assert projected["structure_shadow"] == {"signal": "flat", "score": 0.0}

    compacted = compact_row(sample_row)
    assert compacted["structure_v1"] == {"schema_version": "structure_v1", "wyckoff_phase": "range"}
    assert compacted["structure_shadow"] == {"signal": "flat", "score": 0.0}


def test_atr_risk_bucket_rule_and_boundaries():
    assert RISK_BUCKET_RULE_VERSION == "atr_pct_fixed_v1"

    # low: < 1.0% (0.010)
    assert bucket_from_pct(0.005) == "low"
    assert bucket_from_pct(0.0099) == "low"

    # mid: [1.0%, 2.0%)
    assert bucket_from_pct(0.010) == "mid"
    assert bucket_from_pct(0.015) == "mid"
    assert bucket_from_pct(0.0199) == "mid"

    # high: [2.0%, 3.5%)
    assert bucket_from_pct(0.020) == "high"
    assert bucket_from_pct(0.028) == "high"
    assert bucket_from_pct(0.0349) == "high"

    # extreme: >= 3.5%
    assert bucket_from_pct(0.035) == "extreme"
    assert bucket_from_pct(0.050) == "extreme"

    # missing, NaN, zero, inf
    assert bucket_from_pct(None) == "unknown"
    assert bucket_from_pct(float("nan")) == "unknown"
    assert bucket_from_pct(float("inf")) == "unknown"


def test_atr_features_zero_price_or_missing_samples():
    # Insufficient bars (< 15 bars)
    highs = [10.0] * 10
    lows = [9.0] * 10
    closes = [9.5] * 10
    atr, pct_val, bucket, ev = atr_features(highs, lows, closes, as_of_index=9)
    assert atr is None
    assert pct_val is None
    assert bucket == "unknown"

    # Zero price: cannot divide by zero, must return unknown
    highs = [10.0] * 20
    lows = [9.0] * 20
    closes = [0.0] * 20
    atr, pct_val, bucket, ev = atr_features(highs, lows, closes, as_of_index=19)
    assert pct_val is None
    assert bucket == "unknown"


def test_wyckoff_proxy_insufficient_samples_and_bounds():
    # < 20 bars
    opens = [10.0] * 10
    highs = [10.5] * 10
    lows = [9.5] * 10
    closes = [10.0] * 10
    volumes = [1000.0] * 10
    phase, score, conf, ev = wyckoff_from_ohlcv(opens, highs, lows, closes, volumes, as_of_index=9)
    assert phase == "unknown"
    assert score == 0.0
    assert conf == 0.0

    # Missing/empty volumes
    phase, score, conf, ev = wyckoff_from_ohlcv(opens, highs, lows, closes, [], as_of_index=9)
    assert phase == "unknown"


def test_dow_proxy_insufficient_pivots_and_prefix_invariance():
    # Linear flat series: no confirmed pivots -> unknown
    highs = [10.0 + i * 0.1 for i in range(30)]
    lows = [9.0 + i * 0.1 for i in range(30)]
    pivots = confirmed_pivots(highs, lows, as_of_index=29)
    phase, score, conf, ev = dow_phase_from_pivots(pivots)
    assert phase == "unknown"
    assert score == 0.0

    # Prefix invariance: adding future bars must NOT change past calculation
    as_of = 20
    pivots_past = confirmed_pivots(highs, lows, as_of_index=as_of)
    future_highs = highs + [999.0, 999.0]
    future_lows = lows + [0.1, 0.1]
    pivots_with_future = confirmed_pivots(future_highs, future_lows, as_of_index=as_of)
    assert pivots_past == pivots_with_future


from datetime import datetime, timedelta, timezone
from app.workspace.local_display_contract import compute_parts_hashes
from app.workspace.local_display_read import LocalDisplayReader, LocalDisplayStore


def test_bundle_backward_compatibility_without_structure(tmp_path):
    # Old bundle without structure_v1 does not crash
    now = datetime.now(timezone.utc)
    parts = {
        "overview": {
            "snapshot_id": "s1",
            "generated_at": now.isoformat(),
            "rows": [{"ts_code": "510300.SH", "name": "300ETF", "grade": "观望"}],
        },
        "details": {
            "510300.SH": {"instrument": {"ts_code": "510300.SH"}, "decision": {"grade": "观望"}},
        },
        "charts": {},
        "sectors": {"items": []},
        "market_context": {"items": [], "availability": "unavailable", "reason": "none"},
    }
    raw_bundle = {
        "manifest": {
            "contract_version": "local-display-v2",
            "code_sha": "a0d52e44ba58f34e0ed335d7bcb6409a3ecd7362",
            "config_hash": "a12c6ea1c812d2cd4b5365c3fa383dbd6c6e4296e004806897d9545008b8e5c8",
            "sequence": 1001,
            "generated_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=2)).isoformat(),
            "actionable": False,
            "universe": ["510300.SH"],
            "parts_hashes": compute_parts_hashes(parts),
        },
        "parts": parts,
    }

    store = LocalDisplayStore(tmp_path)
    store.publish(raw_bundle, now=now)

    reader = LocalDisplayReader(store, code_sha="a0d52e44ba58f34e0ed335d7bcb6409a3ecd7362",
                                config_hash="a12c6ea1c812d2cd4b5365c3fa383dbd6c6e4296e004806897d9545008b8e5c8")
    ov = reader.read_overview(1, 0, 10)
    assert ov["total"] == 1
    row = ov["rows"][0]
    assert row["ts_code"] == "510300.SH"
    assert row.get("structure_v1") is None  # Backward compatibility: None, no crash

    board = reader.read_decision_board(1)
    assert board["snapshot_id"] == "s1"
    assert board["rows"][0].get("structure_v1") is None


def test_bundle_structure_v1_preserved_end_to_end(tmp_path):
    now = datetime.now(timezone.utc)
    structure_sample = {
        "schema_version": "structure_v1",
        "ts_code": "510300.SH",
        "as_of": "2026-11-09",
        "wyckoff_phase": "accumulation",
        "wyckoff_score": 0.45,
        "wyckoff_confidence": 0.65,
        "dow_phase": "uptrend",
        "dow_score": 0.70,
        "dow_confidence": 0.65,
        "atr14": 0.0456,
        "atr_pct": 0.0125,
        "atr_risk_bucket": "mid",
        "evidence": [],
        "research_only": True,
    }
    parts = {
        "overview": {
            "snapshot_id": "s2",
            "generated_at": now.isoformat(),
            "rows": [{
                "ts_code": "510300.SH",
                "name": "300ETF",
                "grade": "观望",
                "structure_v1": structure_sample,
            }],
        },
        "details": {
            "510300.SH": {
                "instrument": {"ts_code": "510300.SH"},
                "decision": {"grade": "观望", "structure_v1": structure_sample},
            },
        },
        "charts": {},
        "sectors": {"items": []},
        "market_context": {"items": [], "availability": "unavailable", "reason": "none"},
    }
    raw_bundle = {
        "manifest": {
            "contract_version": "local-display-v2",
            "code_sha": "a0d52e44ba58f34e0ed335d7bcb6409a3ecd7362",
            "config_hash": "a12c6ea1c812d2cd4b5365c3fa383dbd6c6e4296e004806897d9545008b8e5c8",
            "sequence": 1002,
            "generated_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=2)).isoformat(),
            "actionable": False,
            "universe": ["510300.SH"],
            "parts_hashes": compute_parts_hashes(parts),
        },
        "parts": parts,
    }

    store = LocalDisplayStore(tmp_path)
    store.publish(raw_bundle, now=now)

    reader = LocalDisplayReader(store, code_sha="a0d52e44ba58f34e0ed335d7bcb6409a3ecd7362",
                                config_hash="a12c6ea1c812d2cd4b5365c3fa383dbd6c6e4296e004806897d9545008b8e5c8")
    ov = reader.read_overview(1, 0, 10)
    assert ov["rows"][0]["structure_v1"]["wyckoff_phase"] == "accumulation"
    assert ov["rows"][0]["structure_v1"]["atr_risk_bucket"] == "mid"

    board = reader.read_decision_board(1)
    assert board["rows"][0]["structure_v1"]["dow_phase"] == "uptrend"

    detail = reader.read_instrument_detail("510300.SH")
    assert detail["decision"]["structure_v1"]["atr14"] == 0.0456

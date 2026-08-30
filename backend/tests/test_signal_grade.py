from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.holding_service import HoldingService
from app.services.signal_grade_service import GRADE_ORDER, assign_grade, classify_row


def _base_values(**overrides) -> dict:
    values = {
        "close": 2.4,
        "ma5": 2.40,
        "ma10": 2.35,
        "ma20": 2.22,
        "ma30": 2.10,
        "macd_dif": 0.02,
        "macd_dea": 0.01,
        "macd_hist": 0.01,
        "kdj_k": 55.0,
        "kdj_d": 50.0,
        "kdj_j": 60.0,
        "rsi14": 55.0,
        "volume_ratio": 1.0,
        "return_1d": 0.01,
        "return_5d": 0.03,
        "td_buy_setup": 0,
        "td_sell_setup": 0,
    }
    values.update(overrides)
    return values


def test_grade_add_entry_probe_watch_reduce_are_mutually_exclusive():
    cfg = {
        "j_add_cap": 90,
        "j_overbought": 100,
        "j_high": 90,
        "j_low": 20,
        "volume_expand": 1.35,
        "volume_contract": 0.85,
        "stall_return": 0.002,
        "macd_approach_hist": 0.0008,
    }
    add = classify_row(_base_values(volume_ratio=1.5, kdj_j=70), pct_change=0.02, cfg=cfg)
    entry = classify_row(_base_values(volume_ratio=1.0, kdj_j=50, macd_hist=0.01), pct_change=0.005, cfg=cfg)
    probe = classify_row(
        _base_values(
            volume_ratio=1.0,
            kdj_j=40,
            kdj_k=45,
            kdj_d=40,
            ma5=2.10,
            ma10=2.20,
            ma20=2.15,
            ma30=2.12,
            macd_hist=-0.02,
            macd_dif=-0.02,
            macd_dea=-0.01,
        ),
        pct_change=-0.01,
        previous={"macd_hist": -0.01, "macd_dif": -0.01, "macd_dea": -0.005, "kdj_k": 44, "kdj_d": 39},
        cfg=cfg,
    )
    watch = classify_row(_base_values(kdj_j=96, kdj_k=80, kdj_d=70, volume_ratio=1.5), pct_change=0.0, previous={"kdj_k": 70, "kdj_d": 72}, cfg=cfg)
    reduce = classify_row(
        _base_values(kdj_k=40, kdj_d=55, kdj_j=30, macd_hist=-0.01, macd_dif=-0.02, macd_dea=-0.01),
        pct_change=-0.02,
        previous={"kdj_k": 56, "kdj_d": 54, "macd_hist": 0.01, "macd_dif": 0.02, "macd_dea": 0.01},
        cfg=cfg,
    )
    grades = [add["grade"], entry["grade"], probe["grade"], watch["grade"], reduce["grade"]]
    assert grades == ["可加仓", "可入场", "可试探", "观望", "减仓"]
    assert len(set(grades)) == 5


def test_missing_core_indicators_are_anomaly_not_a_grade_bucket():
    row = classify_row({"close": 1.0}, pct_change=None, cfg={})
    assert row["grade"] == "数据异常"
    assert row["grade"] not in GRADE_ORDER


def test_grade_view_does_not_write_holdings(db_session):
    before = HoldingService().list(db_session)
    payload = TestClient(app).get("/api/signals/grade").json()
    after = HoldingService().list(db_session)
    assert payload["writes_holdings"] is False
    assert payload["research_only"] is True
    assert payload["version"] == "signal-grade-v0.2.0"
    assert before == after
    assert all(not row["actionable"] for row in payload["rows"])
    assert set(payload["groups"]) == set(GRADE_ORDER)
    assert "数据异常" not in payload["groups"]


def test_assign_grade_reduce_beats_add_when_death_cross():
    grade = assign_grade(
        pct_change=0.03,
        volume={"kind": "expand"},
        ma={"kind": "bull"},
        macd={"kind": "death"},
        kdj={"j": 40, "kind": "death", "death": True},
        cfg={"j_add_cap": 90, "stall_return": 0.002},
    )
    assert grade == "减仓"

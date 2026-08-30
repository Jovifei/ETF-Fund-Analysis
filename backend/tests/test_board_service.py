from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models import Instrument
from app.services.board_service import BoardService, component_scores, weighted_score
from app.services.signal_grade_service import classify_row


def test_board_catalog_has_dozens_of_industry_and_concept_entries():
    payload = TestClient(app).get("/api/signals/boards").json()
    assert payload["scrapes_eastmoney"] is False
    assert payload["research_only"] is True
    assert payload["counts"]["industry"] >= 80
    assert payload["counts"]["concept"] >= 40
    names = {item["name"] for item in payload["industry"]}
    assert "半导体" in names
    assert "银行" in names
    assert "白酒" in names
    concepts = {item["name"] for item in payload["concept"]}
    assert "人工智能" in concepts
    assert "机器人概念" in concepts


def test_board_score_uses_indicator_coefficients_not_llm():
    row = classify_row(
        {
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
            "volume_ratio": 1.5,
            "return_1d": 0.02,
            "return_5d": 0.04,
            "td_buy_setup": 3,
            "td_sell_setup": 0,
        },
        pct_change=0.02,
        cfg={},
    )
    parts = component_scores(row)
    score = weighted_score(parts, {"volume": 0.15, "ma": 0.2, "macd": 0.2, "kdj": 0.15, "rsi": 0.15, "td": 0.05, "momentum": 0.1})
    assert score is not None and 40 <= score <= 90
    assert parts["ma"] > parts["kdj"] or parts["macd"] >= 60


def test_add_fund_to_board_does_not_write_holdings(db_session):
    from app.services.holding_service import HoldingService

    before = HoldingService().list(db_session)
    result = BoardService().add_fund(db_session, "ind-semiconductor", "588000.SH", "科创板50")
    db_session.commit()
    after = HoldingService().list(db_session)
    assert result["ts_code"] == "588000.SH"
    assert result["needs_bars"] is True
    assert before == after
    row = db_session.query(Instrument).filter_by(ts_code="588000.SH").one()
    assert "ind-semiconductor" in (row.metadata_json or {}).get("board_ids", [])


def test_unknown_board_add_is_rejected(db_session):
    try:
        BoardService().add_fund(db_session, "no-such-board", "512480.SH")
        raise AssertionError("expected missing board")
    except KeyError:
        pass

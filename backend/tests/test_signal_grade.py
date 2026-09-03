from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models import SectorSnapshot
from app.services.holding_service import HoldingService
from app.services.signal_grade_service import GRADE_ORDER, SignalGradeService, assign_grade, classify_row


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
    assert payload["version"] == "signal-grade-v0.3.0-reference"
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


# --------------------------------------------------------------------------
# 板块口径：与「K线企稳分析看板」共用真实板块数据（行业 / 概念 / 全市场宽度）
# --------------------------------------------------------------------------

class _StubInstrument:
    """仅暴露 _sector_for 需要的主题属性。"""

    def __init__(self, theme_l1=None, theme_l2=None):
        self.theme_l1 = theme_l1
        self.theme_l2 = theme_l2


def _clear_sectors(db_session):
    db_session.query(SectorSnapshot).delete()
    db_session.flush()


def _add_sector(db_session, name, board_type, up, down, flat=0, total=None):
    db_session.add(
        SectorSnapshot(
            sector_name=name,
            trade_date=date(2026, 9, 1),
            up_count=up,
            down_count=down,
            flat_count=flat,
            total_count=total if total is not None else up + down + flat,
            pct_change=0.5,
            source="ut-signal-grade",
            board_type=board_type,
            quality_hash=f"u-{name}-{board_type}",
        )
    )
    db_session.flush()


def test_signal_grade_sector_uses_industry_board(db_session):
    """行业 ETF 应命中 board_type='industry' 的真实行业板块涨跌家数。"""
    _clear_sectors(db_session)
    _add_sector(db_session, "半导体", "industry", up=21, down=165)

    service = SignalGradeService()
    sector = service._sector_for(db_session, _StubInstrument(theme_l1="科技", theme_l2="半导体"))

    assert sector["board_type"] == "industry"
    assert sector["sector_name"] == "半导体"
    assert sector["up"] == 21
    assert sector["down"] == 165
    assert "半导体 21涨 165跌" in sector["label"]


def test_signal_grade_sector_falls_back_to_concept_board(db_session):
    """无行业板块命中时，应回退到 board_type='concept' 的概念板块。"""
    _clear_sectors(db_session)
    # 只落概念板块（半导体 → 芯片），不落行业板块
    _add_sector(db_session, "芯片", "concept", up=320, down=80)

    service = SignalGradeService()
    sector = service._sector_for(db_session, _StubInstrument(theme_l1="科技", theme_l2="半导体"))

    assert sector["board_type"] == "concept"
    assert sector["sector_name"] == "芯片"
    assert sector["up"] == 320
    assert sector["down"] == 80


def test_signal_grade_sector_uses_market_breadth_for_broad_theme(db_session):
    """宽基/指数主题 ETF 应取全市场涨跌家数（board_type='market'）。"""
    _clear_sectors(db_session)
    _add_sector(db_session, "全市场", "market", up=3094, down=1995, flat=125, total=5214)

    service = SignalGradeService()
    sector = service._sector_for(db_session, _StubInstrument(theme_l1="宽基", theme_l2="大盘核心"))

    assert sector["board_type"] == "market"
    assert sector["up"] == 3094
    assert sector["down"] == 1995
    assert "全市场 3094涨 1995跌" in sector["label"]


def test_signal_grade_sector_note_is_accurate_when_no_board(db_session):
    """无板块数据时 up/down 为 None，且 note 不得误导为"无全市场涨跌家数"。"""
    _clear_sectors(db_session)

    service = SignalGradeService()
    sector = service._sector_for(db_session, _StubInstrument(theme_l1="不存在的主题"))

    assert sector["up"] is None
    assert sector["down"] is None
    assert sector["board_type"] is None
    assert sector["note"] == "无对应行业/概念板块数据"


def test_company_reference_thresholds_and_quote_unit_contract():
    from app.services.signal_grade_service import classify_rsi, classify_volume, quote_percent_points_to_ratio
    assert classify_volume(1.15, 1.15, 0.90)["kind"] == "expand"
    assert classify_volume(0.90, 1.15, 0.90)["kind"] == "flat"
    assert classify_volume(0.89, 1.15, 0.90)["kind"] == "contract"
    rsi_cfg = {"rsi_overbought": 70, "rsi_strong": 50, "rsi_oversold": 30}
    assert classify_rsi(70, rsi_cfg)["label"].startswith("超买")
    assert classify_rsi(50, rsi_cfg)["label"].startswith("正常偏强")
    assert classify_rsi(30, rsi_cfg)["label"].startswith("偏弱")
    assert classify_rsi(29.9, rsi_cfg)["label"].startswith("超卖")
    assert quote_percent_points_to_ratio(3.8) == 0.038


def test_reference_macd_bear_cont_is_reduce_risk():
    from app.services.signal_grade_service import assign_grade
    grade = assign_grade(
        pct_change=-0.01,
        volume={"kind": "flat"},
        ma={"kind": "mixed"},
        macd={"kind": "bear_cont"},
        kdj={"kind": "healthy", "j": 55.0, "death": False},
        cfg={"j_add_cap": 90, "stall_return": 0.002},
    )
    assert grade == "减仓"


def test_company_reference_kdj_boundaries_are_exact():
    from app.services.signal_grade_service import classify_kdj
    cfg = {"j_overbought": 100, "j_high": 90, "j_low": 20}
    def item(j):
        return classify_kdj({"kdj_j": j, "kdj_k": 60, "kdj_d": 50}, None, cfg)
    assert item(19.9)["kind"] == "low"
    assert item(20)["kind"] == "healthy"
    assert item(89.9)["kind"] == "healthy"
    assert item(90)["kind"] == "high"
    assert item(100)["kind"] == "high"
    assert item(100.1)["kind"] == "overbought"

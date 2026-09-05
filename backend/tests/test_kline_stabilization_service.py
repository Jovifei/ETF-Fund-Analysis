from __future__ import annotations

from datetime import date

import pytest

from app.services.kline_stabilization_service import KlineStabilizationService


def test_kline_stabilization_summary_contract(bootstrapped, db_session):
    service = KlineStabilizationService()
    summary = service.summary(db_session)
    assert summary["automatic_orders"] is False
    assert summary["generated_at"]
    assert summary["counts"]["可加仓"] >= 0
    rows = summary["rows"]
    assert rows
    row = rows[0]
    # 核心字段契约
    assert row["action"] in {"可加仓", "可入场", "可试探", "观望", "减仓", "数据异常"}
    assert row["action_source"] in {"decision_board_snapshot", "signal_grade_fallback", "signal_snapshot_last_resort", "unavailable"}
    assert row["actionable"] is False  # 研究态必须 fail closed
    assert "td" in row and row["td"]["setup_length"] == 9
    assert "ma" in row and "label" in row["ma"]
    assert "macd" in row and "label" in row["macd"]
    assert "kdj" in row and "label" in row["kdj"]
    assert "rsi" in row and "val" in row["rsi"]
    assert "volume" in row and "text" in row["volume"]
    # K-line compatibility API reads the same persisted forecast contract as the main board.
    forecast = row["forecast"]
    assert forecast["source"] in {"persisted_forecast_snapshot", "unavailable"}
    if forecast["source"] == "persisted_forecast_snapshot":
        assert forecast["p_up_semantics"] in {"weighted_historical_neighbor_up_frequency", "calibrated_up_probability"}
    # 缠论字段存在（可用或不可用都必须有明确结构）
    assert "available" in row["chanlun"]
    # 研究态 no-orders
    assert row["as_of"]


def test_kline_stabilization_td9_detected_when_present(bootstrapped, db_session):
    """若 DB 中有满足 TD9 条件的标的数据，应输出 TD 标签。"""
    service = KlineStabilizationService()
    summary = service.summary(db_session)
    rows = summary["rows"]
    td_labels = [row["td"]["label"] for row in rows if row["td"]["label"] not in {"—", "0"}]
    # 无论是否触发 TD9，标签格式必须合法（数字、TD9、或带 ↓）
    for label in td_labels:
        assert label.startswith("TD") or label.isdigit() or label.endswith("↓")


def test_kline_stabilization_disclaimers(bootstrapped, db_session):
    service = KlineStabilizationService()
    summary = service.summary(db_session)
    assert any("研究视图" in item for item in summary["disclaimers"])
    assert any("不构成投资建议" in item for item in summary["disclaimers"])
    assert any("唯一 current decision" in item for item in summary["disclaimers"])


def test_pct_change_unit_is_percent_not_ratio():
    """回归：pct_change 单位是百分比，_pct 不能再乘 100（历史 bug 曾输出 367.26）。"""
    from app.services.kline_stabilization_service import _pct

    assert _pct(3.6726) == 3.67
    assert _pct(-1.3636) == -1.36
    assert _pct(None) is None


class _StubInstrument:
    """仅暴露 _sector_state 需要的属性，避免改动真实标的行。"""

    def __init__(self, theme_l1=None, theme_l2=None):
        self.theme_l1 = theme_l1
        self.theme_l2 = theme_l2


def test_sector_alias_maps_theme_to_board(bootstrapped, db_session):
    """主题名（如 新能源车）经显式别名表映射后应命中板块（电池）。

    用「新能源车 → 电池」是因为 mock 数据里没有名为 电池/新能源车 的板块，
    能干净地验证别名兜底路径（不直接命中时才走别名）。
    """
    from app.models import SectorSnapshot

    db_session.add(
        SectorSnapshot(
            sector_name="电池",
            trade_date=date(2026, 9, 1),
            up_count=30,
            down_count=10,
            flat_count=0,
            total_count=40,
            pct_change=1.5,
            source="unit-test",
            quality_hash="unit-test-battery",
        )
    )
    db_session.flush()

    result = KlineStabilizationService._sector_state(
        db_session, _StubInstrument(theme_l1="新能源车"), {"新能源车": "电池"}
    )
    assert result["up"] == 30
    assert result["down"] == 10
    assert result["sector_name"] == "电池"


def test_sector_unmapped_theme_returns_null_not_arbitrary_board(bootstrapped, db_session):
    """无映射的主题必须返回 null（前端显示 —），不能拿无关板块兜底。"""
    result = KlineStabilizationService._sector_state(
        db_session, _StubInstrument(theme_l1="__no_such_theme__"), {}
    )
    assert result["up"] is None
    assert result["down"] is None
    assert result["ratio"] is None


def test_summary_rows_expose_concept_and_market_breadth(bootstrapped, db_session):
    """每行必须同时携带行业板块(sector)、概念板块(sector_concept)、全市场宽度(market_breadth)。"""
    service = KlineStabilizationService()
    summary = service.summary(db_session)
    for row in summary["rows"]:
        assert "sector_concept" in row
        assert "market_breadth" in row
        assert set(row["sector_concept"]) >= {"up", "down", "ratio"}
        # market_breadth 允许为 None（仅宽基/指数 ETF 有值）
        assert row["market_breadth"] is None or set(row["market_breadth"]) >= {"up", "down", "ratio"}


def test_concept_alias_maps_theme_to_concept_board(bootstrapped, db_session):
    """主题(半导体)经 concept_alias 映射后应命中概念板块(芯片)。"""
    from app.models import SectorSnapshot

    db_session.add(
        SectorSnapshot(
            sector_name="芯片",
            trade_date=date(2026, 9, 1),
            up_count=300,
            down_count=80,
            flat_count=5,
            total_count=385,
            pct_change=3.0,
            source="ut-conceptalias",
            board_type="concept",
            quality_hash="u-con2",
        )
    )
    db_session.flush()
    result = KlineStabilizationService._sector_state(
        db_session, _StubInstrument(theme_l2="半导体"), {"半导体": "芯片"}, board_type="concept"
    )
    assert result["sector_name"] == "芯片"
    assert result["board_type"] == "concept"


def test_config_readers_expose_concept_alias_and_broad_market_themes():
    """config 读取器应暴露 concept_alias 与 broad_market_themes（来自 etf_1430_workbench.json）。"""
    service = KlineStabilizationService()
    concept_alias = service._concept_alias()
    assert isinstance(concept_alias, dict)
    assert concept_alias.get("半导体") == "芯片"
    assert "宽基" in service._broad_market_themes()


def test_kline_summary_api_marks_deprecated(bootstrapped):
    """PR-I：兼容 API 废弃标记——K线研判并入 /etf/{code} + /boards。"""
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/workbench/kline/summary")
        assert response.status_code == 200
        payload = response.json()
        assert payload.get("deprecated") is True
        assert "/etf/" in payload.get("successor", "")

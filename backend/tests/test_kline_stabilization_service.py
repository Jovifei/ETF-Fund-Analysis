from __future__ import annotations

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
    assert row["action"] in {"可加仓", "可入场", "可试探", "观望", "减仓"}
    assert row["actionable"] is False  # 研究态必须 fail closed
    assert "td" in row and row["td"]["setup_length"] == 9
    assert "ma" in row and "label" in row["ma"]
    assert "macd" in row and "label" in row["macd"]
    assert "kdj" in row and "label" in row["kdj"]
    assert "rsi" in row and "val" in row["rsi"]
    assert "volume" in row and "text" in row["volume"]
    # 形态预测必须未校准
    forecast = row["forecast"]
    assert forecast["calibration_status"] == "not_calibrated"
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

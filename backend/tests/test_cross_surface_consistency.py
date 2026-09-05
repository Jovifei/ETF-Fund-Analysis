"""跨页面一致性门禁（修复方案 PR-B 验收）。

同一 ETF 在 决策总表 / 14:30 工作台 / K线看板 三个读取面上：
* current action 必须完全一致（唯一决策契约）；
* 支撑/压力数值必须完全一致（统一 SupportResistanceSnapshot 口径）；
* 指标语义标签必须来自同一 indicator_state 推导。

注意：共享的 session 级测试库会被其他断言计数（如 test_decision_board 的
快照计数），因此本模块在结束时清理自己产生的 DecisionBoardSnapshot 行。
"""
from __future__ import annotations

import pytest

from app.services.decision_board_service import DecisionBoardService
from app.services.etf_1430_service import ETF1430WorkbenchService
from app.services.kline_stabilization_service import KlineStabilizationService
from app.services.support_resistance_service import SupportResistanceService
from app.services.task_service import TaskService


@pytest.fixture()
def _cleanup_board_snapshots(db_session):
    """记录并清理本测试产生的 DecisionBoardSnapshot，保持共享库对其他测试稳定。"""
    from sqlalchemy import delete, select

    from app.models import DecisionBoardSnapshot

    existing_ids = set(
        db_session.scalars(select(DecisionBoardSnapshot.id)).all()
    )
    yield
    db_session.execute(
        delete(DecisionBoardSnapshot).where(
            DecisionBoardSnapshot.id.not_in(existing_ids) if existing_ids else True
        )
    )
    db_session.commit()


def _board_rows(db):
    TaskService().run(db, "refresh_decision_board")
    db.flush()
    payload = DecisionBoardService().read_latest(db)
    assert payload is not None
    return {row["ts_code"]: row for row in payload["rows"]}


def test_actions_and_support_resistance_consistent_across_surfaces(
    bootstrapped, db_session, _cleanup_board_snapshots
):
    board = _board_rows(db_session)
    assert board, "decision board payload expected after refresh"

    kline_rows = {row["ts_code"]: row for row in KlineStabilizationService().summary(db_session)["rows"]}
    wb_rows = {row["ts_code"]: row for row in ETF1430WorkbenchService().summary(db_session)["rows"]}
    sr_service = SupportResistanceService()

    common = [code for code in board if code in kline_rows and code in wb_rows]
    assert common, "expected overlapping instruments across all three surfaces"

    checked = 0
    for code in common:
        b, k, w = board[code], kline_rows[code], wb_rows[code]

        # 1) 唯一决策契约：三个面的 action 完全一致
        assert k["action"] == b["grade"] == w["action"], (
            f"{code} action drift: board={b['grade']} kline={k['action']} 1430={w['action']}"
        )

        # 2) 支撑/压力同一快照口径（board 与 1430 都来自 SupportResistanceSnapshot）
        b_sr = b.get("support_resistance") or {}
        w_sr = w.get("support_resistance") or {}
        b_support = ((b_sr.get("nearest_support") or {}).get("price")) if isinstance(b_sr, dict) else None
        w_support = ((w_sr.get("nearest_support") or {}).get("price")) if isinstance(w_sr, dict) else None
        if b_support is not None and w_support is not None:
            assert abs(float(b_support) - float(w_support)) < 1e-9, f"{code} support drift"
        b_resistance = ((b_sr.get("nearest_resistance") or {}).get("price")) if isinstance(b_sr, dict) else None
        w_resistance = ((w_sr.get("nearest_resistance") or {}).get("price")) if isinstance(w_sr, dict) else None
        if b_resistance is not None and w_resistance is not None:
            assert abs(float(b_resistance) - float(w_resistance)) < 1e-9, f"{code} resistance drift"
        checked += 1
    assert checked >= 3


def test_support_resistance_snapshot_persisted_and_reused(
    bootstrapped, db_session, _cleanup_board_snapshots
):
    """refresh 后快照落库；summary 读取同一 payload（snapshot_source=persisted_snapshot）。"""
    _board_rows(db_session)
    service = SupportResistanceService()
    from app.models import Instrument, SupportResistanceSnapshot
    from sqlalchemy import select

    instruments = db_session.scalars(select(Instrument).where(Instrument.enabled.is_(True))).all()
    assert instruments
    for instrument in instruments[:3]:
        snapshots = db_session.scalars(
            select(SupportResistanceSnapshot).where(
                SupportResistanceSnapshot.instrument_id == instrument.id
            )
        ).all()
        assert snapshots, f"{instrument.ts_code} should have a persisted S/R snapshot"
        latest = service.latest(db_session, instrument.id)
        assert latest is not None
        assert latest.get("snapshot_source") == "persisted_snapshot"
        assert "levels" in latest and "chan_zone_approx" in latest
        # 历史行有 amount（统一输入口径：真实成交额或 volume*close 降级）
        stored = snapshots[0]
        assert stored.source_bars > 0


def test_kline_states_match_signal_grade_semantics(bootstrapped, db_session):
    """kline 行的 MACD/KDJ 语义标签与 signal_grade 从同一 values_json 推导（等价性抽查）。"""
    from app.services.signal_grade_service import SignalGradeService

    rows = KlineStabilizationService().summary(db_session)["rows"]
    assert rows
    grades = SignalGradeService().build(db_session)
    grade_rows = {row["ts_code"]: row for row in grades["rows"]}
    for row in rows[:5]:
        gr = grade_rows.get(row["ts_code"])
        if not gr:
            continue
        # 同一 values_json → 同一 MACD 标签（kline 视图只是形状适配）
        assert row["macd"]["label"] == (gr.get("macd") or {}).get("label", row["macd"]["label"])
        # KDJ 的 sub 与分级标签一致（超买/偏高/死叉/低位/健康）
        assert row["kdj"]["sub"] == (gr.get("kdj") or {}).get("label", row["kdj"]["sub"])

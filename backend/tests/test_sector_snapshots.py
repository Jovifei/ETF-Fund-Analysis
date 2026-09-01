from __future__ import annotations

from datetime import date

import pytest

from app.models import SectorSnapshot
from app.providers.akshare import AKShareProvider
from app.providers.base import ProviderError
from app.providers.types import SectorRecord
from app.services.kline_stabilization_service import KlineStabilizationService
from app.services.market_service import MarketService
from app.services.task_service import TaskService


class _FakeSectorProvider:
    """带 fetch_sector_snapshots 的假 provider，模拟成功路径。"""

    name = "fake"

    def fetch_sector_snapshots(self) -> list[SectorRecord]:
        return [
            SectorRecord(
                sector_name="AI应用",
                trade_date=date(2026, 8, 31),
                up_count=390,
                down_count=142,
                flat_count=8,
                total_count=540,
                pct_change=2.02,
            ),
            SectorRecord(
                sector_name="有色金属",
                trade_date=date(2026, 8, 31),
                up_count=20,
                down_count=180,
                flat_count=5,
                total_count=205,
                pct_change=-1.60,
            ),
        ]


def test_market_service_refresh_sector_snapshots_inserts(bootstrapped, db_session):
    service = MarketService(_FakeSectorProvider(), persist_provider_audits=False)
    result = service.refresh_sector_snapshots(db_session)
    assert result["inserted"] == 2
    assert result["error"] is None
    # 验证 fake provider 的板块已落库（按名称过滤，避免与其他来源数据串扰）
    ai = db_session.query(SectorSnapshot).filter(SectorSnapshot.sector_name == "AI应用").first()
    assert ai is not None
    assert ai.up_count == 390
    assert ai.down_count == 142
    assert ai.total_count == 540
    ys = db_session.query(SectorSnapshot).filter(SectorSnapshot.sector_name == "有色金属").first()
    assert ys is not None
    assert ys.up_count == 20


def test_market_service_refresh_sector_snapshots_idempotent(bootstrapped, db_session):
    service = MarketService(_FakeSectorProvider(), persist_provider_audits=False)
    first = service.refresh_sector_snapshots(db_session)
    assert first["inserted"] == 2
    second = service.refresh_sector_snapshots(db_session)
    # upsert 语义：再次刷新不新增行（fake 的 2026-08-31 AI应用 仍只有一条）
    assert second["inserted"] == 2
    count = (
        db_session.query(SectorSnapshot)
        .filter(SectorSnapshot.sector_name == "AI应用", SectorSnapshot.trade_date == date(2026, 8, 31))
        .count()
    )
    assert count == 1


def test_market_service_refresh_sector_snapshots_degrades_when_unsupported(bootstrapped, db_session):
    """provider 不支持板块快照时降级：inserted=0 + error，不抛异常，且不写入任何行。"""
    before = db_session.query(SectorSnapshot).count()

    class _NoSectorProvider:
        name = "mock-no-sector"

    service = MarketService(_NoSectorProvider(), persist_provider_audits=False)
    result = service.refresh_sector_snapshots(db_session)
    assert result["inserted"] == 0
    assert result["error"] == "ProviderError"
    after = db_session.query(SectorSnapshot).count()
    assert after == before  # 降级不写入任何新行


def test_kline_service_reads_sector_snapshot(bootstrapped, db_session):
    """落库后 kline 服务应能读出板块涨跌家数。"""
    service = MarketService(_FakeSectorProvider(), persist_provider_audits=False)
    service.refresh_sector_snapshots(db_session)

    kline = KlineStabilizationService()
    summary = kline.summary(db_session)
    # 任一行的 sector 结构必须合法（可能 null 或带值）
    for row in summary["rows"]:
        assert set(row["sector"]) >= {"up", "down", "ratio"}


def test_task_service_registers_sector_snapshot_task():
    """TaskService 注册了 refresh_sector_snapshots 调度任务。"""
    assert "refresh_sector_snapshots" in TaskService().task_names


# --------------------------------------------------------------------------
# AKShare provider：东财主源 → 同花顺备用源的降级链
# --------------------------------------------------------------------------

def _frame(rows: list[dict]):
    import pandas as pd

    return pd.DataFrame(rows)


class _FakeAk:
    """假的 akshare 模块，只暴露板块接口，用于脱离真实网络测试降级链。"""

    def __init__(self, em=None, ths=None):
        self._em = em
        self._ths = ths

    def stock_board_industry_name_em(self):
        if self._em is None:
            raise ProviderError("boom-em")
        if isinstance(self._em, Exception):
            raise self._em
        return self._em

    def stock_board_industry_summary_ths(self):
        if self._ths is None:
            raise ProviderError("boom-ths")
        if isinstance(self._ths, Exception):
            raise self._ths
        return self._ths


def _provider(em=None, ths=None) -> AKShareProvider:
    provider = AKShareProvider()
    provider.ak = _FakeAk(em=em, ths=ths)
    return provider


def test_akshare_sector_uses_eastmoney_when_available():
    """东财可用时优先用东财（含平盘家数）。"""
    em = _frame([{"板块名称": "AI应用", "上涨家数": 390, "下跌家数": 142, "平盘家数": 8, "涨跌幅": 2.02}])
    rows = _provider(em=em).fetch_sector_snapshots(trade_date=date(2026, 8, 31))
    assert len(rows) == 1
    assert rows[0].sector_name == "AI应用"
    assert (rows[0].up_count, rows[0].down_count, rows[0].flat_count) == (390, 142, 8)
    assert rows[0].total_count == 540
    assert rows[0].pct_change == 2.02


def test_akshare_sector_falls_back_to_ths():
    """东财不可达时降级到同花顺：总家数按 涨+跌 计，平盘记 0。"""
    ths = _frame([{"板块": "半导体", "涨跌幅": -2.64, "上涨家数": 21, "下跌家数": 165}])
    rows = _provider(em=RuntimeError("ProxyError"), ths=ths).fetch_sector_snapshots(trade_date=date(2026, 8, 31))
    assert len(rows) == 1
    assert rows[0].sector_name == "半导体"
    assert (rows[0].up_count, rows[0].down_count, rows[0].flat_count) == (21, 165, 0)
    assert rows[0].total_count == 186
    assert rows[0].pct_change == -2.64


def test_akshare_sector_raises_when_all_sources_fail():
    """两个源都失败才抛 ProviderError，且错误信息带上每个源的原因。"""
    provider = _provider(em=RuntimeError("em-down"), ths=RuntimeError("ths-down"))
    with pytest.raises(ProviderError) as excinfo:
        provider.fetch_sector_snapshots()
    message = str(excinfo.value)
    assert "em-down" in message
    assert "ths-down" in message

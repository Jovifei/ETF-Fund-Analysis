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


class _FakeAllBoardsProvider:
    """同时支持 行业 / 概念 / 全市场 三类板块快照的假 provider。"""

    name = "fake-all"

    def fetch_sector_snapshots(self, trade_date=None) -> list[SectorRecord]:
        return [
            SectorRecord(
                sector_name="AI应用",
                trade_date=date(2026, 8, 31),
                up_count=390,
                down_count=142,
                flat_count=8,
                total_count=540,
                pct_change=2.02,
                board_type="industry",
            )
        ]

    def fetch_concept_snapshots(self, trade_date=None) -> list[SectorRecord]:
        return [
            SectorRecord(
                sector_name="芯片",
                trade_date=date(2026, 8, 31),
                up_count=300,
                down_count=80,
                flat_count=5,
                total_count=385,
                pct_change=3.0,
                board_type="concept",
            )
        ]

    def fetch_market_breadth(self, trade_date=None) -> SectorRecord | None:
        return SectorRecord(
            sector_name="全市场",
            trade_date=date(2026, 8, 31),
            up_count=3000,
            down_count=2000,
            flat_count=100,
            total_count=5100,
            pct_change=0.5,
            board_type="market",
        )


def test_market_service_refresh_sector_snapshots_inserts(bootstrapped, db_session):
    service = MarketService(_FakeSectorProvider(), persist_provider_audits=False)
    result = service.refresh_sector_snapshots(db_session)
    assert result["inserted"] == 2
    # 行业板块成功落库；概念/全市场因该 fake provider 不支持而优雅降级（不抛异常）
    assert result["boards"]["industry"]["error"] is None
    assert result["boards"]["industry"]["inserted"] == 2
    assert result["boards"]["concept"]["error"] == "ProviderError"
    assert result["boards"]["market"]["error"] == "ProviderError"
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
    # 三类板块均降级，总 error 非 None 且首类为 ProviderError
    assert result["error"] is not None
    assert result["error"].startswith("industry:")
    assert result["boards"]["industry"]["error"] == "ProviderError"
    assert result["boards"]["concept"]["error"] == "ProviderError"
    assert result["boards"]["market"]["error"] == "ProviderError"
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


def test_market_service_refresh_all_three_boards(bootstrapped, db_session):
    """provider 同时支持 行业/概念/全市场 时，三类快照都应落库。"""
    service = MarketService(_FakeAllBoardsProvider(), persist_provider_audits=False)
    result = service.refresh_sector_snapshots(db_session)
    assert result["inserted"] == 3
    assert result["error"] is None
    assert result["boards"]["industry"]["inserted"] == 1
    assert result["boards"]["concept"]["inserted"] == 1
    assert result["boards"]["market"]["inserted"] == 1
    # 验证 board_type 已正确落库（行业 / 概念 / 市场 各一条）
    boards = {
        s.board_type
        for s in db_session.query(SectorSnapshot)
        .filter(SectorSnapshot.trade_date == date(2026, 8, 31))
        .all()
    }
    assert boards == {"industry", "concept", "market"}


def test_sector_state_filters_by_board_type(bootstrapped, db_session):
    """_sector_state 必须按 board_type 精准隔离：行业命中不污染概念。"""
    from app.models import SectorSnapshot as SS

    db_session.add_all(
        [
            SS(sector_name="电池", trade_date=date(2026, 9, 1), up_count=30, down_count=10,
               flat_count=0, total_count=40, pct_change=1.5, source="ut-boardfilter", board_type="industry",
               quality_hash="u-ind"),
            SS(sector_name="芯片", trade_date=date(2026, 9, 1), up_count=300, down_count=80,
               flat_count=5, total_count=385, pct_change=3.0, source="ut-boardfilter", board_type="concept",
               quality_hash="u-con"),
        ]
    )
    db_session.flush()

    industry = KlineStabilizationService._sector_state(
        db_session, _StubInstrument(theme_l1="新能源车"), {"新能源车": "电池"}, board_type="industry"
    )
    assert industry["sector_name"] == "电池"
    assert industry["board_type"] == "industry"

    concept = KlineStabilizationService._sector_state(
        db_session, _StubInstrument(theme_l2="半导体"), {"半导体": "芯片"}, board_type="concept"
    )
    assert concept["sector_name"] == "芯片"
    assert concept["board_type"] == "concept"

    # 反向：用行业别名查 concept 类型必须落空（不串类别）
    miss = KlineStabilizationService._sector_state(
        db_session, _StubInstrument(theme_l1="新能源车"), {"新能源车": "电池"}, board_type="concept"
    )
    assert miss["up"] is None


def test_market_breadth_reads_single_row(bootstrapped, db_session):
    """_market_breadth 只取 board_type='market' 的唯一全市场行。"""
    from app.models import SectorSnapshot as SS

    # 清除 bootstrap（mock）可能写入的全市场行，避免污染断言
    db_session.query(SS).filter(SS.board_type == "market").delete()
    db_session.add(
        SS(sector_name="全市场", trade_date=date(2026, 9, 1), up_count=3000, down_count=2000,
           flat_count=100, total_count=5100, pct_change=0.5, source="ut-breadth", board_type="market",
           quality_hash="u-mkt")
    )
    db_session.flush()

    breadth = KlineStabilizationService._market_breadth(db_session)
    assert breadth is not None
    assert breadth["sector_name"] == "全市场"
    assert breadth["up"] == 3000
    assert breadth["down"] == 2000
    assert breadth["flat"] == 100
    assert breadth["total"] == 5100
    # 跌比 = 2000/5100 ≈ 39.2%
    assert round(breadth["ratio"], 1) == 39.2


def test_market_breadth_prefers_real_source_over_mock(bootstrapped, db_session):
    """健壮性核心：即使 mock 行更新（trade_date/fetched_at 更晚），真实源也必须优先。

    模拟真实风险场景——mock provider 在演示模式手动刷出一条「全市场」假数据，
    其时间戳晚于之前落库的真实 AKShare 宽度。_market_breadth 必须用 case 排序把
    真实源(source != 'mock-sector')顶到最前，避免假数据遮蔽真实研究结论。
    """
    from app.models import SectorSnapshot as SS
    from datetime import datetime

    db_session.query(SS).filter(SS.board_type == "market").delete()

    # 真实源：较早落库（akshare）
    db_session.add(
        SS(sector_name="全市场", trade_date=date(2026, 9, 1), up_count=3094, down_count=1995,
           flat_count=125, total_count=5214, pct_change=0.41, source="akshare", board_type="market",
           fetched_at=datetime(2026, 9, 1, 20, 2, 14), quality_hash="u-mkt-real")
    )
    # mock 源：更晚落库（演示假数据 3387/2039/126）——必须被真实源压过
    db_session.add(
        SS(sector_name="全市场", trade_date=date(2026, 9, 2), up_count=3387, down_count=2039,
           flat_count=126, total_count=5552, pct_change=-0.20, source="mock-sector", board_type="market",
           fetched_at=datetime(2026, 9, 2, 9, 0, 0), quality_hash="u-mkt-mock")
    )
    db_session.flush()

    breadth = KlineStabilizationService._market_breadth(db_session)
    assert breadth is not None
    # 取到的必须是真实 akshare 行，而不是更晚的 mock 行
    assert breadth["source"] == "akshare"
    assert breadth["is_mock"] is False
    assert breadth["up"] == 3094
    assert breadth["down"] == 1995
    assert breadth["total"] == 5214


def test_market_breadth_falls_back_to_mock_only_when_no_real(bootstrapped, db_session):
    """无任何真实源时，才回退到 mock 行（保留演示可用性，但显式标注 is_mock）。"""
    from app.models import SectorSnapshot as SS
    from datetime import datetime

    db_session.query(SS).filter(SS.board_type == "market").delete()
    db_session.add(
        SS(sector_name="全市场", trade_date=date(2026, 9, 2), up_count=3387, down_count=2039,
           flat_count=126, total_count=5552, pct_change=-0.20, source="mock-sector", board_type="market",
           fetched_at=datetime(2026, 9, 2, 9, 0, 0), quality_hash="u-mkt-mock")
    )
    db_session.flush()

    breadth = KlineStabilizationService._market_breadth(db_session)
    assert breadth is not None
    assert breadth["source"] == "mock-sector"
    assert breadth["is_mock"] is True
    assert breadth["up"] == 3387


class _StubInstrument:
    """仅暴露 _sector_state 需要的属性，避免改动真实标的行。"""

    def __init__(self, theme_l1=None, theme_l2=None):
        self.theme_l1 = theme_l1
        self.theme_l2 = theme_l2


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


def _fake_code_df():
    import pandas as pd

    return pd.DataFrame(
        {"code": ["600000", "000001", "600519", "300750"], "name": ["a", "b", "c", "d"]}
    )


def _tencent_payload(pct: float) -> str:
    """构造腾讯行情行 payload：第 33 个 ~ 分隔字段(索引 32)为涨跌幅%。"""
    parts = ["x"] * 32 + [f"{pct}"] + ["y"] * 5
    return "~".join(parts)


def _provider_no_init(fake_ak):
    """绕过 __init__ 构造 AKShareProvider 实例（单元测试用，不触发真实网络/watchlist）。"""
    prov = AKShareProvider.__new__(AKShareProvider)
    prov.name = "akshare"
    prov.ak = fake_ak
    return prov


def test_akshare_market_breadth_tencent_parses_quotes():
    """腾讯回退：批量报价按字段 32(涨跌幅%) 统计 涨/跌/平。"""
    import io
    from unittest.mock import MagicMock, patch

    fake_ak = MagicMock()
    fake_ak.stock_info_a_code_name.return_value = _fake_code_df()
    prov = _provider_no_init(fake_ak)
    body = ";".join(
        [
            'v_sh600000="' + _tencent_payload(1.71) + '"',
            'v_sz000001="' + _tencent_payload(0.00) + '"',
            'v_sh600519="' + _tencent_payload(-0.50) + '"',
            'v_sz300750="' + _tencent_payload(3.20) + '"',
        ]
    )
    with patch("urllib.request.urlopen", return_value=io.BytesIO(body.encode("gbk"))):
        rec = prov._fetch_market_breadth_tencent(date(2026, 9, 1))
    assert rec is not None
    assert rec.board_type == "market"
    assert rec.sector_name == "全市场"
    assert rec.up_count == 2  # 600000(+1.71), 300750(+3.20)
    assert rec.down_count == 1  # 600519(-0.50)
    assert rec.flat_count == 1  # 000001(0.00)
    assert rec.total_count == 4
    assert rec.pct_change is not None


def test_akshare_market_breadth_falls_back_to_tencent_when_sina_fails():
    """sina 主源失败时应回退到腾讯并成功返回真实结构。"""
    import io
    from unittest.mock import MagicMock, patch

    fake_ak = MagicMock()
    fake_ak.stock_zh_a_spot.side_effect = RuntimeError("sina-down")
    fake_ak.stock_info_a_code_name.return_value = _fake_code_df()
    prov = _provider_no_init(fake_ak)
    body = 'v_sh600000="' + _tencent_payload(2.0) + '"'
    with patch("urllib.request.urlopen", return_value=io.BytesIO(body.encode("gbk"))):
        rec = prov.fetch_market_breadth(date(2026, 9, 1))
    assert rec is not None
    assert rec.up_count == 1
    assert rec.down_count == 0


def test_akshare_market_breadth_returns_none_when_both_fail():
    """sina 与腾讯都失败时应优雅降级返回 None（不抛异常）。"""
    from unittest.mock import MagicMock

    fake_ak = MagicMock()
    fake_ak.stock_zh_a_spot.side_effect = RuntimeError("sina-down")
    fake_ak.stock_info_a_code_name.side_effect = RuntimeError("code-list-down")
    prov = _provider_no_init(fake_ak)
    assert prov.fetch_market_breadth(date(2026, 9, 1)) is None


# --------------------------------------------------------------------------
# AKShare provider：概念板块东财 → 同花顺降级（无涨跌家数）
# --------------------------------------------------------------------------

def test_akshare_concept_uses_eastmoney_when_available():
    """东财概念可用时优先用东财（含涨跌家数）。"""
    from unittest.mock import MagicMock

    fake_ak = MagicMock()
    fake_ak.stock_board_concept_name_em.return_value = _frame(
        [{"板块名称": "芯片概念", "上涨家数": 300, "下跌家数": 80, "平盘家数": 5, "涨跌幅": 3.0}]
    )
    prov = _provider_no_init(fake_ak)
    rows = prov.fetch_concept_snapshots(trade_date=date(2026, 8, 31))
    assert len(rows) == 1
    assert rows[0].sector_name == "芯片概念"
    assert rows[0].board_type == "concept"
    assert (rows[0].up_count, rows[0].down_count) == (300, 80)


def test_akshare_concept_falls_back_to_ths_without_breadth():
    """东财概念被断时降级同花顺：有成分股数量但无涨跌家数，up/down 记 0。"""
    from unittest.mock import MagicMock

    fake_ak = MagicMock()
    fake_ak.stock_board_concept_name_em.side_effect = RuntimeError("em-down")
    fake_ak.stock_board_concept_summary_ths.return_value = _frame(
        [{"概念名称": "MLCC概念", "成分股数量": 37, "驱动事件": "x", "龙头股": "y"}]
    )
    prov = _provider_no_init(fake_ak)
    rows = prov.fetch_concept_snapshots(trade_date=date(2026, 8, 31))
    assert len(rows) == 1
    assert rows[0].sector_name == "MLCC概念"
    assert rows[0].board_type == "concept"
    assert rows[0].total_count == 37
    assert (rows[0].up_count, rows[0].down_count) == (0, 0)


def test_akshare_concept_returns_empty_when_all_fail():
    """概念两源都失败时返回空列表（优雅降级，不抛异常）。"""
    from unittest.mock import MagicMock

    fake_ak = MagicMock()
    fake_ak.stock_board_concept_name_em.side_effect = RuntimeError("em-down")
    fake_ak.stock_board_concept_summary_ths.side_effect = RuntimeError("ths-down")
    prov = _provider_no_init(fake_ak)
    assert prov.fetch_concept_snapshots(trade_date=date(2026, 8, 31)) == []


# --------------------------------------------------------------------------
# AKShare provider：K线东财 → 新浪降级
# --------------------------------------------------------------------------

def test_akshare_daily_bars_falls_back_to_sina():
    """东财 fund_etf_hist_em 被断时降级新浪 fund_etf_hist_sina。"""
    from unittest.mock import MagicMock

    fake_ak = MagicMock()
    fake_ak.fund_etf_hist_em.side_effect = RuntimeError("em-down")
    fake_ak.fund_etf_hist_sina.return_value = _frame(
        [
            {"date": "2025-01-02", "open": 3.90, "high": 3.95, "low": 3.88, "close": 3.91, "volume": 1000, "amount": 2000},
            {"date": "2025-01-03", "open": 3.91, "high": 3.96, "low": 3.89, "close": 3.92, "volume": 1100, "amount": 2200},
        ]
    )
    prov = _provider_no_init(fake_ak)
    prov._watchlist = [{"symbol": "510300", "kind": "ETF"}]
    rows = prov.fetch_daily_bars("510300.SH", date(2025, 1, 1), date(2025, 1, 31))
    assert len(rows) == 2
    assert rows[0].trade_date == date(2025, 1, 2)
    assert rows[0].close == 3.91
    # 新浪源无涨跌幅字段，pct_change 记 None，但 pre_close 由前一日 close 回填
    assert rows[1].pre_close == 3.91


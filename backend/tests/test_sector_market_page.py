"""PR-E：行业板块一等页（/boards + /api/sectors/market）。

覆盖语义契约：板块行为 = SectorSnapshot 广度 + 池内 ETF 代理，非东财板块指数；
广度缺失时诚实 unavailable，不用成员 ETF 涨跌冒充板块行情。
"""
from __future__ import annotations

from datetime import date

from app.services.board_service import BoardService
from app.models import SectorSnapshot
from sqlalchemy import select

# 共享 session 库中可能有其他测试写入的板块快照；用远期日期 + 专属 source
# 保证本测试的数据是"最新"且不撞唯一键 (sector_name, trade_date, source, board_type)。
FUTURE_DATE = date(2026, 12, 31)
SOURCE = "pr-e-test"


def _seed_breadth(db_session, name: str, kind: str, up: int, down: int, pct: float) -> None:
    existing = db_session.scalar(
        select(SectorSnapshot).where(
            SectorSnapshot.board_type == kind,
            SectorSnapshot.sector_name == name,
            SectorSnapshot.trade_date == FUTURE_DATE,
            SectorSnapshot.source == SOURCE,
        )
    )
    if existing is not None:
        return
    db_session.add(
        SectorSnapshot(
            board_type=kind,
            sector_name=name,
            trade_date=FUTURE_DATE,
            up_count=up,
            down_count=down,
            flat_count=0,
            total_count=up + down,
            pct_change=pct,
            source=SOURCE,
            quality_hash="pr-e-test-hash",
        )
    )
    db_session.flush()


def test_market_overview_ranks_by_breadth_and_merges_proxies(bootstrapped, db_session):
    _seed_breadth(db_session, "半导体", "industry", up=210, down=40, pct=9.9)
    _seed_breadth(db_session, "贵金属", "industry", up=30, down=80, pct=-1.2)
    overview = BoardService().market_overview(db_session, kind="industry")
    assert overview["research_only"] is True and overview["actionable"] is False
    assert overview["scrapes_eastmoney"] is False
    assert overview["trade_date"] == FUTURE_DATE.isoformat()
    assert overview["counts"]["with_breadth"] >= 2

    names = [board["name"] for board in overview["boards"]]
    assert "半导体" in names and "贵金属" in names

    semiconductor = next(board for board in overview["boards"] if board["name"] == "半导体")
    assert semiconductor["breadth"]["up"] == 210
    assert semiconductor["breadth"]["down_ratio"] == round(40 / 250 * 100, 1)
    assert semiconductor["breadth"]["trade_date"] == FUTURE_DATE.isoformat()
    if semiconductor["members"]:
        assert semiconductor["members"][0]["grade"] in {"可加仓", "可入场", "可试探", "观望", "减仓", "数据异常"}

    # 未配置广度的板块诚实标注 None（前端显示不可用），不编造
    no_breadth = [board for board in overview["boards"] if board["breadth"] is None]
    assert all(board["sector_pct_change"] is None for board in no_breadth)

    # 本测试种下的两个板块之间按涨跌降序
    assert names.index("半导体") < names.index("贵金属")


def test_market_overview_kind_filter(bootstrapped, db_session):
    _seed_breadth(db_session, "半导体", "industry", up=210, down=40, pct=9.9)
    overview_all = BoardService().market_overview(db_session, kind=None)
    kinds = {board["kind"] for board in overview_all["boards"]}
    assert kinds <= {"industry", "concept"}
    overview_concept = BoardService().market_overview(db_session, kind="concept")
    assert all(board["kind"] == "concept" for board in overview_concept["boards"])


def test_sectors_market_api_and_boards_page(bootstrapped):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/sectors/market")
        assert response.status_code == 200
        payload = response.json()
        assert payload["research_only"] is True
        assert "boards" in payload

        filtered = client.get("/api/sectors/market?kind=concept")
        assert filtered.status_code == 200
        assert all(board["kind"] == "concept" for board in filtered.json()["boards"])

        bad = client.get("/api/sectors/market?kind=invalid")
        assert bad.status_code == 422

        page = client.get("/boards")
        assert page.status_code == 200
        assert "行业板块 · 板块市场" in page.text
        assert "ETF 代理" in page.text
        script = client.get("/assets/boards.js")
        assert script.status_code == 200
        assert "/api/sectors/market" in script.text

        # 决策总览导航含板块入口
        home = client.get("/")
        assert home.status_code == 200
        # 主导航由统一壳 JS 渲染：断言壳脚本包含 /boards 链接（单一来源）
        shell_js = client.get("/assets/app_shell.js")
        assert shell_js.status_code == 200
        assert "/boards" in shell_js.text

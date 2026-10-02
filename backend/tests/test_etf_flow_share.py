"""Free ETF flow and exchange share-change research fields."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from app.core.config import Settings
from app.models import DecisionBoardSnapshot, EtfShareScale, IndicatorSnapshot, Instrument, QuoteSnapshot
from app.providers.akshare import SPOT_FLOW_CONTRACT, AKShareProvider
from app.providers.base import CapabilityUnavailable, ProviderError
from app.providers.bounded_sdk import AKSHARE_APIS
from app.providers.composite import CompositeProvider
from app.providers.types import ShareScaleRecord
from app.services.decision_board_service import DecisionBoardService
from app.services.flow_share_research import build_flow_share_view
from app.services.market_service import MarketService
from app.services.share_scale_service import ShareScaleService, annotate_share_series
from app.services.signal_grade_service import SignalGradeService
from app.services.task_service import TaskService
from app.services.trading_calendar_service import TradingDayDecision

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _instrument(db, ts_code: str, symbol: str, exchange: str) -> Instrument:
    row = db.query(Instrument).filter(Instrument.ts_code == ts_code).one_or_none()
    if row is None:
        row = Instrument(ts_code=ts_code, symbol=symbol, name=symbol, kind="ETF", exchange=exchange, enabled=True)
        db.add(row)
        db.flush()
    return row


class _Calendar:
    def __init__(self, verified: bool = True) -> None:
        self.verified = verified

    def decision(self, day: date) -> TradingDayDecision:
        return TradingDayDecision(day=day, is_trade_day=True, verified=self.verified, source="test")


def test_spot_flow_fields_map_without_inventing_premium_or_realtime():
    def etf():
        return [{
            "代码": "510300",
            "最新价": 4.0,
            "IOPV实时估值": 4.2,
            "基金折价率": -1.25,
            "涨跌幅": 0,
            "成交量": 20,
            "成交额": 8000,
            "主力净流入-净额": -1500.5,
            "超大单净流入-净额": -800,
            "大单净流入-净额": -700.5,
            "中单净流入-净额": 300,
            "小单净流入-净额": 1200.5,
            "最新份额": 123456789,
        }]

    provider = AKShareProvider(Settings(_env_file=None), ak_client=SimpleNamespace(fund_etf_spot_em=etf, fund_lof_spot_em=lambda: []))
    quote = provider.fetch_spot_quotes(["510300.SH"])[0]

    assert quote.volume == 2000
    assert quote.is_realtime is False
    assert quote.flow_contract == SPOT_FLOW_CONTRACT
    assert quote.iopv == 4.2
    assert quote.premium_rate == -1.25
    assert quote.latest_shares == 123456789
    assert quote.main_net_inflow == -1500.5
    assert quote.super_large_net_inflow == -800
    assert quote.large_net_inflow == -700.5
    assert quote.medium_net_inflow == 300
    assert quote.small_net_inflow == 1200.5
    assert quote.source == "akshare:em:v101"


def test_missing_discount_is_not_recomputed_from_price_and_iopv():
    def etf():
        return [{"代码": "510300", "最新价": 1.0, "IOPV实时估值": 2.0, "涨跌幅": 0}]

    provider = AKShareProvider(Settings(_env_file=None), ak_client=SimpleNamespace(fund_etf_spot_em=etf))
    quote = provider.fetch_spot_quotes(["510300.SH"])[0]
    assert quote.premium_rate is None
    assert quote.iopv == 2.0
    assert quote.flow_contract == SPOT_FLOW_CONTRACT


def test_share_scale_allowlist_includes_exchange_helpers():
    assert {"fund_etf_scale_sse", "fund_scale_daily_szse", "fund_etf_scale_szse"} <= AKSHARE_APIS


def test_share_scales_keep_helper_units_and_label_adjacent_sessions(db_session):
    sse_calls: list[str] = []
    sz_calls: list[dict] = []

    def sse(date: str):
        sse_calls.append(date)
        shares = 1_000_000 if date == "20260901" else 1_100_000
        return [{"基金代码": "510300", "基金份额": shares, "统计日期": date, "基金简称": "沪深300"}]

    def szse(**kwargs):
        sz_calls.append(kwargs)
        start = kwargs["start_date"]
        assert kwargs["symbol"] == "ETF"
        return [
            {"基金代码": "159915", "基金份额": 2_000_000, "日期": start},
            {"基金代码": 159915, "基金份额": 1_500_000, "日期": kwargs["end_date"]},
        ]

    provider = AKShareProvider(
        Settings(_env_file=None, market_provider="akshare"),
        ak_client=SimpleNamespace(fund_etf_scale_sse=sse, fund_scale_daily_szse=szse),
    )
    instruments = [
        _instrument(db_session, ts_code, symbol, exchange)
        for ts_code, symbol, exchange in (("510300.SH", "510300", "SH"), ("159915.SZ", "159915", "SZ"))
    ]
    ids = [item.id for item in instruments]
    db_session.query(EtfShareScale).filter(EtfShareScale.instrument_id.in_(ids)).delete(synchronize_session=False)
    db_session.flush()
    result = ShareScaleService(provider, provider.settings, calendar=_Calendar()).refresh(
        db_session,
        codes=["510300.SH", "159915.SZ"],
        lookback_days=2,
        as_of=date(2026, 9, 2),
        run_id="share-scale-test",
    )
    db_session.flush()

    assert sse_calls == ["20260901", "20260902"]
    assert sz_calls[0]["symbol"] == "ETF"
    assert result["actionable"] is False
    assert result["status"] == "succeeded"
    rows = {
        row.exchange: row
        for row in db_session.query(EtfShareScale).filter(EtfShareScale.instrument_id.in_(ids)).all()
        if row.trade_date == date(2026, 9, 2)
    }
    assert rows["SH"].shares == 1_100_000
    assert rows["SH"].share_delta == 100_000
    assert rows["SH"].proxy == "份额增加"
    assert rows["SH"].day_over_day is True
    assert rows["SH"].source == "akshare:fund_etf_scale_sse"
    assert rows["SZ"].shares == 1_500_000
    assert rows["SZ"].share_delta == -500_000
    assert rows["SZ"].proxy == "份额减少"
    assert rows["SZ"].source == "akshare:fund_scale_daily_szse"

    again = ShareScaleService(provider, provider.settings, calendar=_Calendar()).refresh(
        db_session,
        codes=["510300.SH", "159915.SZ"],
        lookback_days=2,
        as_of=date(2026, 9, 2),
        run_id="share-scale-test-2",
    )
    assert again["inserted"] == 0
    assert db_session.query(EtfShareScale).filter(EtfShareScale.instrument_id.in_(ids)).count() == 4


def test_undated_szse_snapshot_is_not_stored(db_session):
    provider = AKShareProvider(
        Settings(_env_file=None, market_provider="akshare"),
        ak_client=SimpleNamespace(fund_etf_scale_szse=lambda: [{"基金代码": "159915", "基金份额": 10}]),
    )
    _instrument(db_session, "159915.SZ", "159915", "SZ")
    result = ShareScaleService(provider, provider.settings, calendar=_Calendar()).refresh(
        db_session, codes=["159915.SZ"], lookback_days=2, as_of=date(2026, 9, 2), run_id="undated",
    )
    assert result["status"] == "failed"
    assert result["reason"] == "share_scale_undated_or_unavailable"
    assert result["actionable"] is False
    assert result["inserted"] == 0
    assert db_session.query(EtfShareScale).filter(EtfShareScale.source == "akshare:fund_etf_scale_szse").count() == 0


def test_unverified_calendar_keeps_delta_but_not_the_add_reduce_label():
    points = [
        {"trade_date": date(2026, 9, 1), "shares": 100.0},
        {"trade_date": date(2026, 9, 2), "shares": 110.0},
    ]
    annotate_share_series(points, _Calendar(verified=False))
    assert points[1]["share_delta"] == 10
    assert points[1]["day_over_day"] is False
    assert points[1]["proxy"] == "不可用"


def test_mock_provider_does_not_fabricate_share_scales(db_session):
    called: list[str] = []
    before = db_session.query(EtfShareScale).count()
    provider = SimpleNamespace(name="mock", fetch_share_scales=lambda *args, **kwargs: called.append("called"))
    result = ShareScaleService(provider, Settings(_env_file=None, market_provider="mock")).refresh(
        db_session, run_id="mock-block",
    )
    assert called == []
    assert result["status"] == "skipped"
    assert result["reason"] == "mock_share_scale_blocked"
    assert result["actionable"] is False
    assert db_session.query(EtfShareScale).count() == before


def test_mock_task_skips_share_scale_refresh(db_session):
    result = TaskService().run(db_session, "refresh_share_scales")
    assert result["status"] == "skipped"
    assert result["reason"] == "mock_share_scale_blocked"
    assert result["actionable"] is False


def test_composite_uses_public_share_scale_and_does_not_call_ftshare():
    calls: list[str] = []

    def ak_fetch(codes, start, end):
        calls.append("akshare")
        return [ShareScaleRecord("510300.SH", start, 10, "akshare:fund_etf_scale_sse", "SH")]

    def ft_fetch(codes, start, end):
        calls.append("ftshare")
        raise AssertionError("FTShare must not supply share scales")

    provider = CompositeProvider([
        SimpleNamespace(name="akshare", fetch_share_scales=ak_fetch),
        SimpleNamespace(name="ftshare", fetch_share_scales=ft_fetch),
    ])
    rows = provider.fetch_share_scales(["510300.SH"], date(2026, 9, 1), date(2026, 9, 2))
    assert calls == ["akshare"]
    assert rows[0].shares == 10


def test_quote_flow_fields_are_persisted(db_session):
    when = datetime(2026, 9, 2, 14, 0, tzinfo=SHANGHAI)
    provider = SimpleNamespace(
        name="akshare",
        fetch_spot_quotes=lambda codes: [SimpleNamespace(
            ts_code=codes[0], quote_time=when, price=4.0, open=4.0, high=4.1, low=3.9,
            pre_close=3.9, pct_change=2.0, volume=100.0, amount=400.0, premium_rate=-0.4,
            source="akshare:em:v101", is_realtime=False, degraded_reason="public_quote_not_qualified",
            iopv=4.02, latest_shares=50_000.0, main_net_inflow=-10.0, super_large_net_inflow=-6.0,
            large_net_inflow=-4.0, medium_net_inflow=1.0, small_net_inflow=9.0,
            flow_contract=SPOT_FLOW_CONTRACT,
            to_dict=lambda: {"ts_code": codes[0], "price": 4.0},
        )],
    )
    instrument = _instrument(db_session, "510300.SH", "510300", "SH")
    MarketService(provider, Settings(_env_file=None, market_provider="akshare"), persist_provider_audits=False).refresh_quotes(
        db_session, codes=["510300.SH"], run_id="quote-flow",
    )
    stored = (
        db_session.query(QuoteSnapshot)
        .filter(QuoteSnapshot.instrument_id == instrument.id, QuoteSnapshot.flow_contract == SPOT_FLOW_CONTRACT)
        .order_by(QuoteSnapshot.id.desc())
        .first()
    )
    assert stored.iopv == 4.02
    assert stored.latest_shares == 50_000
    assert stored.main_net_inflow == -10
    assert stored.small_net_inflow == 9
    assert stored.premium_rate == -0.4
    assert stored.flow_contract == SPOT_FLOW_CONTRACT
    assert stored.is_realtime is False


def test_grade_keeps_technical_label_and_refuses_actionable_flow(db_session):
    instrument = Instrument(ts_code="510390.SH", symbol="510390", name="流量样本", kind="ETF", exchange="SH", enabled=True)
    db_session.add(instrument)
    db_session.flush()
    when = datetime(2026, 9, 2, 14, 0, tzinfo=SHANGHAI)
    db_session.add(QuoteSnapshot(
        instrument_id=instrument.id, quote_time=when, price=2.4, pct_change=2.0, premium_rate=-0.5,
        iopv=2.41, latest_shares=1000, main_net_inflow=20, super_large_net_inflow=5,
        large_net_inflow=15, medium_net_inflow=-3, small_net_inflow=-17,
        flow_contract=SPOT_FLOW_CONTRACT, source="akshare:em:v101", is_realtime=False,
        quality_hash="flow-grade",
    ))
    db_session.add(EtfShareScale(
        instrument_id=instrument.id, trade_date=date(2026, 9, 2), shares=900, previous_trade_date=date(2026, 9, 1),
        previous_shares=1000, share_delta=-100, share_delta_ratio=-0.1, day_over_day=True, proxy="份额减少",
        source="akshare:fund_etf_scale_sse", exchange="SH", fetched_at=when, quality_hash="scale-grade",
    ))
    db_session.add(IndicatorSnapshot(
        instrument_id=instrument.id, as_of_date=date(2026, 9, 2), version="ind-test",
        values_json={
            "close": 2.4, "ma5": 2.4, "ma10": 2.35, "ma20": 2.22, "ma30": 2.1,
            "macd_dif": 0.02, "macd_dea": 0.01, "macd_hist": 0.01,
            "kdj_k": 55, "kdj_d": 50, "kdj_j": 70, "rsi14": 55, "volume_ratio": 1.5,
            "return_1d": 0.02, "return_5d": 0.03, "td_buy_setup": 0, "td_sell_setup": 0,
        },
        technical_score=70, risk_score=30, trend_label="up", data_quality=80, input_hash="ind-flow",
    ))
    db_session.flush()
    try:
        payload = SignalGradeService(Settings(_env_file=None, market_provider="akshare")).build(db_session)
        row = next(item for item in payload["rows"] if item["ts_code"] == "510390.SH")
        assert row["grade"] == "可加仓"
        assert row["actionable"] is False
        assert row["flow_share"]["actionable"] is False
        assert row["flow_share"]["changes_grade"] is False
        assert row["flow_share"]["premium_rate"] == -0.5
        assert row["flow_share"]["main_net_inflow"] == 20
        assert row["flow_share"]["share_scale"]["proxy"] == "份额减少"
        assert row["flow_share"]["share_scale"]["share_delta"] == -100
        assert payload["flow_share_changes_grade"] is False
        assert all(item["actionable"] is False and item["flow_share"]["actionable"] is False for item in payload["rows"])
    finally:
        # This sample is inserted before the shared bootstrap. Leaving it enabled
        # makes later freshness checks read a newer mock quote against this row.
        db_session.query(EtfShareScale).filter(EtfShareScale.instrument_id == instrument.id).delete(synchronize_session=False)
        db_session.query(QuoteSnapshot).filter(QuoteSnapshot.instrument_id == instrument.id).delete(synchronize_session=False)
        db_session.query(IndicatorSnapshot).filter(IndicatorSnapshot.instrument_id == instrument.id).delete(synchronize_session=False)
        db_session.delete(instrument)
        db_session.flush()


def test_mock_grade_does_not_present_demo_premium_as_flow(db_session, bootstrapped):
    payload = SignalGradeService().build(db_session)
    assert payload["flow_share_contract"] == "etf-flow-share-v1"
    blocked = [row for row in payload["rows"] if row["flow_share"]["status"] == "mock_blocked"]
    assert blocked
    assert all(row["quote_is_mock"] for row in payload["rows"])
    assert all(row["flow_share"]["premium_rate"] is None and row["flow_share"]["actionable"] is False for row in blocked)
    assert all(row["actionable"] is False for row in payload["rows"])


def test_decision_board_surfaces_flow_without_actionable(db_session, bootstrapped):
    instrument = db_session.query(Instrument).filter(Instrument.ts_code == "510300.SH").one()
    when = datetime.now(SHANGHAI) + timedelta(days=1)
    db_session.add(QuoteSnapshot(
        instrument_id=instrument.id, quote_time=when, price=4.2, pct_change=0.2, premium_rate=0.15,
        iopv=4.19, latest_shares=8_000_000, main_net_inflow=42, super_large_net_inflow=20,
        large_net_inflow=22, medium_net_inflow=-10, small_net_inflow=-32,
        flow_contract=SPOT_FLOW_CONTRACT, source="akshare:em:v101", is_realtime=False,
        degraded_reason="public_quote_not_qualified", quality_hash="board-flow",
    ))
    db_session.add(EtfShareScale(
        instrument_id=instrument.id, trade_date=when.date(), shares=8_000_000,
        previous_trade_date=when.date() - timedelta(days=1), previous_shares=7_900_000,
        share_delta=100_000, share_delta_ratio=100_000 / 7_900_000, day_over_day=True, proxy="份额增加",
        source="akshare:fund_etf_scale_sse", exchange="SH", fetched_at=when, quality_hash="board-scale",
    ))
    db_session.flush()
    built = DecisionBoardService().refresh(db_session, generated_at=when)
    try:
        payload = built.payload
        row = next(item for item in payload["rows"] if item["ts_code"] == "510300.SH")
        assert payload["flow_share_changes_grade"] is False
        assert row["actionable"] is False
        assert row["flow_share"]["actionable"] is False
        assert row["flow_share"]["changes_grade"] is False
        assert row["flow_share"]["iopv"] == 4.19
        assert row["flow_share"]["latest_shares"] == 8_000_000
        assert row["flow_share"]["share_scale"]["proxy"] == "份额增加"
        assert row["flow_share"]["share_scale"]["day_over_day"] is True
        assert all(item["actionable"] is False for item in payload["rows"])
    finally:
        # Session DB is shared. A future quote or snapshot becomes the latest row
        # and breaks later decision-board freshness and retention checks.
        db_session.query(QuoteSnapshot).filter(QuoteSnapshot.quality_hash == "board-flow").delete(synchronize_session=False)
        db_session.query(EtfShareScale).filter(EtfShareScale.quality_hash == "board-scale").delete(synchronize_session=False)
        db_session.query(DecisionBoardSnapshot).filter(
            DecisionBoardSnapshot.snapshot_id == built.snapshot.snapshot_id
        ).delete(synchronize_session=False)
        db_session.flush()


def test_duplicate_share_rows_are_rejected():
    provider = AKShareProvider(
        Settings(_env_file=None, market_provider="akshare"),
        ak_client=SimpleNamespace(fund_etf_scale_sse=lambda date: [
            {"基金代码": "510300", "基金份额": 1, "统计日期": date},
            {"基金代码": "510300", "基金份额": 2, "统计日期": date},
        ]),
    )
    with pytest.raises(ProviderError, match="share_scale_duplicate_conflict"):
        provider.fetch_share_scales(["510300.SH"], date(2026, 9, 2), date(2026, 9, 2))


def test_missing_share_endpoint_is_unavailable():
    provider = AKShareProvider(Settings(_env_file=None, market_provider="akshare"), ak_client=SimpleNamespace())
    with pytest.raises(CapabilityUnavailable):
        provider.fetch_share_scales(["510300.SH"], date(2026, 9, 1), date(2026, 9, 2))


def test_mock_quote_view_does_not_keep_a_synthetic_premium():
    view = build_flow_share_view(SimpleNamespace(source="mock", premium_rate=1.2, iopv=1), None)
    assert view["status"] == "mock_blocked"
    assert view["premium_rate"] is None
    assert view["actionable"] is False

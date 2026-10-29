"""HS300 passive-holder share of float market cap: research-only snapshot.

The ratio is Σ(HS300-tracking ETF value) / Σ(HS300 constituent 流通市值).
Every dataset is a free public snapshot. The Eastmoney market-cap endpoint
carries no upstream trade date, so it can only be used same-day after the
close; these tests pin that contract instead of assuming backfill.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from app.core.config import Settings
from app.models import DailyBar, EtfShareScale, Hs300PassiveRatioSnapshot, Instrument
from app.providers.akshare import AKShareProvider
from app.providers.base import CapabilityUnavailable
from app.providers.bounded_sdk import AKSHARE_APIS
from app.providers.composite import CompositeProvider
from app.providers.types import (
    FundNavRecord,
    IndexConstituentRecord,
    StockMarketCapRecord,
    StockMarketCapSnapshot,
)
from app.services.hs300_ratio import universe_hash
from app.services.hs300_ratio_service import Hs300RatioService
from app.services.task_service import TaskService

SHANGHAI = ZoneInfo("Asia/Shanghai")
POST_CLOSE = datetime(2026, 10, 29, 15, 30, tzinfo=SHANGHAI)
AS_OF = date(2026, 10, 29)
INDEX = "000300.SH"
FUNDS = ("512999.SH", "159999.SZ")


def _constituents() -> list[IndexConstituentRecord]:
    return [
        IndexConstituentRecord(ts_code="600000.SH", index_code=INDEX, as_of=date(2026, 6, 30),
                               name="浦发银行", exchange="SH", source="akshare:index_stock_cons_csindex"),
        IndexConstituentRecord(ts_code="000001.SZ", index_code=INDEX, as_of=date(2026, 6, 30),
                               name="平安银行", exchange="SZ", source="akshare:index_stock_cons_csindex"),
        IndexConstituentRecord(ts_code="300001.SZ", index_code=INDEX, as_of=date(2026, 6, 30),
                               name="特锐德", exchange="SZ", source="akshare:index_stock_cons_csindex"),
    ]


def _caps() -> list[StockMarketCapRecord]:
    return [
        StockMarketCapRecord(ts_code="600000.SH", total_mv=500_000_000.0, float_mv=400_000_000.0,
                             name="浦发银行", source="akshare:stock_zh_a_spot_em"),
        StockMarketCapRecord(ts_code="000001.SZ", total_mv=400_000_000.0, float_mv=300_000_000.0,
                             name="平安银行", source="akshare:stock_zh_a_spot_em"),
        StockMarketCapRecord(ts_code="300001.SZ", total_mv=350_000_000.0, float_mv=300_000_000.0,
                             name="特锐德", source="akshare:stock_zh_a_spot_em"),
    ]


def _navs() -> list[FundNavRecord]:
    return [
        FundNavRecord(ts_code="512999.SH", nav_date=date(2026, 10, 28), nav=4.05,
                      source="akshare:fund_etf_fund_daily_em"),
        FundNavRecord(ts_code="159999.SZ", nav_date=date(2026, 10, 28), nav=2.02,
                      source="akshare:fund_etf_fund_daily_em"),
    ]


class _RatioProvider:
    name = "akshare"

    def __init__(self, *, observed_at=POST_CLOSE, constituents=None, caps=None, navs=None):
        self.observed_at = observed_at
        self.constituents = _constituents() if constituents is None else constituents
        self.caps = _caps() if caps is None else caps
        self.navs = _navs() if navs is None else navs
        self.calls: list[str] = []

    def fetch_index_constituents(self, index_code: str):
        self.calls.append("constituents")
        if isinstance(self.constituents, Exception):
            raise self.constituents
        return self.constituents

    def fetch_stock_float_market_caps(self):
        self.calls.append("caps")
        if isinstance(self.caps, Exception):
            raise self.caps
        return StockMarketCapSnapshot(
            observed_at=self.observed_at, source="akshare:stock_zh_a_spot_em", rows=self.caps,
        )

    def fetch_etf_nav_snapshot(self):
        self.calls.append("navs")
        if isinstance(self.navs, Exception):
            raise self.navs
        return self.navs


def _write_universe(tmp_path, *, status="confirmed", funds=FUNDS, declared_hash="auto"):
    payload = {
        "index_code": INDEX,
        "index_name": "沪深300",
        "status": status,
        "funds": list(funds),
        "universe_hash": universe_hash(INDEX, list(funds)) if declared_hash == "auto" else declared_hash,
    }
    path = tmp_path / "hs300_etf_universe.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _settings(tmp_path, **kwargs):
    return Settings(
        _env_file=None,
        market_provider=kwargs.pop("market_provider", "akshare"),
        hs300_universe_path=_write_universe(tmp_path, **kwargs),
    )


def _seed(db, *, shares=(1_000_000.0, 500_000.0), closes=(4.0, 2.0)):
    created: list[int] = []
    for index, code in enumerate(FUNDS):
        row = db.query(Instrument).filter(Instrument.ts_code == code).one_or_none()
        if row is None:
            row = Instrument(ts_code=code, symbol=code.split(".")[0], name=code,
                             kind="ETF", exchange=code.split(".")[1], enabled=True)
            db.add(row)
            db.flush()
            created.append(row.id)
        if shares is not None:
            db.add(EtfShareScale(
                instrument_id=row.id, trade_date=AS_OF, shares=shares[index],
                previous_trade_date=None, previous_shares=None, share_delta=None,
                share_delta_ratio=None, day_over_day=False, proxy="不可用",
                source="akshare:fund_etf_scale_sse" if code.endswith(".SH") else "akshare:fund_scale_daily_szse",
                exchange=code.split(".")[1], fetched_at=POST_CLOSE,
                quality_hash=f"ratio-share-{code}",
            ))
        if closes is not None:
            db.add(DailyBar(
                instrument_id=row.id, trade_date=AS_OF, open=closes[index], high=closes[index],
                low=closes[index], close=closes[index], adjust="none", source="test",
                quality_hash=f"ratio-bar-{code}",
            ))
    db.flush()
    return created


def _cleanup(db, created: list[int]) -> None:
    db.query(Hs300PassiveRatioSnapshot).filter(
        Hs300PassiveRatioSnapshot.trade_date == AS_OF
    ).delete(synchronize_session=False)
    if created:
        db.query(EtfShareScale).filter(EtfShareScale.instrument_id.in_(created)).delete(synchronize_session=False)
        db.query(DailyBar).filter(DailyBar.instrument_id.in_(created)).delete(synchronize_session=False)
        db.query(Instrument).filter(Instrument.id.in_(created)).delete(synchronize_session=False)
    db.flush()


def _snapshot_count(db) -> int:
    return db.query(Hs300PassiveRatioSnapshot).filter(
        Hs300PassiveRatioSnapshot.trade_date == AS_OF).count()


def test_allowlist_covers_constituent_and_fund_nav_helpers():
    assert {"index_stock_cons_csindex", "fund_etf_fund_daily_em"} <= AKSHARE_APIS


def test_akshare_parses_official_hs300_constituents():
    def cons(symbol: str):
        assert symbol == "000300"
        return [
            {"日期": "20260630", "指数代码": "000300", "成分券代码": "600000",
             "成分券名称": "浦发银行", "交易所": "上海证券交易所"},
            {"日期": "20260630", "指数代码": "000300", "成分券代码": "000001",
             "成分券名称": "平安银行", "交易所": "深圳证券交易所"},
        ]

    provider = AKShareProvider(Settings(_env_file=None), ak_client=SimpleNamespace(index_stock_cons_csindex=cons))
    rows = provider.fetch_index_constituents(INDEX)

    assert [row.ts_code for row in rows] == ["600000.SH", "000001.SZ"]
    assert rows[0].index_code == INDEX
    assert rows[0].as_of == date(2026, 6, 30)
    assert {row.exchange for row in rows} == {"SH", "SZ"}


def test_akshare_keeps_market_cap_units_and_stamps_the_snapshot():
    def spot():
        return [{"代码": "600000", "名称": "浦发银行", "总市值": 300_000_000_000, "流通市值": 250_000_000_000},
                {"代码": "000001", "名称": "平安银行", "总市值": 200_000_000_000, "流通市值": None}]

    provider = AKShareProvider(Settings(_env_file=None), ak_client=SimpleNamespace(stock_zh_a_spot_em=spot))
    snapshot = provider.fetch_stock_float_market_caps()

    assert snapshot.source == "akshare:stock_zh_a_spot_em"
    assert snapshot.observed_at.tzinfo is not None
    assert len(snapshot) == 1
    row = snapshot.rows[0]
    assert row.ts_code == "600000.SH"
    assert row.float_mv == 250_000_000_000
    assert row.total_mv == 300_000_000_000


def test_akshare_reads_the_latest_dated_nav_columns():
    def daily():
        return [{
            "基金代码": "512999", "基金简称": "沪深300ETF", "类型": "ETF",
            "2026-10-28-单位净值": 4.05, "2026-10-28-累计净值": 4.05,
            "2026-10-27-单位净值": 4.01, "2026-10-27-累计净值": 4.01,
            "增长值": 0.04, "增长率": 1.0, "市价": 4.04, "折价率": 0.1,
        }]

    provider = AKShareProvider(Settings(_env_file=None), ak_client=SimpleNamespace(fund_etf_fund_daily_em=daily))
    rows = provider.fetch_etf_nav_snapshot()

    assert len(rows) == 1
    assert rows[0].ts_code == "512999.SH"
    assert rows[0].nav_date == date(2026, 10, 28)
    assert rows[0].nav == 4.05


def test_akshare_enumerates_the_etf_catalog_for_owner_review():
    def spot():
        return [{"代码": "510300", "名称": "沪深300ETF"},
                {"代码": "159919", "名称": "沪深300ETF"},
                {"代码": "510300", "名称": "沪深300ETF"}]

    provider = AKShareProvider(Settings(_env_file=None), ak_client=SimpleNamespace(fund_etf_spot_em=spot))
    rows = provider.fetch_etf_catalog()

    assert [row.ts_code for row in rows] == ["510300.SH", "159919.SZ"]
    assert rows[0].name == "沪深300ETF"
    assert rows[0].kind == "ETF"


def test_missing_public_endpoints_are_capability_unavailable():
    provider = AKShareProvider(Settings(_env_file=None), ak_client=SimpleNamespace())
    with pytest.raises(CapabilityUnavailable):
        provider.fetch_index_constituents(INDEX)
    with pytest.raises(CapabilityUnavailable):
        provider.fetch_stock_float_market_caps()
    with pytest.raises(CapabilityUnavailable):
        provider.fetch_etf_nav_snapshot()


def test_composite_delegates_ratio_capabilities():
    snapshot = StockMarketCapSnapshot(observed_at=POST_CLOSE, source="akshare:stock_zh_a_spot_em", rows=_caps())
    provider = CompositeProvider([SimpleNamespace(
        name="akshare",
        fetch_index_constituents=lambda code: _constituents(),
        fetch_stock_float_market_caps=lambda: snapshot,
        fetch_etf_nav_snapshot=lambda: _navs(),
        fetch_etf_catalog=lambda: [SimpleNamespace(ts_code="510300.SH", symbol="510300", name="沪深300ETF")],
    )])

    assert provider.fetch_index_constituents(INDEX)[0].ts_code == "600000.SH"
    assert len(provider.fetch_stock_float_market_caps()) == 3
    assert provider.fetch_etf_nav_snapshot()[0].nav == 4.05
    assert provider.fetch_etf_catalog()[0].ts_code == "510300.SH"


def test_provisional_universe_refuses_before_any_fetch(db_session, tmp_path):
    provider = _RatioProvider()
    service = Hs300RatioService(provider, _settings(tmp_path, status="provisional"))

    result = service.refresh(db_session, as_of=AS_OF, run_id="ratio-provisional")

    assert result["status"] == "skipped"
    assert result["ratio_status"] == "unavailable"
    assert result["reason"] == "universe_not_confirmed"
    assert result["actionable"] is False
    assert provider.calls == []
    assert _snapshot_count(db_session) == 0


def test_confirmed_universe_computes_both_numerator_bases(db_session, tmp_path):
    created = _seed(db_session)
    provider = _RatioProvider()
    service = Hs300RatioService(provider, _settings(tmp_path))
    try:
        result = service.refresh(db_session, as_of=AS_OF, run_id="ratio-both")

        assert result["status"] == "succeeded"
        assert result["ratio_status"] == "computed"
        assert result["actionable"] is False
        assert result["research_only"] is True
        assert result["changes_grade"] is False
        assert result["qualification"] == "UNKNOWN"
        assert result["calibration_status"] == "not_calibrated"
        assert result["fund_count"] == 2
        assert result["constituent_count"] == 3
        close_basis = result["bases"]["market_value_at_close"]
        nav_basis = result["bases"]["aum_at_nav"]
        assert close_basis["numerator"] == pytest.approx(5_000_000.0)
        assert close_basis["denominator"] == pytest.approx(1_000_000_000.0)
        assert close_basis["ratio"] == pytest.approx(0.005)
        assert close_basis["lag_days"] == 0
        assert nav_basis["numerator"] == pytest.approx(5_060_000.0)
        assert nav_basis["ratio"] == pytest.approx(0.00506)
        assert nav_basis["lag_days"] == 1

        rows = db_session.query(Hs300PassiveRatioSnapshot).filter(
            Hs300PassiveRatioSnapshot.trade_date == AS_OF).all()
        assert {row.numerator_basis for row in rows} == {"market_value_at_close", "aum_at_nav"}
        assert all(row.basis == "float_market_cap" and row.index_code == INDEX for row in rows)
        assert all(row.universe_hash == universe_hash(INDEX, list(FUNDS)) for row in rows)

        again = service.refresh(db_session, as_of=AS_OF, run_id="ratio-both-2")
        assert again["inserted"] == 0
        assert again["unchanged"] == 2
        assert _snapshot_count(db_session) == 2
    finally:
        _cleanup(db_session, created)


def test_incomplete_constituent_coverage_refuses_the_ratio(db_session, tmp_path):
    created = _seed(db_session)
    provider = _RatioProvider(caps=_caps()[:2])
    service = Hs300RatioService(provider, _settings(tmp_path))
    try:
        result = service.refresh(db_session, as_of=AS_OF, run_id="ratio-coverage")

        assert result["status"] == "failed"
        assert result["ratio_status"] == "unavailable"
        assert result["reason"] == "constituent_coverage_incomplete"
        assert result["missing_constituents"] == 1
        assert result["bases"] == {}
        assert _snapshot_count(db_session) == 0
    finally:
        _cleanup(db_session, created)


def test_snapshot_from_another_day_is_not_backfilled(db_session, tmp_path):
    created = _seed(db_session)
    provider = _RatioProvider(observed_at=datetime(2026, 10, 28, 15, 30, tzinfo=SHANGHAI))
    service = Hs300RatioService(provider, _settings(tmp_path))
    try:
        result = service.refresh(db_session, as_of=AS_OF, run_id="ratio-backfill")
        assert result["status"] == "failed"
        assert result["reason"] == "snapshot_not_as_of"
        assert result["ratio_status"] == "unavailable"
    finally:
        _cleanup(db_session, created)


def test_intraday_snapshot_is_refused(db_session, tmp_path):
    created = _seed(db_session)
    provider = _RatioProvider(observed_at=datetime(2026, 10, 29, 14, 0, tzinfo=SHANGHAI))
    service = Hs300RatioService(provider, _settings(tmp_path))
    try:
        result = service.refresh(db_session, as_of=AS_OF, run_id="ratio-intraday")
        assert result["status"] == "failed"
        assert result["reason"] == "snapshot_before_close"
    finally:
        _cleanup(db_session, created)


def test_missing_share_rows_block_both_bases(db_session, tmp_path):
    created = _seed(db_session, shares=None)
    provider = _RatioProvider()
    service = Hs300RatioService(provider, _settings(tmp_path))
    try:
        result = service.refresh(db_session, as_of=AS_OF, run_id="ratio-no-shares")
        assert result["status"] == "failed"
        assert result["reason"] == "fund_shares_missing"
        assert result["missing_funds"] == 2
        assert _snapshot_count(db_session) == 0
    finally:
        _cleanup(db_session, created)


def test_missing_close_keeps_only_the_nav_basis(db_session, tmp_path):
    created = _seed(db_session, closes=None)
    provider = _RatioProvider()
    service = Hs300RatioService(provider, _settings(tmp_path))
    try:
        result = service.refresh(db_session, as_of=AS_OF, run_id="ratio-no-close")
        assert result["status"] == "partial"
        assert result["ratio_status"] == "computed"
        assert result["unavailable_reasons"]["market_value_at_close"] == "fund_close_missing"
        assert result["bases"]["aum_at_nav"]["ratio"] == pytest.approx(0.00506)
        assert result["actionable"] is False
        assert _snapshot_count(db_session) == 1
    finally:
        _cleanup(db_session, created)


def test_implausible_ratio_is_rejected_instead_of_stored(db_session, tmp_path):
    created = _seed(db_session, shares=(100_000_000.0, 100_000_000.0))
    provider = _RatioProvider()
    service = Hs300RatioService(provider, _settings(tmp_path))
    try:
        result = service.refresh(db_session, as_of=AS_OF, run_id="ratio-bounds")
        assert result["status"] == "failed"
        assert result["reason"] == "ratio_out_of_bounds"
        assert result["bases"] == {}
        assert _snapshot_count(db_session) == 0
    finally:
        _cleanup(db_session, created)


def test_universe_hash_mismatch_refuses_the_frozen_list(db_session, tmp_path):
    provider = _RatioProvider()
    service = Hs300RatioService(provider, _settings(tmp_path, declared_hash="0" * 64))

    result = service.refresh(db_session, as_of=AS_OF, run_id="ratio-hash")

    assert result["status"] == "skipped"
    assert result["reason"] == "universe_hash_mismatch"
    assert provider.calls == []


def test_mock_provider_never_produces_a_ratio(db_session, tmp_path):
    provider = SimpleNamespace(name="mock", fetch_index_constituents=lambda code: _constituents())
    result = Hs300RatioService(provider, _settings(tmp_path)).refresh(db_session, as_of=AS_OF, run_id="ratio-mock")

    assert result["status"] == "skipped"
    assert result["reason"] == "mock_ratio_blocked"
    assert result["actionable"] is False
    assert _snapshot_count(db_session) == 0


def test_task_registry_exposes_the_ratio_refresh():
    assert "refresh_hs300_ratio" in TaskService().task_names


def test_mock_task_skips_the_ratio_refresh(db_session):
    result = TaskService().run(db_session, "refresh_hs300_ratio")
    assert result["status"] == "skipped"
    assert result["reason"] == "mock_ratio_blocked"
    assert result["actionable"] is False

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import IndicatorSnapshot, Instrument, NewsItem, SignalSnapshot
from app.services.holding_service import HoldingService
from app.services.signal_center_service import (
    OPPORTUNITY_STATES,
    RISK_STATES,
    SignalCenterService,
)

STRATEGY_VERSION = "signal-v0.4.0"
INDICATOR_VERSION = "indicator-v0.2.0"


def _indicator_values(**overrides) -> dict:
    values = {
        "close": 1.0,
        "ma5": 1.0,
        "ma10": 1.0,
        "ma20": 1.0,
        "ma30": 1.0,
        "ma60": 1.0,
        "macd_dif": 0.0,
        "macd_dea": 0.0,
        "macd_hist": 0.0,
        "kdj_k": 50.0,
        "kdj_d": 50.0,
        "kdj_j": 50.0,
        "rsi6": 50.0,
        "rsi12": 50.0,
        "rsi14": 50.0,
        "atr": 0.0,
        "atr_pct": 1.0,
        "boll_mid": 1.0,
        "boll_upper": 1.1,
        "boll_lower": 0.9,
        "volume_ratio": 1.0,
        "return_1d": 0.0,
        "return_5d": 0.0,
        "return_20d": 0.0,
        "return_60d": 0.0,
        "volatility_20d": 0.2,
        "drawdown_60d": 0.0,
        "td_buy_setup": 0,
        "td_sell_setup": 0,
        "technical_reasons": [],
    }
    values.update(overrides)
    return values


def _attach(
    db,
    instrument: Instrument,
    *,
    when: datetime,
    state: str,
    score: float,
    values: dict,
    technical: float = 60.0,
    risk: float = 40.0,
) -> None:
    stamp = when.strftime("%Y%m%d%H%M")
    db.flush()  # session autoflush=False，先落盘同事务已挂起行
    existing = db.scalar(
        select(IndicatorSnapshot).where(
            IndicatorSnapshot.instrument_id == instrument.id,
            IndicatorSnapshot.as_of_date == when.date(),
            IndicatorSnapshot.version == INDICATOR_VERSION,
        )
    )
    if existing is None:
        db.add(
            IndicatorSnapshot(
                instrument_id=instrument.id,
                as_of_date=when.date(),
                version=INDICATOR_VERSION,
                values_json=values,
                technical_score=technical,
                risk_score=risk,
                trend_label="震荡",
                data_quality=90.0,
                input_hash=f"it-{instrument.ts_code}-{stamp}",
            )
        )
    db.add(
        SignalSnapshot(
            instrument_id=instrument.id,
            as_of_time=when,
            strategy_version=STRATEGY_VERSION,
            indicator_version=INDICATOR_VERSION,
            forecast_version="similarity-v0.2.0",
            state=state,
            score=score,
            confidence=60.0,
            target_weight=None,
            first_step_target_weight=None,
            reasons_json=[],
            risks_json=[],
            evidence_json={},
            input_hash=f"sig-{instrument.ts_code}-{stamp}",
            expires_at=when + timedelta(hours=2),
            is_actionable=False,
            data_quality=90.0,
        )
    )


def _instrument(db, ts_code: str) -> Instrument:
    return db.scalar(select(Instrument).where(Instrument.ts_code == ts_code))


def test_constants_and_states_are_exposed():
    assert "可入场" in OPPORTUNITY_STATES and "可试探" in OPPORTUNITY_STATES
    assert "减仓" in RISK_STATES and "风险观察" in RISK_STATES


def test_summary_fronts_and_research_only_flag(bootstrapped, db_session):
    payload = SignalCenterService().build(db_session)
    assert payload["version"].startswith("signal-center-")
    assert payload["coefficient"] == 1.0
    assert payload["research_only"] is True  # 测试环境为 mock 数据源

    total = len({row.instrument_id for row in db_session.scalars(select(SignalSnapshot)).all()})
    summary = payload["summary"]
    assert summary["total"] == total
    assert summary["opportunity"] == len(payload["fronts"]["opportunity"])
    assert summary["risk"] >= len(payload["fronts"]["risk"])  # 前排只取前 N
    assert summary["take_profit"] >= len(payload["fronts"]["take_profit"])

    entry, reduce_line = 68.0, 38.0
    for item in payload["fronts"]["opportunity"]:
        assert item["category"] == "opportunity"
        assert item["state"] in OPPORTUNITY_STATES or item["effective_score"] >= entry
    for item in payload["fronts"]["risk"]:
        assert item["category"] == "risk"
        assert item["state"] in RISK_STATES or item["effective_score"] < reduce_line
    for item in payload["fronts"]["take_profit"]:
        assert item["category"] == "take_profit"
        assert (item["return_20d"] or 0) > 0


def test_coefficient_is_monotonic_for_opportunity(bootstrapped, db_session):
    counts = []
    for coefficient in (0.5, 1.0, 1.5):
        payload = SignalCenterService().build(db_session, coefficient=coefficient)
        counts.append(payload["summary"]["opportunity"])
    assert counts[0] <= counts[1] <= counts[2]


def test_curve_uses_latest_snapshot_per_instrument_per_day(bootstrapped, db_session):
    instrument = _instrument(db_session, "510300.SH")
    base = datetime(2026, 8, 20, 15, 0)
    _attach(db_session, instrument, when=base, state="可入场", score=72.0, values=_indicator_values())
    _attach(
        db_session,
        instrument,
        when=base + timedelta(hours=1),
        state="风险观察",
        score=30.0,
        values=_indicator_values(),
    )
    _attach(
        db_session,
        instrument,
        when=base + timedelta(days=1),
        state="观察",
        score=65.0,
        values=_indicator_values(),
    )
    db_session.flush()

    payload = SignalCenterService().build(db_session, days=10)
    curve = {point["date"]: point for point in payload["curve"]}
    day1 = base.date().isoformat()
    day2 = (base + timedelta(days=1)).date().isoformat()
    assert day1 in curve and day2 in curve
    # 同日两条快照时，较晚一条（风险观察）生效
    assert curve[day1]["risk"] == 1 and curve[day1]["opportunity"] == 0
    assert curve[day1]["total"] >= 1
    # 系数 1.0 时 65 分不构成机会
    assert curve[day2]["opportunity"] == 0

    boosted = SignalCenterService().build(db_session, coefficient=1.2, days=10)
    boosted_curve = {point["date"]: point for point in boosted["curve"]}
    assert boosted_curve[day2]["opportunity"] == 1  # 65 × 1.2 = 78 ≥ 68


def test_take_profit_front_ranks_overheated_instruments(bootstrapped, db_session):
    hot = _instrument(db_session, "512170.SH")
    cold = _instrument(db_session, "518880.SH")
    when = datetime.now() + timedelta(days=1)
    _attach(
        db_session,
        hot,
        when=when,
        state="持有",
        score=60.0,
        values=_indicator_values(return_20d=0.28, return_5d=0.08, rsi14=76.0),
        technical=72.0,
    )
    _attach(
        db_session,
        cold,
        when=when,
        state="持有",
        score=60.0,
        values=_indicator_values(return_20d=0.02, return_5d=0.01, rsi14=45.0),
    )
    db_session.flush()

    payload = SignalCenterService().build(db_session, days=10)
    codes = [item["ts_code"] for item in payload["fronts"]["take_profit"]]
    assert "512170.SH" in codes
    assert "518880.SH" not in codes
    item = next(i for i in payload["fronts"]["take_profit"] if i["ts_code"] == "512170.SH")
    assert item["heat"] is not None and item["heat"] > 0.6


def test_sector_strength_ranking_with_news_component(bootstrapped, db_session):
    when = datetime.now() + timedelta(days=2)
    medicine = _instrument(db_session, "512170.SH")
    _attach(
        db_session,
        medicine,
        when=when,
        state="持有",
        score=60.0,
        values=_indicator_values(
            return_20d=0.25, return_5d=0.06, return_60d=0.30, close=1.30, ma20=1.10
        ),
        technical=88.0,
        risk=30.0,
    )
    for ts_code in ("510300.SH", "510500.SH"):
        instrument = _instrument(db_session, ts_code)
        _attach(
            db_session,
            instrument,
            when=when,
            state="观察",
            score=50.0,
            values=_indicator_values(
                return_20d=-0.12, return_5d=-0.03, return_60d=-0.05, close=0.95, ma20=1.05
            ),
            technical=28.0,
            risk=62.0,
        )
    published = datetime.now() - timedelta(hours=1)
    db_session.add(
        NewsItem(
            source="test",
            source_id="signal-center-sector-1",
            title="医药板块获得政策利好支持",
            published_at=published,
            affected_themes_json=["医药"],
            impact_direction="positive",
            impact_score=0.8,
            quality_hash="signal-center-sector-news",
        )
    )
    db_session.flush()

    payload = SignalCenterService().build(db_session, days=5)
    sectors = payload["sectors"]
    assert sectors, "板块强度列表不应为空"
    assert sectors[0]["theme_l1"] == "医药"
    top = sectors[0]
    assert 0.0 <= top["strength"] <= 100.0
    assert any(member["ts_code"] == "512170.SH" for member in top["members"])
    broad = next(s for s in sectors if s["theme_l1"] == "宽基")
    assert broad["strength"] < top["strength"]
    # 每个有指标的板块都有强度分（新闻缺失时权重归一化）
    for sector in sectors:
        assert sector["members"]
        assert 0.0 <= sector["strength"] <= 100.0
        assert sector["rank"] == sectors.index(sector) + 1


def test_in_account_flag_for_held_instruments(bootstrapped, db_session):
    instrument = _instrument(db_session, "512170.SH")
    when = datetime.now() + timedelta(days=3)
    _attach(
        db_session,
        instrument,
        when=when,
        state="可入场",
        score=75.0,
        values=_indicator_values(return_20d=0.30, return_5d=0.10, rsi14=80.0),
        technical=80.0,
    )
    db_session.flush()
    HoldingService().upsert(db_session, ts_code="512170.SH", shares=1000, cost_price=1.0)
    db_session.flush()

    payload = SignalCenterService().build(db_session, days=10)
    items = [
        item
        for front in payload["fronts"].values()
        for item in front
        if item["ts_code"] == "512170.SH"
    ]
    assert items, "强信号 + 高热度标的应至少出现在一个前排"
    assert all(item["in_account"] for item in items)
    assert items[0]["holding"] is not None


def test_signal_center_api_and_settings(bootstrapped):
    with TestClient(app) as client:
        response = client.get("/api/signals/center")
        assert response.status_code == 200
        payload = response.json()
        for key in ("version", "coefficient", "research_only", "summary", "curve", "sectors", "fronts"):
            assert key in payload
        assert set(payload["fronts"]) == {"opportunity", "risk", "take_profit"}

        preview = client.get("/api/signals/center", params={"coefficient": 1.3})
        assert preview.status_code == 200
        assert preview.json()["coefficient"] == 1.3

        saved = client.put("/api/settings", json={"signal_center_coefficient": 1.2})
        assert saved.status_code == 200
        assert saved.json()["signal_center_coefficient"] == 1.2

        rejected = client.put("/api/settings", json={"signal_center_coefficient": 3.0})
        assert rejected.status_code == 422

        persisted = client.get("/api/signals/center")
        assert persisted.json()["coefficient"] == 1.2

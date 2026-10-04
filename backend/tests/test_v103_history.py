from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.models import DailyBar, IndicatorSnapshot, Instrument, MarketBar
from app.services.indicator_service import IndicatorService
from app.workspace.read_model import chart_data, instrument_detail
from sqlalchemy import select


def _unused_59_code(db) -> str:
    occupied = set(
        db.scalars(select(Instrument.ts_code).where(Instrument.ts_code.like("59%.SH"))).all()
    )
    code = next(
        (f"{value:06d}.SH" for value in range(590000, 600000) if f"{value:06d}.SH" not in occupied),
        None,
    )
    assert code is not None
    return code


def instrument(db, missing_volume=False, legacy=False):
    code = _unused_59_code(db)
    inst = Instrument(ts_code=code, symbol=code[:6], name='history test', kind='ETF', enabled=True)
    db.add(inst)
    db.flush()
    for i in range(80):
        price = 2 + i * .01
        db.add(DailyBar(instrument_id=inst.id, trade_date=date(2025,1,1)+timedelta(days=i),
            open=price, high=price+.1, low=price-.1, close=price+.02,
            volume=None if missing_volume else 1000, amount=None if missing_volume else 2000,
            source='akshare' if legacy else 'akshare:sina:v101' if missing_volume else 'akshare:em:v101'  # synthetic rows exercising the documented EM contract
            ,
            adjust='none', quality_hash=str(i)))
    db.flush()
    return inst


def test_missing_volume_does_not_block_price_chart_or_detail(db_session):
    db = db_session
    inst = instrument(db, missing_volume=True)
    settings = get_settings().model_copy(update={'market_provider':'akshare'})
    result = chart_data(db,settings,inst.ts_code,'1d',100)
    assert result['bars'][-1]['indicators']['macd_dif'] is not None
    detail = instrument_detail(db,settings,inst.ts_code,None)
    assert detail['indicator_values']['macd_dif'] is not None
    assert detail['quote']['price'] == pytest.approx(2.81)
    assert detail['quote']['status'] == 'historical_close'
    assert detail['actionable'] is False
    assert detail['forecasts'] == {}
    assert detail['availability']['price']['status'] == 'available'
    assert detail['availability']['volume']['reason_code'] == 'volume_missing_or_unverified'
    assert result['bars'][-1]['volume'] is None
    db.rollback()


def test_intraday_provisional_updates_daily_chart_indicator_series(db_session):
    inst = instrument(db_session)
    settings = get_settings().model_copy(update={'market_provider':'akshare'})
    from app.services.decision_board_service import DecisionBoardService
    observed = datetime.now(settings.timezone).replace(second=0, microsecond=0)
    DecisionBoardService(settings).record_provisional_input(
        db_session, ts_code=inst.ts_code, observed_at=observed,
        source='fixture:intraday', timestamp_verified=False,
        open_price=2.8, high_price=2.9, low_price=2.7, last_price=2.85,
        volume=1200, amount=3420, pct_change_percent_points=0.5,
    )

    result = chart_data(db_session, settings, inst.ts_code, '1d', 100, as_of=observed)

    assert result['bars'][-1]['is_provisional'] is True
    assert result['bars'][-1]['date'].startswith(observed.date().isoformat())
    assert result['bars'][-1]['indicators']['macd_dif'] is not None
    assert result['source_as_of'].startswith(observed.date().isoformat())
    assert result['as_of'] == observed.isoformat()
    assert datetime.fromisoformat(result['computed_at']).tzinfo is not None
    assert datetime.fromisoformat(result['computed_at']) >= observed
    assert '盘中指标' in result['indicator_note']


def test_chart_read_as_of_excludes_later_persisted_daily_bars(db_session):
    from zoneinfo import ZoneInfo

    inst = instrument(db_session)
    settings = get_settings().model_copy(update={'market_provider':'akshare'})
    as_of = datetime(2025, 2, 1, 15, 15, tzinfo=ZoneInfo('Asia/Shanghai'))

    result = chart_data(db_session, settings, inst.ts_code, '1d', 200, as_of=as_of)

    assert result['bars'][-1]['date'] == as_of.date().isoformat()
    assert all(bar['date'][:10] <= as_of.date().isoformat() for bar in result['bars'])
    db_session.rollback()


def test_minute_chart_read_as_of_excludes_later_persisted_bars(db_session):
    from zoneinfo import ZoneInfo

    inst = instrument(db_session)
    settings = get_settings().model_copy(update={'market_provider':'akshare'})
    as_of = datetime(2026, 9, 23, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    for bar_time in (as_of - timedelta(minutes=1), as_of + timedelta(minutes=1)):
        db_session.add(MarketBar(
            instrument_id=inst.id, interval='30m', bar_time=bar_time,
            open=2.0, high=2.1, low=1.9, close=2.0, volume=100, amount=200,
            source='fixture:intraday', source_timestamp=bar_time, timestamp_verified=True,
        ))
    db_session.flush()

    result = chart_data(db_session, settings, inst.ts_code, '30m', 100, as_of=as_of)

    assert len(result['bars']) == 1
    assert datetime.fromisoformat(result['source_as_of']) <= as_of
    db_session.rollback()


def test_intraday_provisional_replaces_same_day_unsettled_daily_bar(db_session):
    from zoneinfo import ZoneInfo

    from app.services.decision_board_service import DecisionBoardService

    inst = instrument(db_session)
    settings = get_settings().model_copy(update={'market_provider':'akshare'})
    as_of = datetime(2026, 9, 23, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    db_session.add(DailyBar(
        instrument_id=inst.id, trade_date=as_of.date(), open=2.8, high=2.9, low=2.7,
        close=2.82, volume=900, amount=2538, source='akshare:em:v101',
        adjust='none', quality_hash='unsettled-daily',
    ))
    DecisionBoardService(settings).record_provisional_input(
        db_session, ts_code=inst.ts_code, observed_at=as_of - timedelta(minutes=1),
        source='fixture:intraday', timestamp_verified=True, open_price=2.8,
        high_price=2.95, low_price=2.7, last_price=2.9, volume=1200, amount=3480,
        pct_change_percent_points=0.5,
    )

    result = chart_data(db_session, settings, inst.ts_code, '1d', 120, as_of=as_of)
    today = [bar for bar in result['bars'] if bar['date'][:10] == as_of.date().isoformat()]

    assert len(today) == 1
    assert today[0]['is_provisional'] is True
    assert today[0]['close'] == 2.9
    db_session.rollback()


def test_settled_daily_bar_replaces_same_day_provisional(db_session):
    from zoneinfo import ZoneInfo

    from app.services.decision_board_service import DecisionBoardService

    inst = instrument(db_session)
    settings = get_settings().model_copy(update={'market_provider':'akshare'})
    as_of = datetime(2026, 9, 23, 15, 15, tzinfo=ZoneInfo('Asia/Shanghai'))
    db_session.add(DailyBar(
        instrument_id=inst.id, trade_date=as_of.date(), open=2.8, high=2.9, low=2.7,
        close=2.84, volume=900, amount=2556, source='akshare:em:v101',
        adjust='none', quality_hash='settled-daily',
    ))
    DecisionBoardService(settings).record_provisional_input(
        db_session, ts_code=inst.ts_code, observed_at=as_of - timedelta(minutes=5),
        source='fixture:intraday', timestamp_verified=True, open_price=2.8,
        high_price=2.95, low_price=2.7, last_price=2.9, volume=1200, amount=3480,
        pct_change_percent_points=0.5,
    )

    result = chart_data(db_session, settings, inst.ts_code, '1d', 120, as_of=as_of)
    today = [bar for bar in result['bars'] if bar['date'][:10] == as_of.date().isoformat()]

    assert len(today) == 1
    assert today[0].get('is_provisional') is not True
    assert today[0]['close'] == 2.84
    db_session.rollback()


def test_detail_indicators_match_latest_chart_input_not_old_board_snapshot(db_session):
    from zoneinfo import ZoneInfo

    from app.services.decision_board_service import DecisionBoardService

    inst = instrument(db_session)
    settings = get_settings().model_copy(update={'market_provider':'akshare'})
    now = datetime.now(ZoneInfo('Asia/Shanghai')).replace(second=0, microsecond=0)
    earlier = now - timedelta(minutes=2)
    service = DecisionBoardService(settings)
    service.record_provisional_input(
        db_session, ts_code=inst.ts_code, observed_at=earlier, source='fixture:intraday',
        timestamp_verified=True, open_price=2.8, high_price=2.9, low_price=2.7,
        last_price=2.82, volume=1000, amount=2820, pct_change_percent_points=0.2,
    )
    service.refresh(db_session, generated_at=earlier + timedelta(seconds=5))
    service.record_provisional_input(
        db_session, ts_code=inst.ts_code, observed_at=now - timedelta(minutes=1),
        source='fixture:intraday', timestamp_verified=True, open_price=2.8,
        high_price=3.1, low_price=2.6, last_price=3.05, volume=1400, amount=4270,
        pct_change_percent_points=1.0,
    )

    as_of = datetime.now(ZoneInfo('Asia/Shanghai'))
    detail = instrument_detail(db_session, settings, inst.ts_code, None, as_of=as_of)
    chart = chart_data(db_session, settings, inst.ts_code, '1d', 100, as_of=as_of)

    assert detail['indicator_values'] == chart['bars'][-1]['indicators']
    assert detail['indicator_as_of'] == chart['bars'][-1]['date']
    assert detail['read_as_of'] == chart['as_of']
    db_session.rollback()


def test_detail_reports_disabled_instrument_and_module_gaps_separately(db_session):
    inst = instrument(db_session)
    inst.enabled = False
    settings = get_settings().model_copy(update={'market_provider':'akshare'})

    detail = instrument_detail(db_session, settings, inst.ts_code, None)

    assert detail['instrument']['enabled'] is False
    assert detail['availability']['instrument']['reason_code'] == 'instrument_disabled'
    assert detail['availability']['price']['status'] == 'available'
    assert detail['availability']['decision']['reason_code'] == 'decision_not_generated'
    assert detail['availability']['forecasts']['reason_code'] == 'forecast_not_generated'
    db_session.rollback()


def test_detail_compares_only_persisted_previous_decision_snapshots(db_session):
    from zoneinfo import ZoneInfo

    from app.services.decision_board_service import DecisionBoardService

    inst = instrument(db_session)
    settings = get_settings().model_copy(update={'market_provider':'mock'})
    service = DecisionBoardService(settings)
    now = datetime.now(ZoneInfo('Asia/Shanghai')).replace(second=0, microsecond=0)
    service.refresh(db_session, generated_at=now - timedelta(minutes=2))
    service.refresh(db_session, generated_at=now - timedelta(minutes=1))

    detail = instrument_detail(db_session, settings, inst.ts_code, None, as_of=now)

    comparison = detail['decision_explanation']['comparison']
    assert comparison['status'] == 'available'
    assert comparison['current_grade'] == detail['decision']['grade']
    assert comparison['previous_snapshot_id'] != detail['snapshot_id']
    assert detail['decision_explanation']['actionable'] is False
    db_session.rollback()


def test_detail_rejects_decision_snapshot_newer_than_its_read_time(db_session):
    from zoneinfo import ZoneInfo

    from app.services.decision_board_service import DecisionBoardService

    inst = instrument(db_session)
    settings = get_settings().model_copy(update={'market_provider':'mock'})
    read_as_of = datetime.now(ZoneInfo('Asia/Shanghai')).replace(second=0, microsecond=0)
    DecisionBoardService(settings).refresh(db_session, generated_at=read_as_of + timedelta(minutes=1))

    detail = instrument_detail(db_session, settings, inst.ts_code, None, as_of=read_as_of)

    assert detail['decision'] is None
    assert detail['availability']['decision']['reason_code'] == 'decision_snapshot_after_read_time'
    db_session.rollback()


def test_detail_rejects_indicator_snapshot_generated_after_its_read_time(db_session):
    from zoneinfo import ZoneInfo

    from app.utils.hashing import stable_hash

    inst = instrument(db_session)
    settings = get_settings().model_copy(update={'market_provider':'mock'})
    as_of = datetime.now(ZoneInfo('Asia/Shanghai'))
    strategy = settings.load_strategy()
    db_session.add(IndicatorSnapshot(
        instrument_id=inst.id, as_of_date=as_of.date(), version=strategy['indicator_version'],
        values_json={'rsi14': 99}, technical_score=50, risk_score=50, trend_label='fixture',
        data_quality=1, input_hash='f' * 64, feature_schema_version=strategy['feature_schema_version'],
        config_hash=stable_hash(strategy), generated_at=as_of + timedelta(minutes=1),
    ))
    db_session.flush()

    detail = instrument_detail(db_session, settings, inst.ts_code, None, as_of=as_of)
    chart = chart_data(db_session, settings, inst.ts_code, '1d', 100, as_of=as_of)

    assert 'indicator_snapshot_after_read_time' in detail['snapshot_issues']['indicator']
    assert detail['indicator_values'] == chart['research_bars'][-1]['indicators']
    db_session.rollback()


def test_empty_history_has_a_specific_chart_unavailability_reason(db_session):
    code = _unused_59_code(db_session)
    inst = Instrument(ts_code=code, symbol=code[:6], name='empty history', kind='ETF', enabled=True)
    db_session.add(inst)
    db_session.flush()
    settings = get_settings().model_copy(update={'market_provider':'akshare'})

    result = chart_data(db_session, settings, inst.ts_code, '1d', 100)

    assert result['available'] is False
    assert result['reason'] == 'history_not_prepared'
    db_session.rollback()


@pytest.mark.parametrize("provisional_day,provisional_price", [(2, 2.0), (3, 1.0)])
def test_split_price_basis_stays_separate_for_daily_weekly_and_monthly_charts(tmp_path, provisional_day, provisional_price):
    from zoneinfo import ZoneInfo

    from app.db.base import Base
    from app.services.support_resistance_service import SupportResistanceService
    from app.workspace.candle_periods import transform_chart
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(f"sqlite:///{tmp_path / 'r4a.sqlite3'}")
    Base.metadata.create_all(engine)
    settings = get_settings().model_copy(update={'market_provider':'akshare'})
    as_of = datetime(2026, 9, 23, 15, 15, tzinfo=ZoneInfo('Asia/Shanghai'))
    try:
        with Session(engine) as db:
            inst = Instrument(ts_code='512480.SH', symbol='512480', name='split fixture', kind='ETF', enabled=True)
            db.add(inst)
            db.flush()
            start = date(2026, 5, 25)
            split_date = date(2026, 7, 3)
            for i in range(80):
                day = start + timedelta(days=i)
                pre_split = day < split_date
                price = 2.0 if pre_split else 1.0
                db.add(DailyBar(
                    instrument_id=inst.id, trade_date=day, open=price, high=price * 1.02,
                    low=price * 0.98, close=price, volume=1000 if pre_split else 2000,
                    amount=2000, source='akshare:em:v101', adjust='none', quality_hash=f'split-{i}',
                ))
            db.flush()
            daily = chart_data(db, settings, inst.ts_code, '1d', 500, as_of=as_of)
            sr_frame = SupportResistanceService(settings)._sr_frame(db, inst.id)
            config = settings.load_strategy()['indicator']
            week = transform_chart(daily, '1w', config, 500, now=as_of)
            month = transform_chart(daily, '1mo', config, 500, now=as_of)
            daily_view = transform_chart(daily, '1d', config, 500, now=as_of)
            detail = instrument_detail(db, settings, inst.ts_code, None, as_of=as_of)

            assert daily['bars'][0]['close'] == 2.0
            assert daily['research_bars'][0]['close'] == 1.0
            assert daily['bars'][0]['indicators'] == {}
            assert daily['research_bars'][-1]['indicators']['ma20'] is not None
            assert daily['raw_overlay_allowed'] is False
            assert daily['research_price_basis'] == 'official_split_adjusted_price_research_not_total_return'
            assert daily_view['basis_transition'] is True
            assert '价格口径不同' in daily_view['indicator_note']
            assert sr_frame.iloc[0]['close'] == 1.0
            assert sr_frame.attrs['history_issue'] is None
            assert daily_view['series_id'] == daily['series_id']
            assert detail['indicator_values'] == daily['research_bars'][-1]['indicators']
            assert detail['availability']['price_basis']['reason_code'] == 'price_basis_mismatch'
            assert week['bars'][0]['close'] == 2.0
            assert week['research_bars'][0]['close'] == 1.0
            assert month['bars'][0]['close'] == 2.0
            assert month['research_bars'][0]['close'] == 1.0
            assert week['research_price_basis'] == month['research_price_basis'] == daily['research_price_basis']

            from app.services.decision_board_service import DecisionBoardService
            provisional_at = datetime(2026, 7, provisional_day, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
            service = DecisionBoardService(settings)
            provisional = service.record_provisional_input(
                db, ts_code=inst.ts_code, observed_at=provisional_at, source='akshare:em:v101',
                timestamp_verified=True, open_price=provisional_price, high_price=provisional_price * 1.02, low_price=provisional_price * .98,
                last_price=provisional_price, volume=2000 / provisional_price, amount=2000, pct_change_percent_points=0,
            )
            provisional_chart = chart_data(db, settings, inst.ts_code, '1d', 500,
                                           as_of=provisional_at + timedelta(minutes=1))
            provisional_decision = service._derive_provisional(db, inst.id, provisional)
            assert provisional_decision['indicator_values']['ma20'] == provisional_chart['research_bars'][-1]['indicators']['ma20']

            previous_input_hash, previous_series_id = daily['input_hash'], daily['series_id']
            for bar in db.scalars(select(DailyBar).where(DailyBar.instrument_id == inst.id)):
                if bar.trade_date < split_date:
                    bar.open *= 0.5
                    bar.high *= 0.5
                    bar.low *= 0.5
                    bar.close *= 0.5
                bar.adjust = 'qfq'
            db.flush()
            source_adjusted = chart_data(db, settings, inst.ts_code, '1d', 500, as_of=as_of)
            qfq_sr_frame = SupportResistanceService(settings)._sr_frame(db, inst.id)

            assert source_adjusted['bars'][0]['close'] == 1.0
            assert source_adjusted['research_bars'][0]['close'] == 1.0
            assert source_adjusted['raw_overlay_allowed'] is True
            assert source_adjusted['research_price_basis'] == 'source_adjustment:qfq'
            assert qfq_sr_frame.iloc[0]['close'] == 1.0
            assert qfq_sr_frame.attrs['history_issue'] is None
            assert source_adjusted['input_hash'] != previous_input_hash
            assert source_adjusted['series_id'] != previous_series_id
    finally:
        engine.dispose()


def test_same_day_daily_bar_is_partial_through_1515_settlement_cutoff(db_session):
    from zoneinfo import ZoneInfo

    inst = instrument(db_session)
    settings = get_settings().model_copy(update={'market_provider':'akshare'})
    as_of = datetime(2026, 9, 23, 15, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
    db_session.add(DailyBar(
        instrument_id=inst.id, trade_date=as_of.date(), open=2.8, high=2.9, low=2.7,
        close=2.85, volume=1000, amount=2850, source='akshare:em:v101',
        adjust='none', quality_hash='current-session',
    ))
    db_session.flush()

    partial = chart_data(db_session, settings, inst.ts_code, '1d', 100, as_of=as_of)
    settled = chart_data(db_session, settings, inst.ts_code, '1d', 100,
                         as_of=as_of.replace(hour=15, minute=15))

    assert partial['bars'][-1]['date'] == as_of.date().isoformat()
    assert partial['bars'][-1]['is_partial'] is True
    assert settled['bars'][-1]['is_partial'] is False


def test_chart_historical_as_of_excludes_later_515880_split_event(tmp_path):
    from zoneinfo import ZoneInfo

    from app.db.base import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(f"sqlite:///{tmp_path / '515880-asof.sqlite3'}")
    Base.metadata.create_all(engine)
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    rows = (
        (date(2026, 2, 2), 3.0),
        (date(2026, 2, 3), 1.0),
        (date(2026, 5, 29), 1.1),
        (date(2026, 7, 3), 1.1),
        (date(2026, 7, 6), 0.55),
    )
    try:
        with Session(engine) as db:
            inst = Instrument(
                ts_code="515880.SH", symbol="515880", name="two split as-of fixture",
                kind="ETF", enabled=True,
            )
            db.add(inst)
            db.flush()
            for day, close in rows:
                db.add(DailyBar(
                    instrument_id=inst.id,
                    trade_date=day,
                    open=close,
                    high=close * 1.01,
                    low=close * 0.99,
                    close=close,
                    volume=1000.0,
                    amount=close * 1000.0,
                    source="akshare:em:v101",
                    adjust="none",
                    quality_hash=f"quality-{day.isoformat()}",
                ))
            db.flush()

            between_events = chart_data(
                db, settings, inst.ts_code, "1d", 20,
                as_of=datetime(2026, 6, 1, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )
            after_second_event = chart_data(
                db, settings, inst.ts_code, "1d", 20,
                as_of=datetime(2026, 7, 6, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )

            assert [bar["close"] for bar in between_events["research_bars"]] == pytest.approx(
                [1.0, 1.0, 1.1]
            )
            assert between_events["research_basis_evidence_ids"] == [
                "sse_515880_20260203"
            ]
            assert [bar["close"] for bar in after_second_event["research_bars"]] == pytest.approx(
                [0.5, 0.5, 0.55, 0.55, 0.55]
            )
            assert after_second_event["research_basis_evidence_ids"] == [
                "sse_515880_20260203", "sse_515880_20260706"
            ]
    finally:
        engine.dispose()


def test_legacy_units_only_hide_volume_not_price_indicators(db_session):
    inst = instrument(db_session,legacy=True)
    settings=get_settings().model_copy(update={'market_provider':'akshare'})
    result=chart_data(db_session,settings,inst.ts_code,'1d',100)
    assert result['bars'][-1]['indicators']['ma20'] is not None
    assert result['bars'][-1]['volume'] is None
    assert result['actionable'] is False
    db_session.rollback()


def test_shared_indicator_refresh_skips_bad_asset_not_whole_universe(db_session):
    good=instrument(db_session)
    bad=instrument(db_session,missing_volume=True)
    settings=get_settings().model_copy(update={'market_provider':'akshare'})
    outcome=IndicatorService(settings).refresh_all(db_session)
    assert db_session.scalar(select(IndicatorSnapshot).where(IndicatorSnapshot.instrument_id==good.id)) is not None
    assert db_session.scalar(select(IndicatorSnapshot).where(IndicatorSnapshot.instrument_id==bad.id)) is None
    assert any(item['ts_code']==bad.ts_code for item in outcome['failures'])
    db_session.rollback()


def test_eligibility_scope_does_not_mutate_instruments(db_session):
    from app.providers.data_contract import history_issues
    good = instrument(db_session)
    bad = instrument(db_session, missing_volume=True)
    settings=get_settings().model_copy(update={'market_provider':'akshare'})
    issues=history_issues(db_session,settings)
    assert good.id not in issues and bad.id in issues
    assert good.enabled and bad.enabled
    db_session.rollback()


def test_original_board_keeps_price_labels_without_publishing_grade(db_session):
    from app.services.decision_board_service import DecisionBoardService
    inst=instrument(db_session, missing_volume=True)
    settings=get_settings().model_copy(update={'market_provider':'akshare'})
    built=DecisionBoardService(settings).refresh(db_session)
    row=next(r for r in built.payload['rows'] if r['ts_code']==inst.ts_code)
    assert row['data_status']=='historical_price_only'
    assert row['macd']['label'] != 'MACD不足'
    assert row['grade']=='数据异常' and row['actionable'] is False
    assert row['history'][-1]['volume'] is None
    db_session.rollback()

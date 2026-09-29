from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from app.core.config import get_settings
from app.models import DailyBar, Instrument
from app.workspace.read_model import chart_data
from sqlalchemy import event

SHANGHAI = ZoneInfo("Asia/Shanghai")


@pytest.fixture
def isolated_chan_input_db(tmp_path):
    from app.db.base import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(f"sqlite:///{tmp_path / 'chan-corporate-action.sqlite3'}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def _instrument(db, *, prefix: str = "59", ts_code: str | None = None) -> Instrument:
    suffix = str(int(uuid4().hex[:5], 16) % 10000).zfill(4)
    code = ts_code or f"{prefix}{suffix}.SH"
    item = Instrument(
        ts_code=code,
        symbol=code[:6],
        name="Chan input identity fixture",
        kind="ETF",
        enabled=True,
    )
    db.add(item)
    db.flush()
    return item


def _add_daily_bars(
    db,
    instrument: Instrument,
    start: date,
    count: int = 5,
    *,
    source: str = "akshare:em:v101",
    adjust: str = "none",
    volume: float | None = 1000.0,
    amount: float | None = 2000.0,
) -> list[DailyBar]:
    bars = []
    for offset in range(count):
        trade_day = start + timedelta(days=offset)
        close = 2.0 + offset * 0.01
        bar = DailyBar(
            instrument_id=instrument.id,
            trade_date=trade_day,
            open=close,
            high=close * 1.01,
            low=close * 0.99,
            close=close + 0.01,
            volume=volume,
            amount=amount,
            source=source,
            adjust=adjust,
            quality_hash=f"quality-{trade_day.isoformat()}",
        )
        db.add(bar)
        bars.append(bar)
    db.flush()
    return bars


def _add_period_daily_bars(db, instrument, days, closes=None):
    rows = []
    for offset, day in enumerate(days):
        close = closes[offset] if closes is not None else 2.0 + offset * 0.01
        row = DailyBar(
            instrument_id=instrument.id,
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
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def _weekdays(start: date, end: date) -> list[date]:
    days = []
    while start <= end:
        if start.weekday() < 5:
            days.append(start)
        start += timedelta(days=1)
    return days


def _calendar_rows(prepared):
    return [
        {
            "date": bar.timestamp.replace(tzinfo=UTC).astimezone(SHANGHAI).isoformat(),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "amount": bar.amount,
            "source": "M3B-A accepted daily research input",
        }
        for bar in prepared.bars
    ]


def test_freeze_chan_input_maps_r4a_daily_research_bars_to_m2_contract(db_session):
    from app.research.chan_input import freeze_chan_input

    instrument = _instrument(db_session)
    _add_daily_bars(db_session, instrument, date(2025, 1, 2))
    as_of = datetime(2025, 1, 7, 15, 15, tzinfo=SHANGHAI)
    settings = get_settings().model_copy(update={"market_provider": "akshare"})

    chart = chart_data(db_session, settings, instrument.ts_code, "1d", 20, as_of=as_of)
    frozen = freeze_chan_input(
        db_session,
        settings,
        instrument.ts_code,
        interval="D",
        as_of=as_of,
    )

    assert frozen.status == "prepared"
    assert frozen.prepared is not None
    assert frozen.prepared.instrument == instrument.ts_code
    assert frozen.prepared.interval == "D"
    assert frozen.price_basis_id == chart["research_price_basis_id"]
    assert frozen.logical_series_id != chart["series_id"]
    assert [bar.source_bar_id for bar in frozen.prepared.bars] == list(frozen.source_bar_ids)
    assert len(frozen.prepared.bars) == len(chart["research_bars"]) == 5
    for prepared_bar, research_bar in zip(
        frozen.prepared.bars, chart["research_bars"], strict=True
    ):
        assert prepared_bar.timestamp.date().isoformat() == research_bar["date"][:10]
        for field in ("open", "high", "low", "close", "volume", "amount"):
            assert getattr(prepared_bar, field) == pytest.approx(research_bar[field])
    from app.research.chan_contract import prepare_research_input

    canonical = prepare_research_input(
        instrument=frozen.prepared.instrument,
        interval=frozen.prepared.interval,
        series_id=frozen.prepared.series_id,
        price_basis_id=frozen.prepared.price_basis_id,
        adjustment_version=frozen.prepared.adjustment_version,
        input_revision_id=frozen.prepared.input_revision_id,
        settlement_status=frozen.prepared.settlement_status,
        config_id=frozen.prepared.config_id,
        bars=[bar.input_payload() for bar in frozen.prepared.bars],
    )
    assert canonical.input_hash == frozen.prepared.input_hash


def test_chan_series_identity_is_stable_while_daily_revisions_advance(db_session):
    from app.research.chan_input import freeze_chan_input

    instrument = _instrument(db_session)
    rows = _add_daily_bars(db_session, instrument, date(2025, 1, 2))
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    as_of_day_5 = datetime(2025, 1, 6, 16, 0, tzinfo=SHANGHAI)

    first = freeze_chan_input(
        db_session, settings, instrument.ts_code, interval="D", as_of=as_of_day_5
    )
    same_history = freeze_chan_input(
        db_session, settings, instrument.ts_code, interval="D", as_of=as_of_day_5
    )
    assert first.status == same_history.status == "prepared"
    assert first.logical_series_id == same_history.logical_series_id
    assert first.source_bar_ids == same_history.source_bar_ids
    assert first.input_revision_id == same_history.input_revision_id
    assert first.prepared.input_hash == same_history.prepared.input_hash

    _add_daily_bars(db_session, instrument, date(2025, 1, 7), count=1)
    as_of_day_6 = datetime(2025, 1, 7, 16, 0, tzinfo=SHANGHAI)
    after_append = freeze_chan_input(
        db_session, settings, instrument.ts_code, interval="D", as_of=as_of_day_6
    )
    assert after_append.logical_series_id == first.logical_series_id
    assert after_append.source_bar_ids[:5] == first.source_bar_ids
    assert after_append.input_revision_id != first.input_revision_id
    assert after_append.prepared.input_hash != first.prepared.input_hash
    assert after_append.source_bar_ids[-1] != first.source_bar_ids[-1]

    corrected = rows[2]
    corrected.close += 0.005
    corrected.high += 0.005
    corrected.quality_hash = "corrected-quality-revision"
    db_session.flush()
    after_correction = freeze_chan_input(
        db_session, settings, instrument.ts_code, interval="D", as_of=as_of_day_6
    )
    assert after_correction.logical_series_id == first.logical_series_id
    assert after_correction.source_bar_ids[2] != after_append.source_bar_ids[2]
    assert after_correction.source_bar_ids[:2] == after_append.source_bar_ids[:2]
    assert after_correction.source_bar_ids[3:] == after_append.source_bar_ids[3:]
    assert after_correction.input_revision_id != after_append.input_revision_id
    assert after_correction.prepared.input_hash != after_append.prepared.input_hash


def test_daily_freeze_obeys_as_of_and_1515_settlement_boundary(db_session):
    from app.research.chan_input import freeze_chan_input
    from app.services.decision_board_service import DecisionBoardService

    instrument = _instrument(db_session)
    _add_daily_bars(db_session, instrument, date(2025, 1, 2), count=4)
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    DecisionBoardService(settings).record_provisional_input(
        db_session,
        ts_code=instrument.ts_code,
        observed_at=datetime(2025, 1, 5, 10, 0, tzinfo=SHANGHAI),
        source="akshare:em:v101",
        timestamp_verified=True,
        open_price=2.0,
        high_price=2.1,
        low_price=1.9,
        last_price=2.05,
        volume=1000,
        amount=2000,
        pct_change_percent_points=0.5,
    )

    before_settlement = freeze_chan_input(
        db_session,
        settings,
        instrument.ts_code,
        interval="D",
        as_of=datetime(2025, 1, 5, 15, 14, tzinfo=SHANGHAI),
    )
    after_settlement = freeze_chan_input(
        db_session,
        settings,
        instrument.ts_code,
        interval="D",
        as_of=datetime(2025, 1, 5, 15, 15, tzinfo=SHANGHAI),
    )
    earlier_read = freeze_chan_input(
        db_session,
        settings,
        instrument.ts_code,
        interval="D",
        as_of=datetime(2025, 1, 4, 16, 0, tzinfo=SHANGHAI),
    )

    assert before_settlement.status == after_settlement.status == earlier_read.status == "prepared"
    assert [bar.timestamp.date() for bar in before_settlement.prepared.bars] == [
        date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 4)
    ]
    assert [bar.timestamp.date() for bar in after_settlement.prepared.bars] == [
        date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 4), date(2025, 1, 5)
    ]
    assert [bar.timestamp.date() for bar in earlier_read.prepared.bars] == [
        date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 4)
    ]
    assert before_settlement.logical_series_id == earlier_read.logical_series_id
    assert before_settlement.source_bar_ids == earlier_read.source_bar_ids
    assert before_settlement.input_revision_id == earlier_read.input_revision_id
    assert before_settlement.prepared.input_hash == earlier_read.prepared.input_hash
    assert after_settlement.prepared.settlement_status == "settled"


def test_unknown_or_unverified_volume_blocks_but_true_zero_survives(db_session):
    from app.research.chan_input import freeze_chan_input

    as_of = datetime(2025, 1, 7, 16, 0, tzinfo=SHANGHAI)
    settings = get_settings().model_copy(update={"market_provider": "akshare"})

    missing_volume = _instrument(db_session)
    _add_daily_bars(db_session, missing_volume, date(2025, 1, 2), volume=None)
    missing_result = freeze_chan_input(
        db_session, settings, missing_volume.ts_code, interval="D", as_of=as_of
    )
    assert missing_result.status == "blocked"
    assert missing_result.prepared is None
    assert missing_result.reason_code == "unknown_volume"

    undocumented_units = _instrument(db_session)
    _add_daily_bars(
        db_session,
        undocumented_units,
        date(2025, 1, 2),
        source="akshare:sina:v101",
    )
    unverified_result = freeze_chan_input(
        db_session, settings, undocumented_units.ts_code, interval="D", as_of=as_of
    )
    assert unverified_result.status == "blocked"
    assert unverified_result.prepared is None
    assert unverified_result.reason_code == "volume_units_unverified"

    missing_amount = _instrument(db_session)
    _add_daily_bars(db_session, missing_amount, date(2025, 1, 2), amount=None)
    missing_amount_result = freeze_chan_input(
        db_session, settings, missing_amount.ts_code, interval="D", as_of=as_of
    )
    assert missing_amount_result.status == "blocked"
    assert missing_amount_result.prepared is None
    assert missing_amount_result.reason_code == "unknown_amount"

    zero_volume = _instrument(db_session)
    _add_daily_bars(
        db_session,
        zero_volume,
        date(2025, 1, 2),
        volume=0.0,
        amount=0.0,
    )
    zero_result = freeze_chan_input(
        db_session, settings, zero_volume.ts_code, interval="D", as_of=as_of
    )
    assert zero_result.status == "prepared"
    assert [bar.volume for bar in zero_result.prepared.bars] == [0.0] * 5
    assert [bar.amount for bar in zero_result.prepared.bars] == [0.0] * 5


def test_one_valid_settled_bar_is_a_prepared_input(isolated_chan_input_db):
    from app.research.chan_input import freeze_chan_input

    db_session = isolated_chan_input_db
    instrument = _instrument(db_session)
    _add_daily_bars(db_session, instrument, date(2025, 1, 2), count=1)
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    result = freeze_chan_input(
        db_session,
        settings,
        instrument.ts_code,
        interval="D",
        as_of=datetime(2025, 1, 3, 16, 0, tzinfo=SHANGHAI),
    )

    assert result.status == "prepared"
    assert result.prepared.cutoff == 1


def test_missing_instrument_uses_bounded_reason_code(db_session):
    from app.research.chan_input import freeze_chan_input

    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    result = freeze_chan_input(
        db_session,
        settings,
        "599999.SH",
        interval="D",
        as_of=datetime(2025, 1, 3, 16, 0, tzinfo=SHANGHAI),
    )

    assert result.status == "blocked"
    assert result.reason_code == "instrument_missing"


def test_ambiguous_adjustment_uses_bounded_reason_code(isolated_chan_input_db):
    from app.research.chan_input import freeze_chan_input

    db_session = isolated_chan_input_db
    instrument = _instrument(db_session)
    _add_daily_bars(db_session, instrument, date(2025, 1, 2), adjust="qfq")
    _add_daily_bars(db_session, instrument, date(2025, 1, 2), adjust="hfq")
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    result = freeze_chan_input(
        db_session,
        settings,
        instrument.ts_code,
        interval="D",
        as_of=datetime(2025, 1, 7, 16, 0, tzinfo=SHANGHAI),
    )

    assert result.status == "blocked"
    assert result.reason_code == "ambiguous_price_basis"


def test_missing_source_revision_uses_bounded_reason_code(isolated_chan_input_db):
    from app.research.chan_input import freeze_chan_input

    db_session = isolated_chan_input_db
    instrument = _instrument(db_session)
    rows = _add_daily_bars(db_session, instrument, date(2025, 1, 2))
    rows[2].quality_hash = ""
    db_session.flush()
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    result = freeze_chan_input(
        db_session,
        settings,
        instrument.ts_code,
        interval="D",
        as_of=datetime(2025, 1, 7, 16, 0, tzinfo=SHANGHAI),
    )

    assert result.status == "blocked"
    assert result.reason_code == "source_identity_missing"


def test_history_qualification_reason_has_bounded_detail_code(isolated_chan_input_db):
    from app.research.chan_input import freeze_chan_input

    db_session = isolated_chan_input_db
    instrument = _instrument(db_session)
    rows = _add_daily_bars(db_session, instrument, date(2025, 1, 2))
    rows[-1].open = 3.0
    rows[-1].high = 3.1
    rows[-1].low = 2.9
    rows[-1].close = 3.0
    db_session.flush()
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    result = freeze_chan_input(
        db_session,
        settings,
        instrument.ts_code,
        interval="D",
        as_of=datetime(2025, 1, 7, 16, 0, tzinfo=SHANGHAI),
    )

    assert result.status == "blocked"
    assert result.reason_code == "history_qualification_blocked"
    assert result.detail_code == "unexplained_price_discontinuity"


def test_split_research_basis_matches_r4a_and_qfq_changes_chan_namespace(isolated_chan_input_db):
    from app.research.chan_input import freeze_chan_input

    db_session = isolated_chan_input_db
    instrument = _instrument(db_session, ts_code="512480.SH")
    split_day = date(2026, 7, 3)
    rows = _add_daily_bars(
        db_session, instrument, date(2026, 7, 1), count=4
    )
    for row in rows:
        if row.trade_date < split_day:
            continue
        offset = (row.trade_date - split_day).days
        row.open = 1.0 + offset * 0.005
        row.high = row.open + 0.01
        row.low = row.open - 0.01
        row.close = row.open + 0.005
    db_session.flush()
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    as_of = datetime(2026, 7, 5, 16, 0, tzinfo=SHANGHAI)

    official_research = freeze_chan_input(
        db_session, settings, instrument.ts_code, interval="D", as_of=as_of
    )
    chart = chart_data(db_session, settings, instrument.ts_code, "1d", 20, as_of=as_of)
    assert official_research.status == "prepared"
    assert official_research.price_basis_id == chart["research_price_basis_id"]
    for prepared_bar, research_bar in zip(
        official_research.prepared.bars, chart["research_bars"], strict=True
    ):
        assert prepared_bar.timestamp.date().isoformat() == research_bar["date"][:10]
        for field in ("open", "high", "low", "close", "volume", "amount"):
            assert getattr(prepared_bar, field) == pytest.approx(research_bar[field])

    for row in rows:
        if row.trade_date < split_day:
            row.open *= 0.5
            row.high *= 0.5
            row.low *= 0.5
            row.close *= 0.5
        row.adjust = "qfq"
    db_session.flush()
    source_adjusted = freeze_chan_input(
        db_session, settings, instrument.ts_code, interval="D", as_of=as_of
    )
    assert source_adjusted.status == "prepared"
    assert source_adjusted.price_basis_id != official_research.price_basis_id
    assert source_adjusted.logical_series_id != official_research.logical_series_id
    assert source_adjusted.source_bar_ids != official_research.source_bar_ids


def test_historical_chan_input_uses_only_effective_515880_actions(isolated_chan_input_db):
    from app.research.chan_input import freeze_chan_input

    db_session = isolated_chan_input_db
    instrument = _instrument(db_session, ts_code="515880.SH")
    raw_bars = (
        (date(2026, 2, 2), 3.0),
        (date(2026, 2, 3), 1.0),
        (date(2026, 5, 29), 1.1),
        (date(2026, 7, 3), 1.1),
        (date(2026, 7, 6), 0.55),
    )
    for day, close in raw_bars:
        db_session.add(
            DailyBar(
                instrument_id=instrument.id,
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
            )
        )
    db_session.flush()
    settings = get_settings().model_copy(update={"market_provider": "akshare"})

    between_events = freeze_chan_input(
        db_session,
        settings,
        instrument.ts_code,
        interval="D",
        as_of=datetime(2026, 6, 1, 16, 0, tzinfo=SHANGHAI),
    )
    after_second_event = freeze_chan_input(
        db_session,
        settings,
        instrument.ts_code,
        interval="D",
        as_of=datetime(2026, 7, 6, 16, 0, tzinfo=SHANGHAI),
    )

    assert between_events.status == after_second_event.status == "prepared"
    assert [bar.close for bar in between_events.prepared.bars] == pytest.approx(
        [1.0, 1.0, 1.1]
    )
    assert [bar.close for bar in after_second_event.prepared.bars] == pytest.approx(
        [0.5, 0.5, 0.55, 0.55, 0.55]
    )
    assert between_events.price_basis_id != after_second_event.price_basis_id


def test_m3b_a2_preserves_the_frozen_daily_identity_ledger(isolated_chan_input_db):
    from app.research.chan_input import freeze_chan_input

    db = isolated_chan_input_db
    instrument = _instrument(db, ts_code="515880.SH")
    _add_period_daily_bars(
        db,
        instrument,
        [date(2026, 2, 2), date(2026, 2, 3), date(2026, 5, 29), date(2026, 7, 3), date(2026, 7, 6)],
        closes=[3.0, 1.0, 1.1, 1.1, 0.55],
    )
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    daily = freeze_chan_input(
        db, settings, instrument.ts_code, interval="D",
        as_of=datetime(2026, 6, 1, 16, 0, tzinfo=SHANGHAI),
    )

    assert daily.status == "prepared", (daily.reason_code, daily.detail_code, daily.message)
    assert {
        "logical_series_id": daily.logical_series_id,
        "price_basis_id": daily.price_basis_id,
        "source_bar_ids": daily.source_bar_ids,
        "input_revision_id": daily.input_revision_id,
        "input_hash": daily.prepared.input_hash,
        "config_id": daily.prepared.config_id,
        "settlement_status": daily.prepared.settlement_status,
    } == {
        "logical_series_id": "af9feaa0fe9554bf9767a90a5656844676564852d03fb75358f08315e1435cab",
        "price_basis_id": "7bfddf99661c4948f4ca2dd7de9ebd37927e4a3e74acd1e3debb7fccb224ed82",
        "source_bar_ids": (
            "5bf1c34f7815fe27271b9289cc5e34f923c68b016b5adbdae51a60250811f2ce",
            "8d3854cb322b4283bef434249f5772d5def286f6f6a1ca5c26b679cf43aa71fe",
            "b4d058a09127ca94ddaafcc22cb8bce252d461159e11eff8905efe5d49c200ed",
        ),
        "input_revision_id": "7851521c6bcbb8a5e72bbcb988989659f5a8e2a19ff405651db77e28778ec339",
        "input_hash": "c73dd49ea9fa361b98cea4c7645733e06fb4752c4d748db0ee97016d61375dc6",
        "config_id": "044ae6adf34067e1c8bdec7f18eab21a7de9c7fb691519f27bf8caabfd293abf",
        "settlement_status": "settled",
    }
    assert daily.constituent_source_bar_ids == ()


def test_m3b_a2_week_and_month_inputs_match_existing_calendar_aggregation(isolated_chan_input_db):
    from app.research.chan_contract import prepare_research_input
    from app.research.chan_input import freeze_chan_input
    from app.utils.hashing import stable_hash
    from app.workspace.candle_periods import aggregate_bars

    db = isolated_chan_input_db
    instrument = _instrument(db)
    _add_period_daily_bars(db, instrument, _weekdays(date(2026, 1, 5), date(2026, 1, 23)))
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    as_of = datetime(2026, 1, 14, 15, 15, tzinfo=SHANGHAI)
    daily = freeze_chan_input(db, settings, instrument.ts_code, interval="D", as_of=as_of)
    assert daily.status == "prepared"

    period_inputs = {}
    for interval, calendar_period in (("W", "1w"), ("M", "1mo")):
        frozen = freeze_chan_input(db, settings, instrument.ts_code, interval=interval, as_of=as_of)
        period_inputs[interval] = frozen
        expected = aggregate_bars(_calendar_rows(daily.prepared), calendar_period, now=as_of)

        assert frozen.status == "prepared", (frozen.reason_code, frozen.detail_code, frozen.message)
        assert frozen.prepared.interval == interval
        assert frozen.logical_series_id != daily.logical_series_id
        assert frozen.price_basis_id == daily.price_basis_id
        assert frozen.prepared.adjustment_version == daily.prepared.adjustment_version
        assert frozen.prepared.config_id == stable_hash(
            {
                "base_config_id": daily.prepared.config_id,
                "period_input_contract_version": "r4c-calendar-period-v1",
            }
        )
        assert len(frozen.prepared.bars) == len(expected)
        assert frozen.prepared.settlement_status == "temporary"
        assert tuple(bar.source_bar_id for bar in frozen.prepared.bars) == frozen.source_bar_ids

        expected_lineage = []
        cursor = 0
        for row in expected:
            count = row["source_bar_count"]
            expected_lineage.append(
                tuple(bar.source_bar_id for bar in daily.prepared.bars[cursor : cursor + count])
            )
            cursor += count
        assert cursor == len(daily.prepared.bars)
        assert frozen.constituent_source_bar_ids == tuple(expected_lineage)
        canonical = prepare_research_input(
            instrument=frozen.prepared.instrument,
            interval=interval,
            series_id=frozen.prepared.series_id,
            price_basis_id=frozen.prepared.price_basis_id,
            adjustment_version=frozen.prepared.adjustment_version,
            input_revision_id=frozen.prepared.input_revision_id,
            settlement_status=frozen.prepared.settlement_status,
            config_id=frozen.prepared.config_id,
            bars=[bar.input_payload() for bar in frozen.prepared.bars],
        )
        assert canonical.input_hash == frozen.prepared.input_hash

        for actual, row in zip(frozen.prepared.bars, expected, strict=True):
            expected_time = datetime.fromisoformat(row["date"]).astimezone(UTC).replace(tzinfo=None)
            assert actual.timestamp == expected_time
            for field in ("open", "high", "low", "close", "volume", "amount"):
                assert getattr(actual, field) == pytest.approx(row[field])
    assert period_inputs["W"].logical_series_id != period_inputs["M"].logical_series_id


def test_m3b_a2_period_append_and_daily_correction_follow_aggregate_lineage(isolated_chan_input_db):
    from app.research.chan_input import freeze_chan_input

    db = isolated_chan_input_db
    instrument = _instrument(db)
    daily_rows = _add_period_daily_bars(db, instrument, _weekdays(date(2026, 1, 5), date(2026, 1, 19)))
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    open_week = freeze_chan_input(
        db, settings, instrument.ts_code, interval="W",
        as_of=datetime(2026, 1, 14, 15, 15, tzinfo=SHANGHAI),
    )
    appended_in_week = freeze_chan_input(
        db, settings, instrument.ts_code, interval="W",
        as_of=datetime(2026, 1, 15, 15, 15, tzinfo=SHANGHAI),
    )
    closed = freeze_chan_input(
        db, settings, instrument.ts_code, interval="W",
        as_of=datetime(2026, 1, 16, 15, 15, tzinfo=SHANGHAI),
    )
    next_week = freeze_chan_input(
        db, settings, instrument.ts_code, interval="W",
        as_of=datetime(2026, 1, 19, 15, 15, tzinfo=SHANGHAI),
    )

    assert open_week.status == appended_in_week.status == closed.status == next_week.status == "prepared"
    assert open_week.prepared.settlement_status == appended_in_week.prepared.settlement_status == "temporary"
    assert open_week.source_bar_ids[0] == appended_in_week.source_bar_ids[0]
    assert open_week.source_bar_ids[1] != appended_in_week.source_bar_ids[1]
    assert open_week.input_revision_id != appended_in_week.input_revision_id
    assert open_week.prepared.input_hash != appended_in_week.prepared.input_hash
    assert closed.prepared.settlement_status == "settled"
    assert next_week.prepared.settlement_status == "temporary"
    assert len(next_week.source_bar_ids) == len(closed.source_bar_ids) + 1
    assert next_week.source_bar_ids[: len(closed.source_bar_ids)] == closed.source_bar_ids
    assert next_week.logical_series_id == closed.logical_series_id
    assert next_week.input_revision_id != closed.input_revision_id
    assert next_week.prepared.input_hash != closed.prepared.input_hash

    daily_rows[7].close += 0.01
    daily_rows[7].quality_hash = "corrected-2026-01-14"
    db.flush()
    corrected = freeze_chan_input(
        db, settings, instrument.ts_code, interval="W",
        as_of=datetime(2026, 1, 19, 15, 15, tzinfo=SHANGHAI),
    )

    assert corrected.status == "prepared"
    assert corrected.source_bar_ids[0] == next_week.source_bar_ids[0]
    assert corrected.source_bar_ids[1] != next_week.source_bar_ids[1]
    assert corrected.source_bar_ids[2] == next_week.source_bar_ids[2]
    assert corrected.constituent_source_bar_ids[1] != next_week.constituent_source_bar_ids[1]
    assert corrected.input_revision_id != next_week.input_revision_id
    assert corrected.prepared.input_hash != next_week.prepared.input_hash


def test_m3b_a2_monthly_correction_changes_only_containing_aggregate_lineage(isolated_chan_input_db):
    from app.research.chan_input import freeze_chan_input

    db = isolated_chan_input_db
    instrument = _instrument(db)
    daily_rows = _add_period_daily_bars(
        db,
        instrument,
        _weekdays(date(2026, 1, 5), date(2026, 2, 27)),
    )
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    before = freeze_chan_input(
        db,
        settings,
        instrument.ts_code,
        interval="M",
        as_of=datetime(2026, 2, 27, 15, 15, tzinfo=SHANGHAI),
    )

    assert before.status == "prepared"
    assert before.prepared.settlement_status == "settled"
    assert len(before.source_bar_ids) == len(before.constituent_source_bar_ids) == 2
    corrected_daily = next(row for row in daily_rows if row.trade_date == date(2026, 1, 14))
    corrected_daily.close += 0.01
    corrected_daily.quality_hash = "corrected-2026-01-14-monthly"
    db.flush()

    after = freeze_chan_input(
        db,
        settings,
        instrument.ts_code,
        interval="M",
        as_of=datetime(2026, 2, 27, 15, 15, tzinfo=SHANGHAI),
    )

    assert after.status == "prepared"
    assert after.prepared.settlement_status == "settled"
    assert after.price_basis_id == before.price_basis_id
    assert after.logical_series_id == before.logical_series_id
    assert after.source_bar_ids[0] != before.source_bar_ids[0]
    assert after.constituent_source_bar_ids[0] != before.constituent_source_bar_ids[0]
    assert after.source_bar_ids[1] == before.source_bar_ids[1]
    assert after.constituent_source_bar_ids[1] == before.constituent_source_bar_ids[1]
    assert after.input_revision_id != before.input_revision_id
    assert after.prepared.input_hash != before.prepared.input_hash


def test_m3b_a2_month_period_transitions_from_temporary_to_settled(isolated_chan_input_db):
    from app.research.chan_input import freeze_chan_input

    db = isolated_chan_input_db
    instrument = _instrument(db)
    _add_period_daily_bars(db, instrument, _weekdays(date(2026, 1, 5), date(2026, 2, 2)))
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    mid_month = freeze_chan_input(
        db, settings, instrument.ts_code, interval="M",
        as_of=datetime(2026, 1, 14, 15, 15, tzinfo=SHANGHAI),
    )
    month_end = freeze_chan_input(
        db, settings, instrument.ts_code, interval="M",
        as_of=datetime(2026, 1, 30, 15, 15, tzinfo=SHANGHAI),
    )
    next_month = freeze_chan_input(
        db, settings, instrument.ts_code, interval="M",
        as_of=datetime(2026, 2, 2, 15, 15, tzinfo=SHANGHAI),
    )

    assert mid_month.status == month_end.status == next_month.status == "prepared"
    assert mid_month.prepared.settlement_status == "temporary"
    assert month_end.prepared.settlement_status == "settled"
    assert next_month.prepared.settlement_status == "temporary"
    assert mid_month.logical_series_id == month_end.logical_series_id == next_month.logical_series_id
    assert mid_month.source_bar_ids[0] != month_end.source_bar_ids[0]
    assert mid_month.input_revision_id != month_end.input_revision_id
    assert mid_month.prepared.input_hash != month_end.prepared.input_hash
    assert next_month.source_bar_ids[0] == month_end.source_bar_ids[0]
    assert month_end.source_bar_ids[1:] == ()
    assert len(next_month.source_bar_ids) == len(month_end.source_bar_ids) + 1
    assert next_month.input_revision_id != month_end.input_revision_id
    assert next_month.prepared.input_hash != month_end.prepared.input_hash


@pytest.mark.parametrize("interval", ["W", "M"])
def test_m3b_a2_price_basis_transition_uses_causal_daily_namespace(isolated_chan_input_db, interval):
    from app.research.chan_input import freeze_chan_input

    db = isolated_chan_input_db
    instrument = _instrument(db, ts_code="515880.SH")
    _add_period_daily_bars(
        db,
        instrument,
        [date(2026, 2, 2), date(2026, 2, 3), date(2026, 5, 29), date(2026, 7, 3), date(2026, 7, 6)],
        closes=[3.0, 1.0, 1.1, 1.1, 0.55],
    )
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    before = freeze_chan_input(
        db, settings, instrument.ts_code, interval=interval,
        as_of=datetime(2026, 6, 1, 16, 0, tzinfo=SHANGHAI),
    )
    after = freeze_chan_input(
        db, settings, instrument.ts_code, interval=interval,
        as_of=datetime(2026, 7, 6, 16, 0, tzinfo=SHANGHAI),
    )

    assert before.status == after.status == "prepared"
    assert before.price_basis_id != after.price_basis_id
    assert before.logical_series_id != after.logical_series_id
    assert before.source_bar_ids != after.source_bar_ids


@pytest.mark.parametrize("interval", ["W", "M"])
@pytest.mark.parametrize("unknown_field", ["volume", "amount"])
def test_m3b_a2_blocks_daily_unknowns_and_preserves_aggregate_zero(isolated_chan_input_db, interval, unknown_field):
    from app.research.chan_input import freeze_chan_input

    db = isolated_chan_input_db
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    unknown = _instrument(db)
    unknown_row = _add_period_daily_bars(db, unknown, [date(2026, 1, 5)])[0]
    setattr(unknown_row, unknown_field, None)
    db.flush()
    blocked = freeze_chan_input(
        db, settings, unknown.ts_code, interval=interval,
        as_of=datetime(2026, 1, 5, 15, 15, tzinfo=SHANGHAI),
    )
    assert blocked.status == "blocked"
    assert blocked.reason_code == f"unknown_{unknown_field}"

    zero = _instrument(db, prefix="58")
    zero_row = _add_period_daily_bars(db, zero, [date(2026, 1, 5)])[0]
    zero_row.volume = 0.0
    zero_row.amount = 0.0
    db.flush()
    prepared = freeze_chan_input(
        db, settings, zero.ts_code, interval=interval,
        as_of=datetime(2026, 1, 5, 15, 15, tzinfo=SHANGHAI),
    )
    assert prepared.status == "prepared"
    assert prepared.prepared.bars[0].volume == pytest.approx(0.0)
    assert prepared.prepared.bars[0].amount == pytest.approx(0.0)


@pytest.mark.parametrize("interval", ["W", "M"])
def test_m3b_a2_blocked_period_does_not_expose_daily_identity(db_session, monkeypatch, interval):
    import app.research.chan_input as chan_input

    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    daily_blocked = chan_input.FrozenChanInput(
        status="blocked",
        reason_code="source_identity_missing",
        logical_series_id="daily-logical-series",
        price_basis_id="known-price-basis",
        input_revision_id="daily-input-revision",
        source_bar_ids=("daily-source-bar",),
        source_as_of=date(2026, 1, 5),
    )
    original_freeze = chan_input.freeze_chan_input

    def freeze_with_blocked_daily(db, current_settings, instrument_code, *, interval, as_of):
        if interval == "D":
            return daily_blocked
        return original_freeze(
            db,
            current_settings,
            instrument_code,
            interval=interval,
            as_of=as_of,
        )

    monkeypatch.setattr(chan_input, "freeze_chan_input", freeze_with_blocked_daily)
    result = chan_input.freeze_chan_input(
        db_session,
        settings,
        "515880.SH",
        interval=interval,
        as_of=datetime(2026, 1, 5, 15, 15, tzinfo=SHANGHAI),
    )

    assert result.status == "blocked"
    assert result.reason_code == "source_identity_missing"
    assert result.price_basis_id == "known-price-basis"
    assert result.source_as_of == date(2026, 1, 5)
    assert result.logical_series_id is None
    assert result.input_revision_id is None
    assert result.source_bar_ids == ()
    assert result.constituent_source_bar_ids == ()


@pytest.mark.parametrize("interval", ["W", "M"])
def test_m3b_a2_freeze_is_provider_and_database_write_free(isolated_chan_input_db, monkeypatch, interval):
    from app.research.chan_input import freeze_chan_input

    db = isolated_chan_input_db
    instrument = _instrument(db)
    _add_period_daily_bars(db, instrument, _weekdays(date(2026, 1, 5), date(2026, 1, 9)))
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    monkeypatch.setattr("app.providers.factory.create_provider", lambda *_: pytest.fail("Provider called"))

    def reject_dml(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().lower().startswith(("insert", "update", "delete", "replace")):
            pytest.fail(f"A2 input freeze executed DML: {statement}")

    event.listen(db.bind, "before_cursor_execute", reject_dml)
    try:
        frozen = freeze_chan_input(
            db, settings, instrument.ts_code, interval=interval,
            as_of=datetime(2026, 1, 9, 15, 15, tzinfo=SHANGHAI),
        )
        assert frozen.status == "prepared"
    finally:
        event.remove(db.bind, "before_cursor_execute", reject_dml)


def test_indicator_version_does_not_enter_chan_logical_series_identity(db_session):
    from types import SimpleNamespace

    from app.research.chan_input import freeze_chan_input

    instrument = _instrument(db_session)
    _add_daily_bars(db_session, instrument, date(2025, 1, 2))
    as_of = datetime(2025, 1, 7, 16, 0, tzinfo=SHANGHAI)

    def settings_for(version: str):
        return SimpleNamespace(
            market_provider="akshare",
            timezone=SHANGHAI,
            load_strategy=lambda: {"indicator_version": version},
        )

    v1 = freeze_chan_input(
        db_session, settings_for("indicator-v1"), instrument.ts_code, interval="D", as_of=as_of
    )
    v2 = freeze_chan_input(
        db_session, settings_for("indicator-v2"), instrument.ts_code, interval="D", as_of=as_of
    )

    assert v1.status == v2.status == "prepared"
    assert v1.logical_series_id == v2.logical_series_id
    assert v1.source_bar_ids == v2.source_bar_ids


def test_adjustment_contract_version_changes_chan_series_and_source_identity(db_session, monkeypatch):
    import app.research.chan_input as chan_input

    instrument = _instrument(db_session)
    _add_daily_bars(db_session, instrument, date(2025, 1, 2))
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    as_of = datetime(2025, 1, 7, 16, 0, tzinfo=SHANGHAI)
    original_basis = chan_input.research_price_basis

    baseline = chan_input.freeze_chan_input(
        db_session, settings, instrument.ts_code, interval="D", as_of=as_of
    )

    def next_adjustment_contract(*args, **kwargs):
        result = original_basis(*args, **kwargs)
        return {**result, "adjustment_contract_version": "corporate-action-research-v2"}

    monkeypatch.setattr(chan_input, "research_price_basis", next_adjustment_contract)
    changed = chan_input.freeze_chan_input(
        db_session, settings, instrument.ts_code, interval="D", as_of=as_of
    )

    assert baseline.status == changed.status == "prepared"
    assert changed.price_basis_id == baseline.price_basis_id
    assert changed.logical_series_id != baseline.logical_series_id
    assert changed.source_bar_ids != baseline.source_bar_ids


def test_non_daily_interval_is_blocked_and_freeze_performs_no_database_writes(db_session):
    from app.research.chan_input import freeze_chan_input

    instrument = _instrument(db_session)
    _add_daily_bars(db_session, instrument, date(2025, 1, 2))
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    as_of = datetime(2025, 1, 7, 16, 0, tzinfo=SHANGHAI)
    dml_statements: list[str] = []
    connection = db_session.get_bind()

    def collect_dml(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            dml_statements.append(statement)

    event.listen(connection, "before_cursor_execute", collect_dml)
    try:
        daily = freeze_chan_input(
            db_session, settings, instrument.ts_code, interval="D", as_of=as_of
        )
        unsupported = freeze_chan_input(
            db_session, settings, instrument.ts_code, interval="Q", as_of=as_of
        )
    finally:
        event.remove(connection, "before_cursor_execute", collect_dml)

    assert daily.status == "prepared"
    assert unsupported.status == "blocked"
    assert unsupported.reason_code == "unsupported_interval"
    assert dml_statements == []

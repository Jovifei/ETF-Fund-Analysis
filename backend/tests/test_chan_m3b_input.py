from datetime import date, datetime, timedelta
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
            high=close + 0.02,
            low=close - 0.02,
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
        weekly = freeze_chan_input(
            db_session, settings, instrument.ts_code, interval="W", as_of=as_of
        )
    finally:
        event.remove(connection, "before_cursor_execute", collect_dml)

    assert daily.status == "prepared"
    assert weekly.status == "blocked"
    assert weekly.reason_code == "unsupported_interval"
    assert dml_statements == []

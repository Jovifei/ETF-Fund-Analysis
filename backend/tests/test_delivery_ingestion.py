"""Regression/performance tests: injected adapters and idempotent batched history."""
from dataclasses import replace
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.models import DailyBar, Instrument
from app.providers.akshare import AKShareProvider
from app.providers.types import BarRecord
from app.services.market_service import MarketService


@pytest.fixture
def store():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Instrument(ts_code='589971.SH', symbol='589971', name='测试标的', kind='ETF', enabled=True))
        db.commit()
        yield db
    engine.dispose()


def sample_records(count=100):
    return [BarRecord(ts_code='589971.SH', trade_date=date.today()-timedelta(days=count-i),
                      open=2, high=3, low=1, close=2.1, volume=1000, amount=2100,
                      source='test:deterministic') for i in range(count)]


class Adapter:
    name = 'test'
    def __init__(self, records):
        self.records, self.calls = records, []
    def fetch_daily_bars(self, code, start, end):
        self.calls.append((code, start, end))
        return [r for r in self.records if start <= r.trade_date <= end]


def service(records):
    return MarketService(Adapter(records), Settings(_env_file=None), persist_provider_audits=False)


def test_optional_akshare_client_can_be_injected_without_import():
    fake = SimpleNamespace()
    assert AKShareProvider(Settings(_env_file=None), ak_client=fake).ak is fake


def test_ingestion_has_constant_select_count_and_skips_unchanged(store):
    s = service(sample_records())
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(store.get_bind(), 'before_cursor_execute', capture)
    try:
        first = s.refresh_daily_bars(store, lookback_days=120)
        store.commit()
        assert first['inserted'] == 100
        assert len([q for q in statements if q.lstrip().upper().startswith('SELECT')]) <= 5
        statements.clear()
        second = s.refresh_daily_bars(store, lookback_days=120)
        store.commit()
        assert second['inserted'] == 0 and second['updated'] == 0
        assert second['unchanged'] == 100
        assert not any(q.lstrip().upper().startswith('UPDATE DAILY_BARS') for q in statements)
        assert len([q for q in statements if q.lstrip().upper().startswith('SELECT')]) <= 5
    finally:
        event.remove(store.get_bind(), 'before_cursor_execute', capture)


def test_correction_is_updated_and_exact_duplicate_is_idempotent(store):
    rows = sample_records(2)
    s = service(rows + [rows[0]])
    assert s.refresh_daily_bars(store, lookback_days=30)['inserted'] == 2
    store.commit()
    s.provider.records = [replace(rows[0], close=2.2), rows[1]]
    result = s.refresh_daily_bars(store, lookback_days=30)
    assert result['updated'] == 1 and result['unchanged'] == 1
    assert store.scalar(select(DailyBar).where(DailyBar.trade_date == rows[0].trade_date)).close == 2.2


@pytest.mark.parametrize('bad', ['conflict', 'wrong_code', 'nonfinite', 'zero_price'])
def test_invalid_batch_never_partially_mutates_history(store, bad):
    rows = sample_records(2)
    invalid = {'conflict': replace(rows[0], close=2.3),
               'wrong_code': replace(rows[0], ts_code='589972.SH'),
               'nonfinite': replace(rows[0], close=float('nan')),
               'zero_price': replace(rows[0], open=0, low=0)}[bad]
    result = service([rows[0], rows[1], invalid]).refresh_daily_bars(store, lookback_days=30)
    assert result['failures'] and result['inserted'] == 0
    assert store.scalars(select(DailyBar)).all() == []


@pytest.mark.parametrize('output, expected', [({'status':'skipped'},'partial'), ({'status':'partial'},'partial'), ({'missing_codes':['512480.SH']},'partial'), ({'status':'failed'},'failed'), ({'inserted':0,'updated':0,'unchanged':2},'succeeded')])
def test_worker_preserves_partial_outcomes(output, expected):
    from app.workspace.worker import outcome_state
    assert outcome_state(output)==expected


@pytest.mark.parametrize('price', [0,-1,float('nan'),float('inf'),False])
def test_invalid_quote_is_not_a_zero_cost_valuation(price):
    from app.workspace.read_model import quote_view
    from datetime import datetime,UTC
    quote=SimpleNamespace(price=price,pct_change=None,source='fixture',quote_time=datetime.now(UTC),fetched_at=datetime.now(UTC),timestamp_verified=True,degraded_reason=None,is_realtime=True)
    result=quote_view(quote,Settings(_env_file=None))
    assert result['price'] is None and result['status']=='invalid' and not result['actionable']

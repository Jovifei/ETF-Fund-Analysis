from datetime import date, datetime
from dataclasses import replace

from app.core.config import get_settings
from app.providers.composite import CompositeProvider
from app.providers.corporate_action_contract import research_history_rows
from app.providers.data_contract import price_history_issue
from app.providers.types import BarRecord
from app.scheduler import settled_pipeline_tasks


def test_known_split_does_not_disqualify_complete_provider_batch():
    first = BarRecord('512000.SH', date(2025, 8, 1), 1.138, 1.14, 1.13, 1.138,
                      volume=1000, amount=1138, source='tencent:stock_zh_a_hist_tx:v101')
    second = replace(first, trade_date=date(2025, 8, 4), open=.572, high=.58, low=.57, close=.572)
    assert CompositeProvider._daily_candidate([first, second], second.trade_date)[0] == 3
    assert first.close == 1.138


def test_intraday_history_repair_does_not_block_quote_scheduler(db_session):
    assert settled_pipeline_tasks(db_session, get_settings(), datetime(2026, 9, 21, 13, 30,
                                    tzinfo=get_settings().timezone)) == []


def test_official_bank_coal_and_property_events_remove_false_gaps():
    for code, before, after, prices in [
        ('512800.SH', date(2025,7,4), date(2025,7,7), (1.777,.894)),
        ('515220.SH', date(2024,4,11), date(2024,4,12), (2.612,1.297)),
        ('512200.SH', date(2024,8,9), date(2024,8,12), (.441,1.191)),
    ]:
        rows = [BarRecord(code, day, p,p,p,p,volume=1000,amount=p*1000,source='akshare:em:v101')
                for day,p in zip((before,after),prices)]
        assert price_history_issue(research_history_rows(rows,code)) is None


def test_intraday_sectors_refresh_independently_and_publish(monkeypatch):
    from test_scheduler_resilience import _run_fake_tick
    _, calls, _ = _run_fake_tick(monkeypatch,
        now=datetime(2026,9,21,13,8,tzinfo=get_settings().timezone),
        success_due={'refresh_sector_snapshots'},
        terminal_due={'refresh_sector_snapshots'})
    names = [name for name, _ in calls]
    assert 'refresh_sector_snapshots' in names
    assert names.index('refresh_sector_snapshots') < names.index('refresh_decision_board')


def test_unexplained_gap_still_rejects_provider_batch():
    first = BarRecord('510300.SH', date(2026,9,17), 1,1,1,1,
                      volume=1000, amount=1000, source='tencent:stock_zh_a_hist_tx:v101')
    second = replace(first, trade_date=date(2026,9,18), open=3, high=3, low=3, close=3)
    assert CompositeProvider._daily_candidate([first,second],second.trade_date)[0] == 0

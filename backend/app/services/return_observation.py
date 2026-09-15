"""Choose dated daily/quote returns without using fetch time as exchange time."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import select
from app.models import DailyBar
from app.services.settlement import SETTLEMENT_CUTOFF
from app.services.trading_calendar_service import TradingCalendarService
from app.utils.numbers import finite_or_none


def observed_returns(db, settings, instrument_id, quote, at: datetime) -> dict:
    local = at.astimezone(settings.timezone) if at.tzinfo else at.replace(tzinfo=settings.timezone)
    session = TradingCalendarService(settings).effective_trade_date(local.date())
    # A return comparison uses one explicit price basis. Mixed research bases
    # are rejected elsewhere; the raw display deliberately prefers none.
    bases = list(db.scalars(select(DailyBar.adjust).where(DailyBar.instrument_id == instrument_id).distinct()))
    basis = 'none' if 'none' in bases else bases[0] if len(bases) == 1 else None
    rows = (db.scalars(select(DailyBar).where(DailyBar.instrument_id == instrument_id,
        DailyBar.adjust == basis, DailyBar.trade_date <= session)
        .order_by(DailyBar.trade_date.desc(), DailyBar.id.desc()).limit(3)).all() if basis else [])
    def rate(row, previous=None):
        pct = finite_or_none(row.pct_change)
        if pct is not None:
            return pct / 100.0
        prior = finite_or_none(row.pre_close) or (finite_or_none(previous.close) if previous else None)
        close = finite_or_none(row.close)
        return close / prior - 1.0 if close is not None and prior and prior > 0 else None
    source_time = getattr(quote, 'quote_time', None)
    if source_time is not None:
        source_time = source_time.astimezone(settings.timezone) if source_time.tzinfo else source_time.replace(tzinfo=settings.timezone)
    trustworthy_date = (source_time is not None and source_time <= local and source_time.date() == session
                        and not str(getattr(quote, 'degraded_reason', '') or '').startswith('source_timestamp_missing'))
    settled_today = bool(rows and rows[0].trade_date == session and
                         (session < local.date() or local.time().replace(tzinfo=None) >= SETTLEMENT_CUTOFF))
    quote_return = finite_or_none(getattr(quote, 'pct_change', None)) if trustworthy_date else None
    if quote_return is not None and not settled_today:
        value, day, label = quote_return / 100.0, session, 'dated_quote_observation'
    elif rows:
        value, day, label = rate(rows[0], rows[1] if len(rows)>1 else None), rows[0].trade_date, 'confirmed_daily_close'
    else:
        value, day, label = None, None, 'unavailable'
    previous = [row for row in rows if day is not None and row.trade_date < day]
    prior_return = rate(previous[0], previous[1] if len(previous)>1 else None) if previous else None
    return {'value': value, 'as_of_date': day.isoformat() if day else None, 'basis': label,
            'target_trade_date': session.isoformat(), 'previous_return': prior_return,
            'previous_as_of_date': previous[0].trade_date.isoformat() if previous else None}

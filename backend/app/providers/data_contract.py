"""Versioned wire units; old rows are re-fetched, never guessed/conversion-in-place."""
from sqlalchemy import select
from app.models import DailyBar, Instrument
from app.providers.base import ProviderError

VERSION = 'cn-fund-shares-cny-v1.0.2'
LEGACY_SOURCES = ('akshare','tushare','tushare:fund_daily')


class HistoryContractError(ProviderError):
    pass


def legacy_history_present(db, instrument_id=None):
    query=select(DailyBar.id).join(Instrument,DailyBar.instrument_id==Instrument.id).where(
        Instrument.enabled.is_(True),DailyBar.source.in_(LEGACY_SOURCES))
    if instrument_id is not None: query=query.where(DailyBar.instrument_id==instrument_id)
    return db.scalar(query.limit(1)) is not None


def require_current_history(db, settings):
    if settings.market_provider!='mock' and legacy_history_present(db):
        raise HistoryContractError('legacy_history_requires_complete_source_refetch')

    if settings.market_provider != 'mock':
        price_only = db.scalar(select(DailyBar.id).join(Instrument, DailyBar.instrument_id == Instrument.id).where(
            Instrument.enabled.is_(True), DailyBar.source == 'akshare:sina:v101', DailyBar.volume.is_(None)).limit(1))
        if price_only is not None:
            raise HistoryContractError('price_only_history_requires_volume_for_shared_signals')


def history_issues(db, settings, instrument_ids=None):
    """Per-instrument shared-computation gate; price display is independent.

    This never flips enabled flags or edits historical snapshots. The global
    gate above remains in use for validation/backtests that need a whole panel.
    """
    from sqlalchemy import case, func, or_
    if settings.market_provider == 'mock':
        return {}
    invalid = or_(DailyBar.open <= 0, DailyBar.low <= 0,
                  DailyBar.low > DailyBar.open, DailyBar.low > DailyBar.close,
                  DailyBar.high < DailyBar.open, DailyBar.high < DailyBar.close)
    query = select(DailyBar.instrument_id,
        func.sum(case((DailyBar.source.in_(LEGACY_SOURCES), 1), else_=0)),
        func.sum(case((or_(DailyBar.volume.is_(None), DailyBar.volume < 0), 1), else_=0)),
        func.count(func.distinct(DailyBar.adjust)),
        func.sum(case((invalid, 1), else_=0)))
    if instrument_ids is not None:
        query = query.where(DailyBar.instrument_id.in_(instrument_ids))
    result = {}
    for ident, legacy, missing_volume, bases, bad in db.execute(query.group_by(DailyBar.instrument_id)):
        reason = ('legacy_units_unverified' if legacy else
                  'ambiguous_price_basis' if bases != 1 else
                  'invalid_ohlc' if bad else
                  'volume_missing_for_shared_signals' if missing_volume else None)
        if reason:
            result[ident] = reason
    return result

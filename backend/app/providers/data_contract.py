"""Versioned wire units; old rows are re-fetched, never guessed/conversion-in-place."""
from sqlalchemy import select
from app.models import DailyBar, Instrument
from app.providers.base import ProviderError

VERSION = 'cn-fund-shares-cny-v1.0.1'
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

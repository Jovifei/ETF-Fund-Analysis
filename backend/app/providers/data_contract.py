"""Shared-computation qualification, not a data repair or unit inference tool.

Display may retain raw prices. Unknown units and unresolved price events may
never become qualified simply because the amount/volume ratio looks plausible.
"""
from __future__ import annotations
import math
from sqlalchemy import select
from app.models import DailyBar, Instrument
from app.providers.base import ProviderError

VERSION = "cn-fund-shares-cny-v1.0.3-audit"
LEGACY_SOURCES = ("akshare", "tushare", "tushare:fund_daily")
UNVERIFIED_UNIT_SOURCES = ("akshare:sina:v101", "akshare:sina:v102")
# Conservative anomaly trigger, NOT proof of a split or continuity certification.
MAX_UNEXPLAINED_GAP = 0.35

class HistoryContractError(ProviderError):
    pass

def finite(value):
    return value is not None and not isinstance(value, bool) and math.isfinite(float(value))

def price_history_issue(rows):
    if not rows:
        return "history_missing"
    if len({row.adjust for row in rows}) != 1:
        return "ambiguous_price_basis"
    prior = None
    for row in rows:
        prices = [row.open, row.high, row.low, row.close]
        if not all(finite(v) and v > 0 for v in prices) or not row.low <= min(row.open, row.close) <= max(row.open, row.close) <= row.high:
            return "invalid_ohlc"
        if prior is not None:
            if row.trade_date <= prior.trade_date:
                return "duplicate_or_unordered_history"
            # No auto-rescaling, dropping, smoothing, or inferred corporate action.
            if abs(row.close / prior.close - 1) > MAX_UNEXPLAINED_GAP or abs(row.open / prior.close - 1) > MAX_UNEXPLAINED_GAP:
                return "unexplained_price_discontinuity"
        prior = row
    return None

def row_units_verified(row):
    return (row.source not in LEGACY_SOURCES + UNVERIFIED_UNIT_SOURCES
            and "mock" not in str(row.source).lower())

def assess_history(rows):
    reasons = []
    price_issue = price_history_issue(rows)
    if price_issue:
        reasons.append(price_issue)
    if any(row.source in LEGACY_SOURCES for row in rows):
        reasons.append("legacy_units_unverified")
    if any(row.source == "akshare:sina:v102" for row in rows):
        reasons.append("sina_absolute_units_unverified")
    if any("mock" in str(row.source).lower() for row in rows):
        reasons.append("mock_history")
    if any(not finite(row.volume) or row.volume < 0 for row in rows):
        reasons.append("volume_missing_for_shared_signals")
    if any(not finite(row.amount) or row.amount < 0 for row in rows):
        reasons.append("amount_missing_for_shared_signals")
    if any(row.source == "akshare:sina:v101" for row in rows) and not reasons:
        reasons.append("sina_absolute_units_unverified")
    return reasons

def legacy_history_present(db, instrument_id=None):
    query = select(DailyBar.id).join(Instrument, DailyBar.instrument_id == Instrument.id).where(
        Instrument.enabled.is_(True), DailyBar.source.in_(LEGACY_SOURCES))
    if instrument_id is not None:
        query = query.where(DailyBar.instrument_id == instrument_id)
    return db.scalar(query.limit(1)) is not None

def history_issues(db, settings, instrument_ids=None):
    if settings.market_provider == "mock":
        return {}
    ids = list(instrument_ids) if instrument_ids is not None else list(db.scalars(select(Instrument.id).where(Instrument.enabled.is_(True))))
    if not ids:
        return {}
    groups = {ident: [] for ident in ids}
    for row in db.scalars(select(DailyBar).where(DailyBar.instrument_id.in_(ids)).order_by(DailyBar.instrument_id, DailyBar.trade_date, DailyBar.adjust)):
        groups[row.instrument_id].append(row)
    return {ident: reasons[0] for ident, rows in groups.items() if (reasons := assess_history(rows))}

def require_current_history(db, settings):
    if settings.market_provider == "mock":
        return
    issues = history_issues(db, settings)
    if issues:
        reason = next(iter(issues.values()))
        if reason == "legacy_units_unverified":
            reason = "legacy_history_requires_complete_source_refetch"
        raise HistoryContractError(reason)

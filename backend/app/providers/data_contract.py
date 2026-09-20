"""Shared-computation qualification, not a data repair or unit inference tool.

Display may retain raw prices. Unknown units and unresolved price events may
never become qualified simply because the amount/volume ratio looks plausible.
"""
from __future__ import annotations

import math
from datetime import date, datetime

from sqlalchemy import select

from app.models import DailyBar, Instrument
from app.providers.base import ProviderError

VERSION = "cn-fund-shares-cny-v1.0.7-sina-recompute"
LEGACY_SOURCES = ("akshare", "tushare", "tushare:fund_daily")
UNVERIFIED_UNIT_SOURCES = ("akshare:sina:v101", "akshare:sina:v102")
RESEARCH_ADJUST = "corporate_action_research"
# Conservative anomaly trigger, NOT proof of a split or continuity certification.
MAX_UNEXPLAINED_GAP = 0.35

class HistoryContractError(ProviderError):
    pass

# These are endpoint-specific normalization contracts, not blanket SDK trust.
# A new provider must explicitly document its conversion and extend tests here.
DOCUMENTED_UNIT_SOURCES = frozenset({
    "akshare:em:v101", "tencent:stock_zh_a_hist_tx:v101", "tushare:fund_daily:v101", "ftshare:fetch_daily_bars",
})

def finite(value):
    if value is None or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False

def price_history_issue(rows):
    if not rows:
        return "history_missing"
    if any(row.adjust not in {"none", "qfq", "hfq", RESEARCH_ADJUST} for row in rows):
        return "unknown_price_basis"
    if len({row.adjust for row in rows}) != 1:
        return "ambiguous_price_basis"
    prior = None
    for row in rows:
        prices = [row.open, row.high, row.low, row.close]
        if not all(finite(v) and float(v) > 0 for v in prices):
            return "invalid_ohlc"
        op, high, low, close = map(float, prices)
        if not low <= min(op, close) <= max(op, close) <= high:
            return "invalid_ohlc"
        if not isinstance(row.trade_date, date) or isinstance(row.trade_date, datetime):
            return "invalid_history_date"
        if prior is not None:
            if row.trade_date <= prior.trade_date:
                return "duplicate_or_unordered_history"
            # No auto-rescaling, dropping, smoothing, or inferred corporate action.
            if abs(close / float(prior.close) - 1) > MAX_UNEXPLAINED_GAP or abs(op / float(prior.close) - 1) > MAX_UNEXPLAINED_GAP:
                return "unexplained_price_discontinuity"
        prior = row
    return None

def row_units_verified(row):
    return row.source in DOCUMENTED_UNIT_SOURCES

def assess_history(rows):
    reasons = []
    price_issue = price_history_issue(rows)
    if price_issue:
        reasons.append(price_issue)
    if any(row.source in LEGACY_SOURCES for row in rows):
        reasons.append("legacy_units_unverified")
    if any(row.source == "akshare:sina:v102" for row in rows):
        reasons.append("sina_absolute_units_unverified")
    if any(row.source == "akshare:sina:v101" for row in rows):
        reasons.append("price_only_history_units_unverified")
    if any(row.source not in DOCUMENTED_UNIT_SOURCES | set(LEGACY_SOURCES + UNVERIFIED_UNIT_SOURCES)
           and "mock" not in str(row.source).lower() for row in rows):
        reasons.append("unknown_endpoint_units_unverified")
    if any("mock" in str(row.source).lower() for row in rows):
        reasons.append("mock_history")
    if any(not finite(row.volume) or float(row.volume) < 0 for row in rows):
        reasons.append("volume_missing_for_shared_signals")
    if any(not finite(row.amount) or float(row.amount) < 0 for row in rows):
        reasons.append("amount_missing_for_shared_signals")
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
    from itertools import groupby
    from app.providers.corporate_action_contract import research_history_rows
    code_by_id = dict(db.execute(select(Instrument.id, Instrument.ts_code).where(Instrument.id.in_(ids))).all())
    issues = {}
    seen = set()
    query = select(DailyBar).where(DailyBar.instrument_id.in_(ids)).order_by(
        DailyBar.instrument_id, DailyBar.trade_date, DailyBar.adjust).execution_options(yield_per=256)
    for ident, group in groupby(db.scalars(query), key=lambda row: row.instrument_id):
        seen.add(ident)
        raw_rows = list(group)
        research_rows = research_history_rows(raw_rows, code_by_id.get(ident))
        reasons = assess_history(research_rows)
        if reasons:
            issues[ident] = reasons[0]
    for ident in ids:
        if ident not in seen:
            issues[ident] = "history_missing"
    return issues


def trailing_unverified_history(rows):
    """Describe a safe stale-history scope when only the newest rows degrade.

    A complete, documented-unit prefix can still support a historical research
    snapshot.  This helper never promotes the unverified tail: callers must
    mark the result stale, keep actionable false, and avoid using the tail for
    shared volume-derived calculations.  Interleaved or wholly unverified
    histories return ``None`` so the existing fail-closed behavior remains.
    """

    ordered = sorted(rows or [], key=lambda row: row.trade_date)
    if not ordered:
        return None
    unverified = [index for index, row in enumerate(ordered) if not row_units_verified(row)]
    if not unverified:
        return None
    first = unverified[0]
    qualified = ordered[:first]
    tail = ordered[first:]
    if not qualified or any(row_units_verified(row) for row in tail):
        return None
    if price_history_issue(qualified) or assess_history(qualified):
        return None
    reasons = assess_history(tail)
    return {
        "qualified_through": qualified[-1].trade_date,
        "tail_start": tail[0].trade_date,
        "tail_rows": len(tail),
        "reasons": reasons or ["unverified_history_tail"],
    }


def qualified_research_history(rows, ts_code: str | None = None):
    """Return the evidence-adjusted research prefix and any stale tail scope."""

    from app.providers.corporate_action_contract import research_history_rows

    research_rows = research_history_rows(rows, ts_code)
    return research_rows, trailing_unverified_history(research_rows)

def require_current_history(db, settings):
    if settings.market_provider == "mock":
        return
    issues = history_issues(db, settings)
    if issues:
        reason = next(iter(issues.values()))
        if reason == "legacy_units_unverified":
            reason = "legacy_history_requires_complete_source_refetch"
        raise HistoryContractError(reason)

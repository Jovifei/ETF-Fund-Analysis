"""Shared fail-closed checks on the inputs, independent of UI labels."""
from datetime import timedelta
import math
from app.providers.data_contract import VERSION, assess_history
from app.services.trading_calendar_service import TradingCalendarService

GATE_VERSION = "qualification-v2-20260912"

def quote_reasons(settings, quote, now, maximum_age_minutes):
    reasons = []
    target = now.replace(tzinfo=settings.timezone) if now.tzinfo is None else now.astimezone(settings.timezone)
    calendar = TradingCalendarService(settings).decision(target.date())
    if not calendar.verified:
        reasons.append("calendar_unverified")
    if not calendar.is_trade_day:
        reasons.append("not_a_trading_day")
    if settings.market_provider == "mock" or quote and "mock" in str(quote.source).lower():
        reasons.append("mock_provider")
    if quote is None:
        return reasons + ["quote_missing"]
    if not quote.is_realtime:
        reasons.append("quote_not_realtime")
    if not quote.timestamp_verified:
        reasons.append("source_timestamp_unverified")
    if quote.degraded_reason:
        reasons.append("quote_degraded")
    if not isinstance(quote.price, (int, float)) or isinstance(quote.price, bool) or not math.isfinite(quote.price) or quote.price <= 0:
        reasons.append("invalid_quote_price")
    stamp = quote.quote_time
    if stamp is None:
        return reasons + ["quote_time_missing"]
    stamp = stamp.replace(tzinfo=settings.timezone) if stamp.tzinfo is None else stamp.astimezone(settings.timezone)
    age = (target - stamp).total_seconds()
    if age < 0:
        reasons.append("quote_from_future")
    if stamp.date() != target.date():
        reasons.append("quote_wrong_session")
    if age > float(maximum_age_minutes) * 60:
        reasons.append("quote_stale")
    return reasons

def qualify_1430(settings, quote, now, window, bars=None, indicator=None):
    strategy = settings.load_strategy()
    reasons = quote_reasons(settings, quote, now, window.get("maximum_quote_age_minutes", 8))
    reasons += assess_history(bars or [])
    if not window["inside"]:
        reasons.append("outside_1430_window")
    if indicator is None:
        reasons.append("indicator_missing")
    else:
        if indicator.version != strategy["indicator_version"]:
            reasons.append("indicator_version_mismatch")
        if indicator.feature_schema_version != strategy["feature_schema_version"]:
            reasons.append("indicator_schema_mismatch")
        from app.utils.hashing import stable_hash
        if indicator.config_hash != stable_hash(strategy):
            reasons.append("indicator_config_mismatch")
        target = now.replace(tzinfo=settings.timezone) if now.tzinfo is None else now.astimezone(settings.timezone)
        expected = TradingCalendarService(settings).effective_trade_date(target.date() - timedelta(days=1))
        if indicator.as_of_date != expected or not bars or bars[-1].trade_date != expected:
            reasons.append("settled_history_not_as_of_previous_session")
    input_ready = not reasons
    # There is no audited PIT/OOS approval artifact in this release. An env
    # boolean or a verified quote must never silently confer that qualification.
    reasons.append("historical_1430_backtest_not_qualified")
    return {"actionable": False, "input_ready": input_ready, "research_only": True,
            "reasons": list(dict.fromkeys(reasons)), "decision_window": window,
            "historical_1430_backtest": "not_qualified", "gate_version": GATE_VERSION,
            "data_contract": VERSION}

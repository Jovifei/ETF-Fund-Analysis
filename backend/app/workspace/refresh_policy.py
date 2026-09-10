"""Opt-in low-frequency cadence; uses the existing scheduler and TaskService locks."""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Asia/Shanghai')


def market_time(value):
    return value.replace(tzinfo=ZONE) if value.tzinfo is None else value.astimezone(ZONE)


@dataclass(frozen=True)
class RefreshPlan:
    market_open: bool
    after_close: bool
    quote_minutes: int = 30
    signal_minutes: int = 30
    context_minutes: int = 30
    news_minutes: int = 30


def balanced_plan(now: datetime, *, is_trade_day: bool) -> RefreshPlan:
    clock = market_time(now).time().replace(tzinfo=None)
    opened = is_trade_day and (time(9, 30) <= clock <= time(11, 30) or time(13) <= clock <= time(15))
    return RefreshPlan(market_open=opened,
                       after_close=is_trade_day and time(16, 15) <= clock <= time(22),
                       news_minutes=30 if time(8) <= clock < time(22) else 120)


def daily_due(last_success, last_attempt, now, *, retry_minutes=60):
    """Run once per local day; retry failures with a bounded wait.

    Naive legacy TaskRun times were produced by MarketClock, not UTC server defaults.
    Calendar eligibility is supplied by the caller, never inferred from weekdays here.
    """
    current = market_time(now)
    if last_success is not None and market_time(last_success).date() >= current.date():
        return False
    return last_attempt is None or current-market_time(last_attempt) >= timedelta(minutes=retry_minutes)

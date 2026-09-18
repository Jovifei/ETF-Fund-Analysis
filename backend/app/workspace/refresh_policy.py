"""Session-aware refresh cadence; uses the existing scheduler and TaskService locks.

Asia/Shanghai wall-clock policy for quote/signal/decision-board refresh
(trading days only; lunch 11:30–13:00 is a hard gap, not a slow poll):

- 09:30, 10:30, 11:30: hourly
- 13:00, 13:30, 14:00: every 30 minutes
- 14:30–14:49: every 10 minutes
- 14:50–15:00: every 2 minutes

Open auction (09:15–09:29) is not a quote-refresh window.  Non-trading days
return None so the scheduler cannot record a fake session success.  Daily bar
settlement remains owned by ``settlement.session_refresh_due`` (15:15 cutoff;
an early same-day attempt cannot complete today's target session).
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Asia/Shanghai')


def market_time(value):
    return value.replace(tzinfo=ZONE) if value.tzinfo is None else value.astimezone(ZONE)


def intraday_refresh_minutes(now: datetime, *, is_trade_day: bool) -> int | None:
    """Return the requested quote/signal cadence for the current session.

    The board slots and the independent quote refresh use the same policy so a
    browser refresh cannot observe a cadence that the scheduler does not use:
    09:30–11:30 hourly, 13:00–14:29 every 30 minutes, 14:30–14:49 every 10
    minutes, and 14:50–15:00 every 2 minutes.  Outside an open session the
    caller keeps its normal non-session behavior.
    """

    if not is_trade_day:
        return None
    clock = market_time(now).time().replace(tzinfo=None)
    if time(9, 30) <= clock <= time(11, 30):
        return 60
    if time(13, 0) <= clock < time(14, 30):
        return 30
    if time(14, 30) <= clock < time(14, 50):
        return 10
    if time(14, 50) <= clock <= time(15, 0):
        return 2
    return None


def session_quote_window_open(now: datetime, *, is_trade_day: bool) -> bool:
    """True only inside the documented cadence windows, never during lunch or auction."""

    return intraday_refresh_minutes(now, is_trade_day=is_trade_day) is not None


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

"""Daily completion is tied to a settled exchange session, not task wall time."""
from datetime import datetime, time, timedelta
from sqlalchemy import select
from app.models import TaskRun
from app.services.trading_calendar_service import TradingCalendarService

SETTLEMENT_CUTOFF = time(15, 15)

def settled_session(settings, at=None):
    at = at or datetime.now(settings.timezone)
    local = at.astimezone(settings.timezone) if at.tzinfo else at.replace(tzinfo=settings.timezone)
    day = local.date()
    if local.time().replace(tzinfo=None) < SETTLEMENT_CUTOFF:
        day -= timedelta(days=1)
    return TradingCalendarService(settings).effective_trade_date(day)

def session_refresh_due(db, settings, task_name, now, retry_minutes=15):
    """After-settlement or next-session catchup; partial attempts back off."""
    local = now.astimezone(settings.timezone)
    # Do not launch an after-close chain during the known unsettled gap.
    wall = local.time().replace(tzinfo=None)
    if time(15, 0) < wall < SETTLEMENT_CUTOFF:
        return False
    target = settled_session(settings, now).isoformat()
    runs = db.scalars(select(TaskRun).where(TaskRun.task_name == task_name)
        .order_by(TaskRun.started_at.desc()).limit(30)).all()
    for run in runs:
        result = run.result_json or {}
        if (run.status == "succeeded" and result.get("target_trade_date") == target
                and result.get("coverage_complete") is True):
            return False
    if runs:
        run = runs[0]
        last = run.finished_at or run.started_at
        if last is not None:
            last = last.replace(tzinfo=settings.timezone) if last.tzinfo is None else last
            if (local - last).total_seconds() < retry_minutes * 60:
                return False
    return True

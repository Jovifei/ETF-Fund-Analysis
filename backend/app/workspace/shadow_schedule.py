"""Market-calendar-aware bounded slots; no network calendar fallback."""
from datetime import datetime,time
from zoneinfo import ZoneInfo
from app.services.trading_calendar_service import TradingCalendarService

def due_slot(settings,now,slots=('14:30','14:45','14:50','14:55','15:00','15:15'),window_seconds=120):
    if not 1<=window_seconds<=300 or not 1<=len(slots)<=8:raise ValueError('bounded schedule required')
    now=now.astimezone(ZoneInfo('Asia/Shanghai'));decision=TradingCalendarService(settings).decision(now.date())
    if not decision.verified or not decision.is_trade_day:return None
    for slot in slots:
        parsed=time.fromisoformat(slot)
        if not time(14,20)<=parsed<=time(15,30):raise ValueError('slot outside research window')
        age=(now-datetime.combine(now.date(),parsed,now.tzinfo)).total_seconds()
        if 0<=age<window_seconds:return now.date().isoformat()+'T'+slot
    return None

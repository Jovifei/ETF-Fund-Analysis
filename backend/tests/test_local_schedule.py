from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import pytest
from app.workspace.local_schedule import (
    due_slot_local,
    LOCAL_SCHEDULE_SLOTS,
    SETTLEMENT_REFRESH_SLOT,
    LocalRunLock,
)


def test_schedule_due_slots_include_settlement(monkeypatch):
    from app.workspace import shadow_schedule

    class MockCalendar:
        def __init__(self, settings):
            pass

        def decision(self, date):
            return SimpleNamespace(verified=True, is_trade_day=True)

    monkeypatch.setattr(shadow_schedule, "TradingCalendarService", MockCalendar)

    # 14:20 preheat
    now_preheat = datetime(2026, 10, 12, 6, 20, tzinfo=timezone.utc)  # 14:20 Shanghai
    slot = due_slot_local(None, now_preheat)
    assert slot is not None and slot.endswith("14:20")

    # 14:30 intraday
    now_1430 = datetime(2026, 10, 12, 6, 30, tzinfo=timezone.utc)  # 14:30 Shanghai
    slot = due_slot_local(None, now_1430)
    assert slot is not None and slot.endswith("14:30")

    # 16:10 settlement
    now_settlement = datetime(2026, 10, 12, 8, 10, tzinfo=timezone.utc)  # 16:10 Shanghai
    slot = due_slot_local(None, now_settlement)
    assert slot is not None and slot.endswith(SETTLEMENT_REFRESH_SLOT)


def test_local_run_lock_prevents_concurrency(tmp_path):
    lock_file = tmp_path / "run.lock"
    lock1 = LocalRunLock(lock_file)
    assert lock1.acquire() is True

    # Second acquire should fail
    lock2 = LocalRunLock(lock_file)
    assert lock2.acquire() is False

    # Release first lock
    lock1.release()

    # Now second acquire can succeed
    assert lock2.acquire() is True
    lock2.release()

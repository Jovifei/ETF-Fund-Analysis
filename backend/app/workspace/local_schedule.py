from __future__ import annotations

import os
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.clock import MarketClock
from app.core.config import get_settings
from app.services.trading_calendar_service import TradingCalendarService

SHANGHAI = ZoneInfo("Asia/Shanghai")
LOCAL_SCHEDULE_SLOTS = ("14:20", "14:30", "14:45", "14:50", "14:55", "15:00", "15:15", "16:10")
SETTLEMENT_REFRESH_SLOT = "16:10"


def due_slot_local(
    last_slot: str | None,
    now: datetime,
    slots: tuple[str, ...] = LOCAL_SCHEDULE_SLOTS,
    settings=None,
    window_seconds: int = 180,
) -> str | None:
    settings = settings or get_settings()
    local = now.astimezone(SHANGHAI) if now.tzinfo is not None else now.replace(tzinfo=SHANGHAI)
    if not TradingCalendarService(settings).decision(local.date()).is_trade_day:
        return None
    for slot_text in slots:
        parsed = time.fromisoformat(slot_text)
        slot_dt = datetime.combine(local.date(), parsed, SHANGHAI)
        age = (local - slot_dt).total_seconds()
        if 0 <= age < window_seconds:
            slot_id = f"{local.date().isoformat()} {slot_text}"
            if last_slot != slot_id:
                return slot_id
    return None


class LocalRunLock:
    """Non-blocking lock file to ensure single-instance local compute execution."""

    def __init__(self, lock_path: Path | str):
        self.lock_path = Path(lock_path)
        self._fd: int | None = None

    def acquire(self, *, reclaim_stale: bool = True) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Atomic creation with O_EXCL
            self._fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(self._fd, f"{os.getpid()}\n".encode("utf-8"))
            return True
        except FileExistsError:
            # Check if existing lock is stale (e.g. process terminated)
            try:
                # If file exists, check mtime
                mtime = self.lock_path.stat().st_mtime
                if reclaim_stale and datetime.now().timestamp() - mtime > 7200:
                    try:
                        self.lock_path.unlink()
                        self._fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                        os.write(self._fd, f"{os.getpid()}\n".encode("utf-8"))
                        return True
                    except OSError:
                        return False
            except OSError:
                return False
            return False
        except OSError:
            return False

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            owned = os.fstat(fd)
        except OSError:
            owned = None
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
        if owned is not None:
            try:
                current = self.lock_path.stat()
                if (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                    self.lock_path.unlink()
            except OSError:
                pass

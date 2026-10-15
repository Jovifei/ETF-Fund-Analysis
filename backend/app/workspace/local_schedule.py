from __future__ import annotations

import os
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

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
    decision = TradingCalendarService(settings).decision(local.date())
    if not decision.verified or not decision.is_trade_day:
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
        # OS ownership expires when the process exits. Age never proves an owner
        # dead; keep the inode in place so a third process cannot lock a replacement.
        if self._fd is not None:
            return False
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = None
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR, 0o600)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
            self._fd = fd
            return True
        except OSError:
            if fd is not None:
                os.close(fd)
            return False

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        os.close(fd)

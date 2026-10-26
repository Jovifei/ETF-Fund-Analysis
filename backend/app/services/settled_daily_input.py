"""Typed, process-local authority for settled daily research (never realtime)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

SETTLED_DAILY_INPUT_VERSION = "settled-daily-research-input-v1"


@dataclass(frozen=True)
class SettledDailyInput:
    """A receipt minted from actual bars, a scoped TaskRun and display quotes.

    This object is deliberately not reconstructed from exported JSON. Consumers
    revalidate its database identity and input hashes before using daily values.
    """
    base: dict
    quote_hash: str
    task_hash: str
    run_id: str
    after_id: int
    started_at: datetime
    finished_at: datetime
    receipt_hash: str

    @property
    def observation(self) -> dict:
        return {"contract_version": SETTLED_DAILY_INPUT_VERSION,
                "type": "settled_daily_research",
                "basis": "settled_daily_bars", "source_session": self.base["target_trade_date"],
                "scope_hash": _digest(self.base["target_codes"]),
                "daily_input_hash": self.base["input_hash"], "quote_batch_hash": self.quote_hash,
                "quote_task_hash": self.task_hash, "is_realtime": False,
                "source_qualification": "UNKNOWN", "actionable": False,
                "calibration_status": "not_calibrated"}


def _digest(value):
    from app.workspace.shadow_bundle import digest
    return digest(value)


def require_settled_daily_input(db, settings, value, *, at, codes=None):
    from app.workspace.local_compute import _revalidate_settled_daily_input
    if type(value) is not SettledDailyInput:
        raise ValueError("validated in-process settled-daily input required")
    _revalidate_settled_daily_input(db, settings, value, at, codes=codes)
    return value

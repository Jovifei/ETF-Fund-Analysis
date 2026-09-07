"""多周期行情 bar 服务（修复方案 PR-G）。

职责：分钟线（30m/60m）的增量同步与读取。安全与真实性边界：
* 生产默认 ``MINUTE_BARS_ENABLED=false``；未启用时同步任务直接跳过，
  Mock provider 例外（本地演示需要，且 mock 永远 actionable=false）；
* 日线永不冒充分钟线：读取端分钟区间无数据时返回 ``available=false``，
  前端周期按钮禁用；
* 时间戳资格沿用上游 source timestamp 语义，未验证不参与 actionable。
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo
from uuid import uuid4
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import DailyBar, Instrument, MarketBar
from app.providers.base import MarketProvider, ProviderError
from app.services.audit_service import AuditTimer, record_provider_audit

logger = logging.getLogger(__name__)

SUPPORTED_MINUTE_INTERVALS = ("30m", "60m")
_INTERVAL_MINUTES = {"5m": 5, "15m": 15, "30m": 30, "60m": 60}


class MarketBarService:
    def __init__(self, settings: Settings | None = None, provider: MarketProvider | None = None) -> None:
        self.settings = settings or get_settings()
        self.provider = provider
        self.tz = ZoneInfo(self.settings.timezone_name)

    # ------------------------------------------------------------------ sync

    def sync_minute_bars(
        self,
        db: Session,
        codes: list[str] | None = None,
        interval: str = "30m",
        *,
        window_days: int = 30,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = run_id or uuid4().hex
        if interval not in SUPPORTED_MINUTE_INTERVALS:
            raise ValueError(f"不支持的分钟周期：{interval}")
        if self.provider is None:
            raise ValueError("minute bar sync requires an injected provider")
        mock = getattr(self.provider, "name", "") == "mock"
        if not self.settings.minute_bars_enabled and not mock:
            return {
                "run_id": run_id,
                "status": "skipped",
                "reason": "MINUTE_BARS_ENABLED=false；真实分钟线未启用（日线不冒充分钟线）",
                "interval": interval,
                "inserted": 0,
            }
        if codes is None:
            codes = [
                item.ts_code
                for item in db.scalars(select(Instrument).where(Instrument.enabled.is_(True))).all()
            ]
        if not 1 <= window_days <= 30:
            raise ValueError("minute window must be 1..30 days")
        codes = list(dict.fromkeys(code.upper() for code in codes))
        if len(codes) > 200:
            raise ValueError("minute universe exceeds limit")
        end = datetime.now(self.tz)
        start = end - timedelta(days=window_days)
        inserted, updated, incomplete = 0, 0, 0
        failures: dict[str, str] = {}
        for code in codes:
            instrument = db.scalar(select(Instrument).where(Instrument.ts_code == code, Instrument.kind.in_(("ETF", "LOF"))))
            if instrument is None:
                failures[code] = "instrument_not_found"
                continue
            timer, fetch_error, records = AuditTimer(), None, []
            try:
                try:
                    records = self.provider.fetch_minute_bars(code, interval, start.date(), end.date())
                except Exception as exc:
                    fetch_error = ProviderError(type(exc).__name__)
                    raise
                finally:
                    record_provider_audit(db, run_id=run_id, operation="fetch_minute_bars", provider=self.provider,
                                          result=records, error=fetch_error, latency_ms=timer.elapsed_ms)
                if not records:
                    raise ValueError("minute_empty")
                validated = {}
                for record in records:
                    bar_time = record.trade_date
                    if record.ts_code != code or not isinstance(bar_time, datetime):
                        raise ValueError("minute_identity_or_timestamp_invalid")
                    bar_time = bar_time.replace(tzinfo=self.tz) if bar_time.tzinfo is None else bar_time.astimezone(self.tz)
                    if not start.date() <= bar_time.date() <= end.date():
                        raise ValueError("minute_outside_request")
                    if not mock and bar_time > end:
                        incomplete += 1
                        continue
                    values = (record.open, record.high, record.low, record.close)
                    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0 for v in values):
                        raise ValueError("minute_price_invalid")
                    if record.high < max(record.open, record.close, record.low) or record.low > min(record.open, record.close):
                        raise ValueError("minute_ohlc_invalid")
                    if any(v is not None and (not isinstance(v, (float, int)) or isinstance(v, bool) or not math.isfinite(v) or v < 0) for v in (record.volume, record.amount)):
                        raise ValueError("minute_amount_invalid")
                    if not isinstance(record.source, str) or not 1 <= len(record.source) <= 32:
                        raise ValueError("minute_source_invalid")
                    if bar_time in validated and validated[bar_time].to_dict() != record.to_dict():
                        raise ValueError("minute_duplicate_conflict")
                    validated[bar_time] = record
                if not validated:
                    raise ValueError("minute_no_completed_bars")
                added, changed = 0, 0
                with db.begin_nested():
                    existing = {row.bar_time.replace(tzinfo=self.tz) if row.bar_time.tzinfo is None else row.bar_time.astimezone(self.tz): row for row in db.scalars(select(MarketBar).where(
                        MarketBar.instrument_id == instrument.id, MarketBar.interval == interval,
                        MarketBar.bar_time >= min(validated), MarketBar.bar_time <= max(validated)))}
                    for bar_time, record in validated.items():
                        row = existing.get(bar_time)
                        if row is None:
                            row = MarketBar(instrument_id=instrument.id, interval=interval, bar_time=bar_time)
                            db.add(row)
                            added += 1
                        else:
                            changed += 1
                        for field in ("open", "high", "low", "close", "volume", "amount", "source"):
                            setattr(row, field, getattr(record, field))
                        # Explicit source bar-close time is retained, but historical
                        # PIT availability and operational qualification are not proven.
                        row.source_timestamp = bar_time if record.source == "tushare:etf_mins:v101" else None
                        row.timestamp_verified = False
                        row.fetched_at = end
                    db.flush()
                inserted += added
                updated += changed
            except Exception as exc:
                failures[code] = type(exc).__name__
                if fetch_error is None:
                    record_provider_audit(db, run_id=run_id, operation="validate_minute_bars",
                                          provider=SimpleNamespace(name=self.provider.name),
                                          error=ProviderError(type(exc).__name__), latency_ms=timer.elapsed_ms)
        db.flush()
        return {"run_id": run_id, "status": "partial" if failures or incomplete else "succeeded",
                "interval": interval, "codes": len(codes), "inserted": inserted, "updated": updated,
                "failures": failures, "skipped_incomplete": incomplete, "actionable": False}

    # ------------------------------------------------------------------ read

    def read_minute_bars(self, db: Session, ts_code: str, interval: str, *, limit: int = 240) -> dict[str, Any]:
        """分钟 bar 读取；无数据时 available=false（日K 永不冒充分钟线）。"""
        if interval not in SUPPORTED_MINUTE_INTERVALS:
            raise ValueError(f"不支持的分钟周期：{interval}")
        instrument = db.scalar(select(Instrument).where(Instrument.ts_code == ts_code.upper()))
        if instrument is None:
            return {"interval": interval, "available": False, "bars": [], "reason": "instrument_not_found"}
        rows = db.scalars(
            select(MarketBar)
            .where(MarketBar.instrument_id == instrument.id, MarketBar.interval == interval)
            .order_by(MarketBar.bar_time.desc())
            .limit(limit)
        ).all()
        rows = list(reversed(rows))
        bars = [
            {
                "date": (row.bar_time.replace(tzinfo=self.tz) if row.bar_time.tzinfo is None else row.bar_time.astimezone(self.tz)).isoformat(),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
                "is_forecast": False,
                "source": row.source,
            }
            for row in rows
        ]
        sources = sorted({row.source for row in rows})
        return {
            "interval": interval,
            "available": bool(bars),
            "actionable": False,
            "qualification": "historical_pit_not_verified",
            "bars": bars,
            "sources": sources,
            "contains_mock": any("mock" in source for source in sources),
            "reason": None if bars else "minute_bars_not_synced",
        }

    @staticmethod
    def daily_bars(db: Session, ts_code: str, *, limit: int = 240) -> list[dict[str, Any]]:
        rows = db.scalars(
            select(DailyBar)
            .join(Instrument, DailyBar.instrument_id == Instrument.id)
            .where(Instrument.ts_code == ts_code.upper())
            .order_by(DailyBar.trade_date.desc())
            .limit(limit)
        ).all()
        return [
            {
                "date": row.trade_date.isoformat(),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
                "is_forecast": False,
            }
            for row in reversed(rows)
        ]

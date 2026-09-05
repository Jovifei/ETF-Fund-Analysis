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
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import DailyBar, Instrument, MarketBar
from app.providers.base import CapabilityUnavailable, MarketProvider

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
        end = datetime.now(self.tz)
        start = end - timedelta(days=window_days)
        inserted = 0
        failures: dict[str, str] = {}
        for code in codes:
            instrument = db.scalar(select(Instrument).where(Instrument.ts_code == code))
            if instrument is None:
                continue
            try:
                records = self.provider.fetch_minute_bars(
                    code, interval, end.date() - timedelta(days=window_days), end.date()
                )
            except (CapabilityUnavailable, Exception) as exc:  # noqa: BLE001 - 单标的失败隔离
                failures[code] = f"{type(exc).__name__}"
                continue
            for record in records:
                bar_time = record.trade_date
                if hasattr(bar_time, "tzinfo") and bar_time.tzinfo is None:
                    bar_time = bar_time.replace(tzinfo=self.tz)
                existing = db.scalar(
                    select(MarketBar).where(
                        MarketBar.instrument_id == instrument.id,
                        MarketBar.interval == interval,
                        MarketBar.bar_time == bar_time,
                    )
                )
                if existing is not None:
                    existing.open = record.open
                    existing.high = record.high
                    existing.low = record.low
                    existing.close = record.close
                    existing.volume = record.volume
                    existing.amount = record.amount
                    existing.source = record.source
                    continue
                db.add(
                    MarketBar(
                        instrument_id=instrument.id,
                        interval=interval,
                        bar_time=bar_time,
                        open=record.open,
                        high=record.high,
                        low=record.low,
                        close=record.close,
                        volume=record.volume,
                        amount=record.amount,
                        source=record.source,
                        source_timestamp=None,
                        timestamp_verified=False,
                    )
                )
                inserted += 1
        db.flush()
        return {
            "run_id": run_id,
            "status": "succeeded" if not failures else "partial",
            "interval": interval,
            "codes": len(codes),
            "inserted": inserted,
            "failures": failures,
        }

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
                "date": row.bar_time.astimezone(self.tz).isoformat(),
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

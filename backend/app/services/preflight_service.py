from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import MarketClock
from app.core.config import Settings, get_settings
from app.services.trading_calendar_service import TradingCalendarService
from app.models import ForecastSnapshot, IndicatorSnapshot, Instrument, QuoteSnapshot


@dataclass(slots=True)
class PreflightResult:
    ok: bool
    missing_core: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _weekday_gap(start: date, end: date) -> int:
    if end <= start:
        return 0
    cursor = start
    count = 0
    while cursor < end:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            count += 1
    return count


class PreflightService:
    """Check the actual data entering the signal engine.

    This deliberately follows the Vibe-Astock preflight principle: a trading
    calendar saying data *should* exist cannot replace validation of the real
    quote, indicator and forecast payloads.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()
        self.clock = MarketClock(self.settings.timezone)
        self.calendar = TradingCalendarService(self.settings)

    def check_instrument(self, db: Session, instrument: Instrument, at: datetime | None = None) -> PreflightResult:
        at = at or datetime.now(self.settings.timezone)
        if at.tzinfo is None:
            at = at.replace(tzinfo=self.settings.timezone)
        missing_core: list[str] = []
        missing_optional: list[str] = []
        warnings: list[str] = []

        indicator = db.scalar(
            select(IndicatorSnapshot)
            .where(IndicatorSnapshot.instrument_id == instrument.id)
            .order_by(IndicatorSnapshot.as_of_date.desc(), IndicatorSnapshot.generated_at.desc())
            .limit(1)
        )
        if not indicator:
            missing_core.append("技术指标")
        else:
            if indicator.data_quality < float(self.strategy["signal"]["minimum_data_quality"]):
                missing_core.append("指标数据质量")
            max_bar_age = int(self.strategy["signal"].get("maximum_bar_age_trading_days", 3))
            gap = _weekday_gap(indicator.as_of_date, at.date())
            if gap > max_bar_age:
                missing_core.append(f"日线/指标已过期 {gap} 个工作日")

        quote = db.scalar(
            select(QuoteSnapshot)
            .where(QuoteSnapshot.instrument_id == instrument.id)
            .order_by(QuoteSnapshot.quote_time.desc())
            .limit(1)
        )
        if not quote:
            missing_core.append("行情快照")
        else:
            quote_time = quote.quote_time
            if quote_time.tzinfo is None:
                quote_time = quote_time.replace(tzinfo=self.settings.timezone)
            age = at - quote_time
            calendar_decision = self.calendar.decision(at.date())
            if not calendar_decision.verified:
                warnings.append("交易日历未完成验证，操作级信号将被阻断")
            if self.clock.price_session_open(at, is_trade_day=calendar_decision.is_trade_day):
                max_age = timedelta(minutes=float(self.strategy["signal"]["maximum_quote_age_minutes"]))
            else:
                # After close and weekends, the last settled close remains useful
                # research evidence. It is not execution-grade, but it should not
                # invalidate an overnight report solely because 12 minutes passed.
                max_age = timedelta(hours=96)
            if age > max_age:
                missing_core.append("行情已过期")
            if not quote.is_realtime or not bool(getattr(quote, "timestamp_verified", False)):
                warnings.append("实时行情或源时间戳未通过资格验证")
            if quote.degraded_reason:
                warnings.append(quote.degraded_reason)

        forecasts = db.scalars(
            select(ForecastSnapshot)
            .where(ForecastSnapshot.instrument_id == instrument.id)
            .order_by(ForecastSnapshot.as_of_date.desc(), ForecastSnapshot.generated_at.desc())
        ).all()
        latest_by_horizon: dict[int, ForecastSnapshot] = {}
        for item in forecasts:
            latest_by_horizon.setdefault(item.horizon, item)
        for horizon in (1, 5, 20):
            item = latest_by_horizon.get(horizon)
            if item is None or item.p_up is None:
                missing_optional.append(f"{horizon}日预测")
        if latest_by_horizon and any(
            item.calibration_status != "calibrated" for item in latest_by_horizon.values()
        ):
            warnings.append("预测模型尚未完成真实基金池 walk-forward 概率校准")

        return PreflightResult(
            ok=not missing_core,
            missing_core=missing_core,
            missing_optional=missing_optional,
            warnings=list(dict.fromkeys(warnings)),
        )

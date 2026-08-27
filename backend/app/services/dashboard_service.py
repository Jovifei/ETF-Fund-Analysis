from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import (
    DailyBar,
    EventLog,
    ForecastSnapshot,
    Holding,
    IndicatorSnapshot,
    Instrument,
    NewsItem,
    ProviderAudit,
    QuoteSnapshot,
    SignalSnapshot,
    TaskRun,
)
from app.services.holding_service import HoldingService


class DashboardService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.holdings = HoldingService()

    @staticmethod
    def _latest_signal(db: Session, instrument_id: int) -> SignalSnapshot | None:
        return db.scalar(
            select(SignalSnapshot)
            .where(SignalSnapshot.instrument_id == instrument_id)
            .order_by(SignalSnapshot.as_of_time.desc())
            .limit(1)
        )

    @staticmethod
    def _latest_quote(db: Session, instrument_id: int) -> QuoteSnapshot | None:
        return db.scalar(
            select(QuoteSnapshot)
            .where(QuoteSnapshot.instrument_id == instrument_id)
            .order_by(QuoteSnapshot.quote_time.desc())
            .limit(1)
        )

    @staticmethod
    def _latest_indicator(db: Session, instrument_id: int) -> IndicatorSnapshot | None:
        return db.scalar(
            select(IndicatorSnapshot)
            .where(IndicatorSnapshot.instrument_id == instrument_id)
            .order_by(IndicatorSnapshot.as_of_date.desc(), IndicatorSnapshot.generated_at.desc())
            .limit(1)
        )

    @staticmethod
    def _latest_forecasts(db: Session, instrument_id: int) -> dict[int, ForecastSnapshot]:
        rows = db.scalars(
            select(ForecastSnapshot)
            .where(ForecastSnapshot.instrument_id == instrument_id)
            .order_by(ForecastSnapshot.as_of_date.desc(), ForecastSnapshot.generated_at.desc())
        ).all()
        result: dict[int, ForecastSnapshot] = {}
        for row in rows:
            result.setdefault(row.horizon, row)
        return result

    def instrument_rows(self, db: Session) -> list[dict[str, Any]]:
        instruments = db.scalars(
            select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)
        ).all()
        holdings_by_instrument = {
            row.instrument_id: row for row in db.scalars(select(Holding)).all()
        }
        rows: list[dict[str, Any]] = []
        for instrument in instruments:
            quote = self._latest_quote(db, instrument.id)
            indicator = self._latest_indicator(db, instrument.id)
            forecasts = self._latest_forecasts(db, instrument.id)
            signal = self._latest_signal(db, instrument.id)
            holding = holdings_by_instrument.get(instrument.id)
            values = indicator.values_json if indicator else {}
            rows.append(
                {
                    "id": instrument.id,
                    "ts_code": instrument.ts_code,
                    "symbol": instrument.symbol,
                    "name": instrument.name,
                    "kind": instrument.kind,
                    "exchange": instrument.exchange,
                    "theme_l1": instrument.theme_l1,
                    "theme_l2": instrument.theme_l2,
                    "benchmark": instrument.benchmark,
                    "quote": {
                        "time": quote.quote_time,
                        "price": quote.price,
                        "pct_change": quote.pct_change,
                        "volume": quote.volume,
                        "amount": quote.amount,
                        "premium_rate": quote.premium_rate,
                        "source": quote.source,
                        "is_realtime": quote.is_realtime,
                        "degraded_reason": quote.degraded_reason,
                    }
                    if quote
                    else None,
                    "indicator": {
                        "as_of_date": indicator.as_of_date,
                        "technical_score": indicator.technical_score,
                        "risk_score": indicator.risk_score,
                        "trend_label": indicator.trend_label,
                        "data_quality": indicator.data_quality,
                        "values": values,
                    }
                    if indicator
                    else None,
                    "forecasts": {
                        str(horizon): {
                            "horizon": item.horizon,
                            "p_up": item.p_up,
                            "expected_return": item.expected_return,
                            "q10": item.q10,
                            "q50": item.q50,
                            "q90": item.q90,
                            "sample_count": item.sample_count,
                            "confidence": item.confidence,
                            "calibration_status": item.calibration_status,
                            "similarity_distance": item.similarity_distance,
                        }
                        for horizon, item in forecasts.items()
                    },
                    "signal": {
                        "time": signal.as_of_time,
                        "state": signal.state,
                        "score": signal.score,
                        "confidence": signal.confidence,
                        "target_weight": signal.target_weight,
                        "first_step_target_weight": signal.first_step_target_weight,
                        "reasons": signal.reasons_json,
                        "risks": signal.risks_json,
                        "evidence": signal.evidence_json,
                        "expires_at": signal.expires_at,
                        "is_actionable": signal.is_actionable,
                        "data_quality": signal.data_quality,
                    }
                    if signal
                    else None,
                    "holding": {
                        "shares": float(holding.shares or 0),
                        "cost_price": float(holding.cost_price or 0),
                        "target_weight": holding.target_weight,
                        "notes": holding.notes,
                    }
                    if holding
                    else None,
                }
            )
        return rows

    def summary(self, db: Session) -> dict[str, Any]:
        rows = self.instrument_rows(db)
        states = Counter(
            row["signal"]["state"] for row in rows if row.get("signal") is not None
        )
        live_quotes = sum(
            1
            for row in rows
            if row.get("quote") and row["quote"].get("is_realtime") and not row["quote"].get("degraded_reason")
        )
        last_quote = max(
            (row["quote"]["time"] for row in rows if row.get("quote")),
            default=None,
        )
        last_signal = max(
            (row["signal"]["time"] for row in rows if row.get("signal")),
            default=None,
        )
        positive = [
            row["quote"]["pct_change"]
            for row in rows
            if row.get("quote") and row["quote"].get("pct_change") is not None
        ]
        up = sum(1 for value in positive if float(value) > 0)
        down = sum(1 for value in positive if float(value) < 0)
        unchanged = len(positive) - up - down
        return {
            "instrument_count": len(rows),
            "live_quote_count": live_quotes,
            "state_counts": dict(states),
            "last_quote_time": last_quote,
            "last_signal_time": last_signal,
            "market_width": {"up": up, "down": down, "unchanged": unchanged},
            "provider": self.settings.market_provider,
            "app_env": self.settings.app_env,
            "is_mock": self.settings.market_provider == "mock",
        }

    def recent_news(self, db: Session, limit: int = 30) -> list[dict[str, Any]]:
        rows = db.scalars(
            select(NewsItem).order_by(NewsItem.published_at.desc()).limit(limit)
        ).all()
        return [
            {
                "id": row.id,
                "source": row.source,
                "title": row.title,
                "summary": row.summary,
                "url": row.url,
                "published_at": row.published_at,
                "facts": row.facts_json,
                "inferences": row.inferences_json,
                "risk_flags": row.risk_flags_json,
                "affected_themes": row.affected_themes_json,
                "impact_direction": row.impact_direction,
                "impact_horizon": row.impact_horizon,
                "impact_score": row.impact_score,
                "llm_model": row.llm_model,
            }
            for row in rows
        ]

    def provider_health(self, db: Session, limit: int = 50) -> list[dict[str, Any]]:
        rows = db.scalars(
            select(ProviderAudit).order_by(ProviderAudit.created_at.desc()).limit(limit)
        ).all()
        return [
            {
                "operation": row.operation,
                "provider": row.provider,
                "status": row.status,
                "latency_ms": row.latency_ms,
                "record_count": row.record_count,
                "reason": row.reason,
                "source_time": row.source_time,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    def task_runs(self, db: Session, limit: int = 30) -> list[dict[str, Any]]:
        rows = db.scalars(select(TaskRun).order_by(TaskRun.started_at.desc()).limit(limit)).all()
        return [
            {
                "run_id": row.run_id,
                "task_name": row.task_name,
                "status": row.status,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
                "result": row.result_json,
                "error": row.error,
            }
            for row in rows
        ]

    def bars(self, db: Session, ts_code: str, limit: int = 260) -> list[dict[str, Any]]:
        instrument = db.scalar(select(Instrument).where(Instrument.ts_code == ts_code.upper()))
        if instrument is None:
            return []
        rows = list(
            reversed(
                db.scalars(
                    select(DailyBar)
                    .where(DailyBar.instrument_id == instrument.id)
                    .order_by(DailyBar.trade_date.desc())
                    .limit(max(10, min(limit, 1500)))
                ).all()
            )
        )
        return [
            {
                "date": row.trade_date.isoformat(),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
                "amount": row.amount,
                "pct_change": row.pct_change,
                "source": row.source,
            }
            for row in rows
        ]

    def bootstrap(self, db: Session) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(self.settings.timezone),
            "summary": self.summary(db),
            "instruments": self.instrument_rows(db),
            "holdings": self.holdings.list(db),
            "news": self.recent_news(db, 30),
            "tasks": self.task_runs(db, 20),
            "provider_health": self.provider_health(db, 30),
        }

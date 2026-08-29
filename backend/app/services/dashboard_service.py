from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import (
    AnalysisRun,
    DailyBar,
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
from app.services.market_context_service import MarketContextService


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
                        # QuoteSnapshot predates an explicit flag; the active
                        # provider provenance is authoritative for this view.
                        "is_mock": self.settings.market_provider == "mock",
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
                            "as_of_date": item.as_of_date,
                            "generated_at": item.generated_at,
                            "model_version": item.model_version,
                            "p_up": item.p_up,
                            "expected_return": item.expected_return,
                            "q10": item.q10,
                            "q50": item.q50,
                            "q90": item.q90,
                            "sample_count": item.sample_count,
                            "confidence": item.confidence,
                            "calibration_status": item.calibration_status,
                            "similarity_distance": item.similarity_distance,
                            # ForecastSnapshot has no schema-backed cutoff field;
                            # diagnostics are informational and cannot override
                            # authoritative presentation provenance.
                            "data_cutoff": None,
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
        limit = max(0, min(int(limit), 1000))
        rows = db.scalars(
            select(NewsItem)
            .order_by(NewsItem.published_at.desc(), NewsItem.id.desc())
            .limit(limit)
            .execution_options(populate_existing=True)
        ).all()
        run_ids = {row.analysis_run_id for row in rows if row.analysis_run_id is not None}
        runs = (
            {
                run.id: run
                for run in db.scalars(
                    select(AnalysisRun)
                    .where(AnalysisRun.id.in_(run_ids))
                    .execution_options(populate_existing=True)
                ).all()
            }
            if run_ids
            else {}
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            run = runs.get(row.analysis_run_id)
            if row.analysis_run_id is None:
                coherent = (row.analysis_source, row.analysis_status) in {
                    (None, None),
                    ("heuristic", "disabled"),
                }
                analysis = {
                    "analysis_run_id": None,
                    "source": row.analysis_source if coherent else None,
                    "status": row.analysis_status if coherent else "invalid_provenance",
                    "provider": None,
                    "model": None,
                    "prompt_version": None,
                    "schema_version": None,
                    "input_hash": None,
                    "analysis_coherent": coherent,
                    "model_analysis": None,
                }
            else:
                coherent = (
                    run is not None
                    and row.analysis_source == run.provider
                    and row.analysis_status == run.status
                )
                analysis = {
                    "analysis_run_id": row.analysis_run_id,
                    "source": run.provider if coherent and run is not None else None,
                    "status": run.status if coherent and run is not None else "invalid_provenance",
                    "provider": run.provider if coherent and run is not None else None,
                    "model": run.model if coherent and run is not None else None,
                    "prompt_version": run.prompt_version if coherent and run is not None else None,
                    "schema_version": run.schema_version if coherent and run is not None else None,
                    "input_hash": run.input_hash if coherent and run is not None else None,
                    "analysis_coherent": coherent,
                    "model_analysis": (
                        run.output_payload
                        if coherent and run is not None and run.status == "completed"
                        else None
                    ),
                }
            result.append(
                {
                "id": row.id,
                "source": row.source,
                "source_id": row.source_id,
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
                "analysis": analysis,
            }
            )
        return result

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
        market_context = MarketContextService(
            # The bootstrap view is read-only and must not refresh or invoke a provider.
            provider=None,  # type: ignore[arg-type]
            settings=self.settings,
        )
        return {
            "generated_at": datetime.now(self.settings.timezone),
            "summary": self.summary(db),
            "instruments": self.instrument_rows(db),
            "market_context": market_context.latest_view(db),
            "holdings": self.holdings.list(db),
            "news": self.recent_news(db, 30),
            "tasks": self.task_runs(db, 20),
            "provider_health": self.provider_health(db, 30),
        }

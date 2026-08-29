from __future__ import annotations

import logging
import re
import threading
from contextlib import contextmanager
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import Instrument, ProviderAudit, TaskRun
from app.providers.factory import create_provider
from app.services.backtest_v05_service import RotationBacktestV05Service
from app.services.event_service import emit_event
from app.services.factor_analysis_service import FactorAnalysisService
from app.services.forecast_service import ForecastService
from app.services.global_model_research_service import GlobalModelResearchService
from app.services.indicator_service import IndicatorService
from app.services.market_context_service import MarketContextService
from app.services.market_service import MarketService
from app.services.news_service import NewsService
from app.services.report_service import ReportService
from app.services.runtime_service import RuntimeService
from app.services.signal_v05_service import SignalV05Service
from app.services.validation_service import ForecastValidationService
from app.research.integrations import capability_matrix

logger = logging.getLogger(__name__)


class UnknownTaskError(ValueError):
    pass


class TaskBusyError(RuntimeError):
    pass


class TaskExecutionError(RuntimeError):
    """Safe task failure carrying only the durable run identity and error class."""

    def __init__(self, run_id: str, failure_class: str) -> None:
        self.run_id = run_id
        self.failure_class = failure_class
        super().__init__(f"task failed: {run_id} ({failure_class})")


_PROCESS_TASK_LOCK = threading.Lock()
_ADVISORY_LOCK_KEY = 271828182


def _failure_class(exc: BaseException) -> str:
    """Return only a type-derived, bounded failure identifier."""
    module = re.sub(r"[^A-Za-z0-9_.]", "", type(exc).__module__ or "builtins")
    name = re.sub(r"[^A-Za-z0-9_]", "", type(exc).__name__ or "Exception")
    identifier = f"{module}.{name}" if module else name
    return identifier[:128]


@contextmanager
def _task_lock(db: Session):
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        acquired = bool(
            db.scalar(text("SELECT pg_try_advisory_xact_lock(:lock_key)"), {"lock_key": _ADVISORY_LOCK_KEY})
        )
        if not acquired:
            raise TaskBusyError("已有数据流水线正在运行，请稍后重试")
        yield
        return
    acquired = _PROCESS_TASK_LOCK.acquire(blocking=False)
    if not acquired:
        raise TaskBusyError("已有数据流水线正在运行，请稍后重试")
    try:
        yield
    finally:
        _PROCESS_TASK_LOCK.release()


class TaskService:
    """Synchronous task orchestrator used by API, CLI and the scheduler process.

    The task layer owns the audit record. Individual services own data-source audit
    and domain events. This keeps jobs reproducible without needing Celery/Redis on
    a small private ECS.
    """

    def __init__(self, settings: Settings | None = None, provider=None) -> None:
        self.settings = settings or get_settings()
        self.provider = provider if provider is not None else create_provider(self.settings)
        self.market = MarketService(self.provider, self.settings)
        self.market_context = MarketContextService(self.provider, self.settings)
        self.indicators = IndicatorService(self.settings)
        self.forecasts = ForecastService(self.settings)
        self.news = NewsService(self.provider, self.settings)
        self.signals = SignalV05Service(self.settings)
        self.runtime = RuntimeService(self.settings)
        self.reports = ReportService(self.settings)
        self.validation = ForecastValidationService(self.settings)
        self.factor_analysis = FactorAnalysisService(self.settings)
        self.global_models = GlobalModelResearchService(self.settings)
        self.backtest = RotationBacktestV05Service(self.settings)

    @property
    def task_names(self) -> tuple[str, ...]:
        return (
            "sync_instruments",
            "refresh_market_context",
            "refresh_bars",
            "refresh_quotes",
            "refresh_indicators",
            "refresh_forecasts",
            "refresh_news",
            "analyze_news",
            "refresh_signals",
            "generate_report",
            "validate_forecasts",
            "backtest_rotation",
            "backtest_ablation",
            "analyze_factors",
            "research_global_models",
            "research_capabilities",
            "bootstrap",
            "full_pipeline",
        )

    def _ensure_instruments(self, db: Session, run_id: str) -> dict | None:
        count = db.scalar(select(Instrument.id).limit(1))
        if count is None:
            return self.market.sync_instruments(db, run_id=run_id)
        return None

    def _refresh_market_context(self, db: Session, run_id: str) -> dict:
        result = self.market_context.refresh(db, run_id=run_id)
        result.update({"status": "succeeded", "unsupported": 0})
        return result

    def _market_context_failure_result(self, db: Session, exc: BaseException, run_id: str) -> dict:
        outcome = getattr(exc, "outcome", None)
        exception_class = getattr(exc, "exception_class", type(exc).__name__)
        unsupported = int(exception_class == "CapabilityUnavailable")
        return {
            "run_id": run_id,
            "status": "failed",
            "configured": outcome.configured if outcome is not None else 0,
            "eligible": outcome.eligible if outcome is not None else 0,
            "observed": outcome.observed if outcome is not None else 0,
            "inserted": outcome.inserted if outcome is not None else 0,
            "missing": outcome.missing if outcome is not None else 0,
            "mock": outcome.mock if outcome is not None else 0,
            "degraded": outcome.degraded if outcome is not None else 0,
            "unsupported": unsupported,
            "provider_calls": outcome.provider_calls if outcome is not None else 0,
            "failure_class": _failure_class(exc),
        }

    def _execute(self, db: Session, task_name: str, run_id: str, **kwargs) -> dict:
        if task_name == "sync_instruments":
            return self.market.sync_instruments(db, codes=kwargs.get("codes"), run_id=run_id)
        if task_name == "refresh_market_context":
            result = self._refresh_market_context(db, run_id)
            emit_event(db, "market_context.updated", dict(result))
            return result
        if task_name == "refresh_bars":
            self._ensure_instruments(db, run_id)
            return self.market.refresh_daily_bars(
                db,
                lookback_days=int(kwargs.get("lookback_days", 900)),
                codes=kwargs.get("codes"),
                run_id=run_id,
            )
        if task_name == "refresh_quotes":
            self._ensure_instruments(db, run_id)
            return self.market.refresh_quotes(db, codes=kwargs.get("codes"), run_id=run_id)
        if task_name == "refresh_indicators":
            return self.indicators.refresh_all(db, run_id=run_id)
        if task_name == "refresh_forecasts":
            return self.forecasts.refresh_all(db, run_id=run_id)
        if task_name == "refresh_news":
            return self.news.refresh(db, since_hours=int(kwargs.get("since_hours", 72)), run_id=run_id)
        if task_name == "analyze_news":
            return self.news.analyze_existing(
                db,
                limit=int(kwargs.get("limit", 30)),
                force=bool(kwargs.get("force", False)),
                run_id=run_id,
            )
        if task_name == "refresh_signals":
            return self.signals.refresh_all(db, run_id=run_id)
        if task_name == "generate_report":
            return self.reports.generate(db, run_id=run_id)
        if task_name == "validate_forecasts":
            return self.validation.run(db, run_id=run_id)
        if task_name == "backtest_rotation":
            return self.backtest.run(db, run_id=run_id)
        if task_name == "backtest_ablation":
            return self.backtest.run_ablation(db, run_id=run_id)
        if task_name == "analyze_factors":
            return self.factor_analysis.run(db, run_id=run_id)
        if task_name == "research_global_models":
            return self.global_models.run(db, run_id=run_id)
        if task_name == "research_capabilities":
            return {"run_id": run_id, "status": "succeeded", "integrations": capability_matrix()}
        if task_name in {"bootstrap", "full_pipeline"}:
            results: dict[str, dict] = {}
            failed_steps: list[str] = []
            results["sync_instruments"] = self.market.sync_instruments(db, run_id=run_id)
            try:
                results["refresh_market_context"] = self._refresh_market_context(db, run_id)
                emit_event(db, "market_context.updated", dict(results["refresh_market_context"]))
            except Exception as exc:
                failed_steps.append("refresh_market_context")
                results["refresh_market_context"] = self._market_context_failure_result(db, exc, run_id)
                emit_event(db, "market_context.updated", dict(results["refresh_market_context"]))
            results["refresh_bars"] = self.market.refresh_daily_bars(
                db,
                lookback_days=int(kwargs.get("lookback_days", 900)),
                run_id=run_id,
            )
            results["refresh_indicators"] = self.indicators.refresh_all(db, run_id=run_id)
            results["refresh_forecasts"] = self.forecasts.refresh_all(db, run_id=run_id)
            try:
                results["refresh_quotes"] = self.market.refresh_quotes(db, run_id=run_id)
            except Exception as exc:  # bars/indicators remain useful in off-market smoke tests
                failed_steps.append("refresh_quotes")
                results["refresh_quotes"] = {
                    "status": "failed",
                    "failure_class": _failure_class(exc),
                }
            try:
                results["refresh_news"] = self.news.refresh(db, since_hours=72, run_id=run_id)
            except Exception as exc:
                failed_steps.append("refresh_news")
                results["refresh_news"] = {
                    "status": "failed",
                    "failure_class": _failure_class(exc),
                }
            results["refresh_signals"] = self.signals.refresh_all(db, run_id=run_id)
            if task_name == "full_pipeline" or bool(kwargs.get("report", True)):
                results["generate_report"] = self.reports.generate(db, run_id=run_id)
            return {
                "run_id": run_id,
                "status": "partial" if failed_steps else "succeeded",
                "failed_steps": failed_steps,
                "steps": results,
            }
        raise UnknownTaskError(f"未知任务 {task_name}; 可用任务: {', '.join(self.task_names)}")

    @staticmethod
    def _persist_failed_run(
        db: Session,
        *,
        run_id: str,
        task_name: str,
        started_at: datetime,
        finished_at: datetime,
        failure_class: str,
        provider_audit: dict | None = None,
    ) -> None:
        """Persist a minimal failure audit after the caller transaction is broken.

        A flush-time database error invalidates the current SQLAlchemy Session
        transaction.  The original TaskRun is intentionally recreated in a
        separate Session so the audit survives that rollback and the caller can
        safely continue using its Session.
        """
        bind = db.get_bind()
        db.rollback()
        recovery_db = Session(bind=bind, autoflush=False, expire_on_commit=False)
        try:
            task = TaskRun(
                run_id=run_id,
                task_name=task_name,
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                result_json={"status": "failed", "failure_class": failure_class},
                error=failure_class,
            )
            recovery_db.add(task)
            recovery_db.flush()
            if provider_audit is not None:
                recovery_db.add(ProviderAudit(run_id=run_id, **provider_audit))
                recovery_db.flush()
            emit_event(
                recovery_db,
                "task.updated",
                {
                    "run_id": run_id,
                    "task_name": task_name,
                    "status": "failed",
                    "failure_class": failure_class,
                },
            )
            if task_name == "refresh_market_context":
                emit_event(
                    recovery_db,
                    "market_context.updated",
                    {
                        "run_id": run_id,
                        "status": "failed",
                        "failure_class": failure_class,
                    },
                )
            recovery_db.commit()
        except Exception:
            recovery_db.rollback()
            logger.error(
                "Task failure audit for %s (%s) could not be committed",
                task_name,
                run_id,
            )
        finally:
            recovery_db.close()
            # Explicitly reset the caller even when the recovery transaction
            # itself encounters an unexpected database error.
            db.rollback()

    def run(self, db: Session, task_name: str, **kwargs) -> dict:
        if task_name not in self.task_names:
            raise UnknownTaskError(task_name)
        with _task_lock(db):
            run_id = kwargs.pop("run_id", None) or uuid4().hex
            started = datetime.now(self.settings.timezone)
            task = TaskRun(
                run_id=run_id,
                task_name=task_name,
                status="running",
                started_at=started,
                result_json={},
            )
            db.add(task)
            db.flush()
            try:
                result = self._execute(db, task_name, run_id, **kwargs)
                task.status = result.get("status", "succeeded")
                task.result_json = result
                task.finished_at = datetime.now(self.settings.timezone)
                db.flush()
                emit_event(
                    db,
                    "task.updated",
                    {
                        "run_id": run_id,
                        "task_name": task_name,
                        "status": task.status,
                        "failed_steps": result.get("failed_steps", []),
                    },
                )
                return result
            except Exception as exc:
                logger.error("Task %s (%s) failed: %s", task_name, run_id, _failure_class(exc))
                failure_class = _failure_class(exc)
                self._persist_failed_run(
                    db,
                    run_id=run_id,
                    task_name=task_name,
                    started_at=started,
                    finished_at=datetime.now(started.tzinfo),
                    failure_class=failure_class,
                    provider_audit=(
                        {
                            "operation": "fetch_market_context",
                            "provider": str(getattr(self.provider, "name", type(self.provider).__name__))[:32],
                            "status": (
                                "unsupported"
                                if getattr(exc, "exception_class", "") == "CapabilityUnavailable"
                                else "failed"
                            ),
                            "record_count": 0,
                            "reason": (
                                "CapabilityUnavailable"
                                if getattr(exc, "exception_class", "") == "CapabilityUnavailable"
                                else failure_class
                            ),
                        }
                        if (
                            task_name == "refresh_market_context"
                            and getattr(getattr(exc, "outcome", None), "provider_calls", 0) > 0
                        )
                        else None
                    ),
                )
                raise TaskExecutionError(run_id, failure_class) from None

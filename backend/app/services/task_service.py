from __future__ import annotations

import logging
import re
import threading
from contextlib import contextmanager
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import Instrument, ProviderAudit, TaskRun
from app.providers.factory import create_provider
from app.research.integrations import capability_matrix
from app.services.backtest_v05_service import RotationBacktestV05Service
from app.services.calibration_service import CalibrationService
from app.services.crosscheck_engine import crosscheck_main
from app.services.decision_board_service import DecisionBoardService
from app.services.event_service import emit_event
from app.services.execution_policy import TaskExecutionPolicy
from app.services.factor_analysis_service import FactorAnalysisService
from app.services.forecast_service import ForecastService
from app.services.global_model_research_service import GlobalModelResearchService
from app.services.indicator_service import IndicatorService
from app.services.market_context_service import MarketContextService
from app.services.market_service import MarketService
from app.services.news_service import NewsService
from app.services.portfolio_optimization_service import PortfolioOptimizationService
from app.services.report_service import ReportService
from app.services.runtime_service import RuntimeService
from app.services.shadow_run_audit_service import ShadowRunAuditService
from app.services.signal_v05_service import SignalV05Service
from app.services.validation_service import ForecastValidationService

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

    def __init__(
        self,
        settings: Settings | None = None,
        provider=None,
        *,
        execution_policy: TaskExecutionPolicy | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.execution_policy = execution_policy or TaskExecutionPolicy()
        self._owns_provider = provider is None
        self.provider = provider if provider is not None else create_provider(self.settings)
        self._closed = False
        self.market = MarketService(
            self.provider, self.settings, persist_provider_audits=self.execution_policy.persist_provider_audits
        )
        self.market_context = MarketContextService(
            self.provider, self.settings, persist_provider_audits=self.execution_policy.persist_provider_audits
        )
        self.indicators = IndicatorService(self.settings)
        self.forecasts = ForecastService(self.settings)
        self.news = NewsService(
            self.provider, self.settings, persist_provider_audits=self.execution_policy.persist_provider_audits
        )
        self.signals = SignalV05Service(self.settings)
        self.runtime = RuntimeService(self.settings)
        self.reports = ReportService(self.settings)
        self.validation = ForecastValidationService(self.settings)
        self.factor_analysis = FactorAnalysisService(self.settings)
        self.global_models = GlobalModelResearchService(self.settings)
        self.calibration = CalibrationService(self.settings)
        self.portfolio = PortfolioOptimizationService(self.settings)
        self.shadow_audit = ShadowRunAuditService(self.settings)
        self.backtest = RotationBacktestV05Service(self.settings)
        self.decision_board = DecisionBoardService(self.settings)

    def close(self) -> None:
        """Close only providers created by this service instance."""
        if self._closed:
            return
        self._closed = True
        if self._owns_provider:
            close = getattr(self.provider, "close", None)
            if callable(close):
                close()

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
            "refresh_decision_board",
            "generate_report",
            "validate_forecasts",
            "calibrate_forecasts",
            "optimize_portfolio",
            "backtest_rotation",
            "backtest_ablation",
            "backtest_crosscheck",
            "shadow_run_audit",
            "analyze_factors",
            "research_global_models",
            "research_capabilities",
            "bootstrap",
            "full_pipeline",
        )

    def _bind_runtime_provider(self, db: Session) -> None:
        settings = getattr(self, "settings", None)
        runtime = getattr(self, "runtime", None)
        if settings is None or runtime is None or settings.market_provider == "mock":
            return
        resolved = self.runtime.resolve_settings(db)
        if (
            resolved.market_provider == self.settings.market_provider
            and (resolved.tushare_token or "") == (self.settings.tushare_token or "")
        ):
            return
        if self._owns_provider:
            close = getattr(self.provider, "close", None)
            if callable(close):
                close()
        self.settings = resolved
        self.runtime = RuntimeService(resolved)
        self.provider = create_provider(resolved)
        self._owns_provider = True
        self.market = MarketService(
            self.provider, resolved, persist_provider_audits=self.execution_policy.persist_provider_audits
        )
        self.market_context = MarketContextService(
            self.provider, resolved, persist_provider_audits=self.execution_policy.persist_provider_audits
        )
        self.news = NewsService(
            self.provider, resolved, persist_provider_audits=self.execution_policy.persist_provider_audits
        )
        self.decision_board = DecisionBoardService(resolved)

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
        self._bind_runtime_provider(db)
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
                lookback_days=int(kwargs.get("lookback_days", 120)),
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
        if task_name == "refresh_decision_board":
            input_result = None
            if bool(kwargs.get("refresh_input", False)):
                input_result = self.market.refresh_quotes(db, run_id=run_id)
                captured = self.decision_board.capture_latest_quotes(db)
                input_result = {**input_result, "provisional_captured": captured}
            built = self.decision_board.refresh(db)
            emit_event(
                db,
                "decision_board.updated",
                {"snapshot_id": built.snapshot.snapshot_id, "generated_at": built.payload["generated_at"], "freshness": built.payload["freshness"]},
            )
            return {
                "run_id": run_id,
                "status": "succeeded",
                "snapshot_id": built.snapshot.snapshot_id,
                "generated_at": built.payload["generated_at"],
                "freshness": built.payload["freshness"],
                "research_only": True,
                "actionable": False,
                "input": input_result,
            }
        if task_name == "generate_report":
            return self.reports.generate(db, run_id=run_id)
        if task_name == "validate_forecasts":
            return self.validation.run(db, run_id=run_id)
        if task_name == "calibrate_forecasts":
            return self.calibration.create_candidate(db, run_id=run_id)
        if task_name == "optimize_portfolio":
            return self.portfolio.run(db, run_id=run_id)
        if task_name == "backtest_rotation":
            return self.backtest.run(db, run_id=run_id)
        if task_name == "backtest_ablation":
            return self.backtest.run_ablation(db, run_id=run_id)
        if task_name == "backtest_crosscheck":
            return crosscheck_main(db, self.settings)
        if task_name == "shadow_run_audit":
            return self.shadow_audit.run(db, run_id=run_id)
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
            requested_run_id = kwargs.pop("run_id", None)
            run_id = requested_run_id or uuid4().hex
            started = datetime.now(self.settings.timezone)
            task = None
            if self.execution_policy.persist_task_runs:
                task = (
                    db.scalar(
                        select(TaskRun).where(
                            TaskRun.run_id == requested_run_id,
                            TaskRun.task_name == task_name,
                            TaskRun.status == "queued",
                        )
                    )
                    if requested_run_id
                    else None
                )
                if task is None and task_name == "refresh_decision_board" and requested_run_id is None:
                    active = db.scalar(
                        select(TaskRun)
                        .where(
                            TaskRun.task_name == task_name,
                            TaskRun.status.in_(("queued", "running")),
                        )
                        .order_by(TaskRun.started_at)
                        .limit(1)
                    )
                    if active is not None:
                        if active.status == "running":
                            raise TaskBusyError("decision-board refresh is already running")
                        task = active
                        run_id = task.run_id
                if task is None:
                    task = TaskRun(
                        run_id=run_id,
                        task_name=task_name,
                        status="running",
                        started_at=started,
                        result_json={},
                    )
                    if task_name == "refresh_decision_board":
                        try:
                            with db.begin_nested():
                                db.add(task)
                                db.flush()
                        except IntegrityError:
                            active = db.scalar(
                                select(TaskRun)
                                .where(
                                    TaskRun.task_name == task_name,
                                    TaskRun.status.in_(("queued", "running")),
                                )
                                .order_by(TaskRun.started_at)
                                .limit(1)
                            )
                            if active is None or active.status == "running":
                                raise TaskBusyError("decision-board refresh is already running") from None
                            task = active
                            run_id = task.run_id
                    else:
                        db.add(task)
                else:
                    task.status = "running"
                    task.started_at = started
                db.flush()
            try:
                result = self._execute(db, task_name, run_id, **kwargs)
                if task is not None:
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
                if self.execution_policy.persist_task_runs:
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

from __future__ import annotations

import logging
import threading
import traceback
from contextlib import contextmanager
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import Instrument, TaskRun
from app.providers.factory import create_provider
from app.services.backtest_v05_service import RotationBacktestV05Service
from app.services.forecast_service import ForecastService
from app.services.indicator_service import IndicatorService
from app.services.market_service import MarketService
from app.services.news_service import NewsService
from app.services.report_service import ReportService
from app.services.runtime_service import RuntimeService
from app.services.signal_v05_service import SignalV05Service
from app.services.validation_service import ForecastValidationService

logger = logging.getLogger(__name__)


class UnknownTaskError(ValueError):
    pass


class TaskBusyError(RuntimeError):
    pass


_PROCESS_TASK_LOCK = threading.Lock()
_ADVISORY_LOCK_KEY = 271828182


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

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.provider = create_provider(self.settings)
        self.market = MarketService(self.provider, self.settings)
        self.indicators = IndicatorService(self.settings)
        self.forecasts = ForecastService(self.settings)
        self.news = NewsService(self.provider, self.settings)
        self.signals = SignalV05Service(self.settings)
        self.runtime = RuntimeService(self.settings)
        self.reports = ReportService(self.settings)
        self.validation = ForecastValidationService(self.settings)
        self.backtest = RotationBacktestV05Service(self.settings)

    @property
    def task_names(self) -> tuple[str, ...]:
        return (
            "sync_instruments",
            "refresh_bars",
            "refresh_quotes",
            "refresh_indicators",
            "refresh_forecasts",
            "refresh_news",
            "refresh_signals",
            "generate_report",
            "validate_forecasts",
            "backtest_rotation",
            "backtest_ablation",
            "bootstrap",
            "full_pipeline",
        )

    def _ensure_instruments(self, db: Session, run_id: str) -> dict | None:
        count = db.scalar(select(Instrument.id).limit(1))
        if count is None:
            return self.market.sync_instruments(db, run_id=run_id)
        return None

    def _execute(self, db: Session, task_name: str, run_id: str, **kwargs) -> dict:
        if task_name == "sync_instruments":
            return self.market.sync_instruments(db, codes=kwargs.get("codes"), run_id=run_id)
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
        if task_name in {"bootstrap", "full_pipeline"}:
            results: dict[str, dict] = {}
            results["sync_instruments"] = self.market.sync_instruments(db, run_id=run_id)
            results["refresh_bars"] = self.market.refresh_daily_bars(
                db,
                lookback_days=int(kwargs.get("lookback_days", 900)),
                run_id=run_id,
            )
            results["refresh_indicators"] = self.indicators.refresh_all(db, run_id=run_id)
            results["refresh_forecasts"] = self.forecasts.refresh_all(db, run_id=run_id)
            try:
                results["refresh_quotes"] = self.market.refresh_quotes(db, run_id=run_id)
            except Exception as exc:
                results["refresh_quotes"] = {"error": f"{type(exc).__name__}: {exc}"}
            try:
                results["refresh_news"] = self.news.refresh(db, since_hours=72, run_id=run_id)
            except Exception as exc:
                results["refresh_news"] = {"error": f"{type(exc).__name__}: {exc}"}
            results["refresh_signals"] = self.signals.refresh_all(db, run_id=run_id)
            if task_name == "full_pipeline" or bool(kwargs.get("report", True)):
                results["generate_report"] = self.reports.generate(db, run_id=run_id)
            return {"run_id": run_id, "steps": results}
        raise UnknownTaskError(f"未知任务 {task_name}; 可用任务: {', '.join(self.task_names)}")

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
                task.status = "succeeded"
                task.result_json = result
                task.finished_at = datetime.now(self.settings.timezone)
                db.flush()
                return result
            except Exception as exc:
                logger.exception("Task %s (%s) failed", task_name, run_id)
                task.status = "failed"
                task.finished_at = datetime.now(self.settings.timezone)
                task.error = f"{type(exc).__name__}: {exc}"
                task.result_json = {"traceback": traceback.format_exc(limit=12)}
                db.flush()
                raise

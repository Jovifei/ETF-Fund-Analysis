"""Process-local, non-actionable demonstration runtime.

The demo runtime intentionally does not reuse the application's database engine.
It is a small, in-memory SQLite database backed by ``StaticPool`` and is guarded
by one process lock.  This makes it impossible for demo tasks to write the
production database, audits, holdings, or report directory by accident.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.models import DailyBar, IndicatorSnapshot, Instrument
from app.providers.mock import MockProvider
from app.services.board_service import BoardService
from app.services.dashboard_service import DashboardService
from app.services.execution_policy import TaskExecutionPolicy
from app.services.signal_grade_service import SignalGradeService
from app.services.task_service import TaskService


@dataclass
class _DemoRuntime:
    engine: Engine
    sessions: sessionmaker[Session]
    settings: Settings
    provider: MockProvider
    task_service: TaskService
    loaded: bool = False
    status: str = "pending"
    load_result: dict[str, Any] | None = None


STATUS_LABELS = {
    "pending": "待初始化",
    "ready": "演示数据已就绪",
    "insufficient": "历史数据不足",
    "provider_unavailable": "数据源不可用",
    "data_anomaly": "数据异常",
}


class DemoService:
    _lock = threading.RLock()
    _runtime: _DemoRuntime | None = None

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @classmethod
    def _new_runtime(cls, settings: Settings) -> _DemoRuntime:
        # This settings copy is only used by isolated services.  In particular,
        # its mock provider cannot be rebound to RuntimeSetting values because
        # TaskService's runtime binding is bypassed for market_provider=mock.
        demo_settings = settings.model_copy(
            update={
                "app_env": "test",
                "market_provider": "mock",
                "allow_mock_fallback": False,
                "database_url": "sqlite://",
                # No demo task may instantiate or reach an external integration,
                # even when the caller supplied adversarial production settings.
                "analysis_enabled": False,
                "analysis_codex_enabled": False,
                "analysis_anthropic_enabled": False,
                "analysis_deepseek_enabled": False,
                "llm_enabled": False,
                "openai_api_key": SecretStr(""),
                "anthropic_api_key": SecretStr(""),
                "deepseek_api_key": SecretStr(""),
                "tushare_token": "",
                "ftshare_enabled": False,
                "ocr_mode": "disabled",
                "ocr_cloud_review_enabled": False,
                "news_rss_urls": "",
            }
        )
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(bind=engine)
        sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
        provider = MockProvider(demo_settings)
        return _DemoRuntime(
            engine=engine,
            sessions=sessions,
            settings=demo_settings,
            provider=provider,
            task_service=TaskService(
                demo_settings,
                provider=provider,
                execution_policy=TaskExecutionPolicy.isolated_demo(),
            ),
        )

    @classmethod
    def _dispose_runtime(cls, runtime: _DemoRuntime | None) -> None:
        if runtime is None:
            return
        runtime.task_service.close()
        close = getattr(runtime.provider, "close", None)
        if callable(close):
            close()
        runtime.engine.dispose()

    @classmethod
    def reset(cls) -> dict[str, Any]:
        """Drop the process-local demo database and return its pending state."""
        with cls._lock:
            runtime = cls._runtime
            cls._runtime = None
            cls._dispose_runtime(runtime)
            return cls._empty_payload()

    @classmethod
    def close(cls) -> None:
        """Dispose resources during an application shutdown or test teardown."""
        with cls._lock:
            runtime = cls._runtime
            cls._runtime = None
            cls._dispose_runtime(runtime)

    @staticmethod
    def _flags() -> dict[str, Any]:
        return {
            "demo": True,
            "is_mock": True,
            "research_only": True,
            "actionable": False,
        }

    @classmethod
    def _empty_payload(cls) -> dict[str, Any]:
        return {
            **cls._flags(),
            "provider": "mock",
            "status": "pending",
            "status_label": STATUS_LABELS["pending"],
            "summary": {
                "instrument_count": 0,
                "live_quote_count": 0,
                "state_counts": {},
                "market_width": {"up": 0, "down": 0, "unchanged": 0},
                **cls._flags(),
            },
            "instruments": [],
            "market_context": [],
            "holdings": [],
            "news": [],
            "tasks": [],
            "provider_health": [],
            "signal_grade": {**cls._flags(), "counts": {}, "groups": {}, "rows": [], "anomaly": []},
            "boards": {**cls._flags(), "industry": [], "concept": [], "counts": {}},
        }

    @classmethod
    def _classify_status(cls, db: Session, load_result: dict[str, Any] | None) -> str:
        if load_result is None:
            return "pending"
        steps = load_result.get("steps") or {}
        bars_result = steps.get("refresh_bars") or {}
        if load_result.get("failure_stage") == "provider" or bars_result.get("failures"):
            return "provider_unavailable"
        instruments = db.scalars(select(Instrument).where(Instrument.enabled.is_(True))).all()
        if not instruments:
            return "pending"
        counts = {
            int(instrument.id): int(
                db.scalar(select(func.count(DailyBar.id)).where(DailyBar.instrument_id == instrument.id)) or 0
            )
            for instrument in instruments
        }
        if any(value < 30 for value in counts.values()):
            return "insufficient"
        valid_indicators = 0
        for instrument in instruments:
            latest = db.scalar(
                select(IndicatorSnapshot)
                .where(IndicatorSnapshot.instrument_id == instrument.id)
                .order_by(IndicatorSnapshot.as_of_date.desc(), IndicatorSnapshot.generated_at.desc())
                .limit(1)
            )
            if latest is not None and latest.as_of_date is not None and isinstance(latest.values_json, dict):
                valid_indicators += 1
        if load_result.get("failure_stage") == "core" or valid_indicators < len(instruments):
            return "data_anomaly"
        return "ready"

    @classmethod
    def _decorate(cls, payload: dict[str, Any], status: str) -> dict[str, Any]:
        flags = cls._flags()
        def mark(value: Any) -> Any:
            if isinstance(value, dict):
                marked = {key: mark(item) for key, item in value.items()}
                marked.update(flags)
                return marked
            if isinstance(value, list):
                return [mark(item) for item in value]
            return value

        decorated = mark(payload)
        decorated.update({"provider": "mock", "status": status, "status_label": STATUS_LABELS[status]})
        return decorated

    @staticmethod
    def _run_pipeline(runtime: _DemoRuntime, db: Session) -> dict[str, Any]:
        """Run the normal derived-data stages without the report-writing stage."""
        steps: dict[str, dict[str, Any]] = {}
        for task_name, kwargs in (
            ("sync_instruments", {}),
            ("refresh_market_context", {}),
            ("refresh_bars", {"lookback_days": 600}),
            ("refresh_indicators", {}),
            ("refresh_forecasts", {}),
            ("refresh_quotes", {}),
            ("refresh_news", {"since_hours": 72}),
            ("refresh_signals", {}),
        ):
            try:
                steps[task_name] = runtime.task_service.run(db, task_name, **kwargs)
            except Exception:
                # Provider stages are the only network-capable boundary in this
                # pipeline.  Core calculation failures remain distinguishable.
                stage = "provider" if task_name in {
                    "sync_instruments", "refresh_market_context", "refresh_bars", "refresh_quotes", "refresh_news"
                } else "core"
                return {"status": "failed", "failure_stage": stage, "steps": steps}
        if (steps.get("refresh_indicators") or {}).get("failures"):
            return {"status": "failed", "failure_stage": "core", "steps": steps}
        return {"status": "succeeded", "steps": steps}

    def load(self) -> dict[str, Any]:
        cls = type(self)
        with cls._lock:
            if cls._runtime is None:
                cls._runtime = cls._new_runtime(self.settings)
            runtime = cls._runtime
            if not runtime.loaded:
                with runtime.sessions() as db:
                    try:
                        # 600 calendar days yields more than 420 weekday bars.
                        # The explicit stages omit the report-writing stage.
                        runtime.load_result = self._run_pipeline(runtime, db)
                        db.commit()
                        runtime.status = self._classify_status(db, runtime.load_result)
                        runtime.loaded = True
                    except Exception:
                        db.rollback()
                        runtime.status = "provider_unavailable"
                        runtime.loaded = True
                        runtime.load_result = {"status": "failed", "steps": {}}
            return cls._read_locked(runtime)

    def bootstrap(self) -> dict[str, Any]:
        cls = type(self)
        with cls._lock:
            if cls._runtime is None or not cls._runtime.loaded:
                return cls._empty_payload()
            return cls._read_locked(cls._runtime)

    @classmethod
    def _read_locked(cls, runtime: _DemoRuntime) -> dict[str, Any]:
        with runtime.sessions() as db:
            payload = DashboardService(runtime.settings).bootstrap(db)
            payload["signal_grade"] = SignalGradeService(runtime.settings).build(db)
            payload["boards"] = BoardService(runtime.settings).build(db)
            instruments = db.scalars(
                select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)
            ).all()
            quality_rows = []
            for instrument in instruments:
                latest = db.scalar(
                    select(IndicatorSnapshot)
                    .where(IndicatorSnapshot.instrument_id == instrument.id)
                    .order_by(IndicatorSnapshot.as_of_date.desc(), IndicatorSnapshot.generated_at.desc())
                    .limit(1)
                )
                quality_rows.append({
                    "ts_code": instrument.ts_code,
                    "bars": int(
                        db.scalar(select(func.count(DailyBar.id)).where(DailyBar.instrument_id == instrument.id)) or 0
                    ),
                    "has_indicator": latest is not None and isinstance(latest.values_json, dict),
                })
            payload["demo_quality"] = {
                "instruments": quality_rows,
            }
            return cls._decorate(payload, runtime.status)

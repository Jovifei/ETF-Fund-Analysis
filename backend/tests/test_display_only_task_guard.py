"""Fail-first: local_bundle display-only mode must reject every cloud research task."""
import pytest

from app.core.config import Settings
from app.services.task_service import DisplayOnlyTaskRejected, TaskService, UnknownTaskError


def _service(source: str) -> TaskService:
    return TaskService(Settings(_env_file=None, market_provider="mock", analysis_enabled=False,
                                workspace_research_source=source))


@pytest.mark.parametrize("task_name", list(TaskService(Settings(_env_file=None, market_provider="mock")).task_names))
def test_local_bundle_rejects_all_tasks_before_touching_db(task_name):
    service = _service("local_bundle")
    try:
        with pytest.raises(DisplayOnlyTaskRejected) as info:
            service.run(None, task_name)  # db never touched: guard runs before lock/session use
        assert info.value.task_name == task_name
    finally:
        service.close()


def test_unknown_task_still_unknown_in_local_bundle():
    service = _service("local_bundle")
    try:
        with pytest.raises(UnknownTaskError):
            service.run(None, "no_such_task")
    finally:
        service.close()


def test_database_mode_not_blocked_by_guard():
    service = _service("database")
    try:
        with pytest.raises(Exception) as info:
            service.run(None, "refresh_quotes")
        assert not isinstance(info.value, DisplayOnlyTaskRejected)
    finally:
        service.close()


def _allow_service(allowed):
    return TaskService(Settings(_env_file=None, market_provider="mock", analysis_enabled=False,
                                workspace_research_source="local_bundle", display_only_allowed_tasks=allowed))


def test_audited_exception_lets_only_refresh_decision_board_past_guard(caplog):
    service = _allow_service(["refresh_decision_board", "refresh_bars"])
    try:
        with caplog.at_level("WARNING"):
            with pytest.raises(Exception) as info:
                service.run(None, "refresh_decision_board")  # passes guard, then fails on db=None
        assert not isinstance(info.value, DisplayOnlyTaskRejected)
        assert any("display_only_exception task=refresh_decision_board" in r.message for r in caplog.records)
        # refresh_bars is not an honoured exception even if configured
        with pytest.raises(DisplayOnlyTaskRejected):
            service.run(None, "refresh_bars")
        # refresh_input would fetch market data in the cloud -> still rejected
        with pytest.raises(DisplayOnlyTaskRejected):
            service.run(None, "refresh_decision_board", refresh_input=True)
    finally:
        service.close()


def test_exception_disabled_by_default():
    service = _service("local_bundle")
    try:
        with pytest.raises(DisplayOnlyTaskRejected):
            service.run(None, "refresh_decision_board")
    finally:
        service.close()


def test_audited_exception_writes_durable_event(db_session):
    from sqlalchemy import select
    from app.models import EventLog
    from app.services.task_service import _audit_display_only_exception
    try:
        _audit_display_only_exception(db_session, "refresh_decision_board", {"run_id": "x"})
        db_session.flush()
        events = db_session.scalars(select(EventLog).where(EventLog.event_type == "task.display_only_exception")).all()
        assert events and events[-1].payload_json["task_name"] == "refresh_decision_board"
    finally:
        db_session.rollback()  # do not leak rows into the shared suite database

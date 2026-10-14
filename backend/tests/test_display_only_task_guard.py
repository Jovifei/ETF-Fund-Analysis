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

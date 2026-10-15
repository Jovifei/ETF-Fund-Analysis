"""One fail-closed boundary for cloud research producers, separate from user data."""
from contextlib import contextmanager
from contextvars import ContextVar


class DisplayOnlyTaskRejected(RuntimeError):
    def __init__(self, task_name: str):
        self.task_name = task_name
        super().__init__(
            f"task {task_name!r} rejected: server runs in local_bundle display-only mode; "
            "research data is computed locally and synced as display bundles"
        )


_maintenance_operations: ContextVar[frozenset[str]] = ContextVar("research_maintenance_operations", default=frozenset())
_BOARD_MAINTENANCE = frozenset({"refresh_decision_board", "support_resistance.capture", "support_resistance.compute"})
DISPLAY_ONLY_EXCEPTION_TASKS = frozenset({"refresh_decision_board"})


def display_only(settings) -> bool:
    return getattr(settings, "workspace_research_source", "database") == "local_bundle"


def require_research_write(settings, operation: str) -> None:
    if display_only(settings) and operation not in _maintenance_operations.get():
        raise DisplayOnlyTaskRejected(operation)


def require_task_write(settings, task_name: str, **kwargs) -> None:
    if display_only(settings):
        allowed = set(getattr(settings, "display_only_allowed_tasks", ()) or ()) & DISPLAY_ONLY_EXCEPTION_TASKS
        if task_name not in allowed or bool(kwargs.get("refresh_input", False)):
            raise DisplayOnlyTaskRejected(task_name)


@contextmanager
def board_maintenance_scope(settings, task_name: str):
    """Only TaskService's explicitly audited board rebuild opens this scope."""
    operations = _BOARD_MAINTENANCE if display_only(settings) and task_name == "refresh_decision_board" else frozenset()
    token = _maintenance_operations.set(operations)
    try:
        yield
    finally:
        _maintenance_operations.reset(token)

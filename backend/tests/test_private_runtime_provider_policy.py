"""Private public-source compute cannot reload a paid token from runtime DB."""
from types import SimpleNamespace

from app.core.config import Settings
from app.services.execution_policy import TaskExecutionPolicy
from app.services import task_service


class OfflineProvider:
    name = "offline-test"
    def close(self):
        pass


def test_private_policy_never_resolves_runtime_credentials(monkeypatch):
    settings = Settings(_env_file=None, market_provider="public_composite", tushare_token="")
    service = task_service.TaskService(settings, provider=OfflineProvider(),
        execution_policy=TaskExecutionPolicy(resolve_runtime_provider=False))
    def forbidden(db):
        raise AssertionError("must not read runtime credentials in private scope")
    service.runtime = SimpleNamespace(resolve_settings=forbidden)
    try:
        service._bind_runtime_provider(object())
        assert service.settings.tushare_token == ""
        assert service.execution_policy.persist_task_runs is True
        assert service.execution_policy.persist_provider_audits is True
    finally:
        service.close()


def test_default_policy_keeps_existing_runtime_resolution(monkeypatch):
    settings = Settings(_env_file=None, market_provider="public_composite", tushare_token="")
    calls = []
    resolved = settings.model_copy(update={"tushare_token": "synthetic-key-only"})
    service = task_service.TaskService(settings, provider=OfflineProvider())
    service.runtime = SimpleNamespace(resolve_settings=lambda db: calls.append("resolved") or resolved)
    monkeypatch.setattr(task_service, "create_provider", lambda cfg: calls.append(bool(cfg.tushare_token)) or OfflineProvider())
    try:
        service._bind_runtime_provider(object())
        assert calls == ["resolved", True]
        assert service.settings.tushare_token == "synthetic-key-only"
    finally:
        service.close()

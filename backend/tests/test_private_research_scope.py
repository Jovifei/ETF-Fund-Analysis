"""Owner execution consent is not a fabricated data license or unit certificate."""
import pytest

from app.workspace.local_compute import validate_provider_admission


@pytest.mark.parametrize("provider", ["public_composite", "akshare"])
def test_explicit_private_scope_permits_existing_price_research_without_certification(provider):
    result = validate_provider_admission(provider, private_research=True)
    assert result["operation_permitted"] is True
    assert result["admitted"] is False
    assert result["license_status"] == result["source_qualification"] == "UNKNOWN"
    assert result["source_timestamp_quality"] == "UNKNOWN"
    assert result["usage_scope"] == "owner_private_research"
    assert result["actionable"] is False


def test_no_implicit_private_scope():
    assert not validate_provider_admission("public_composite")["operation_permitted"]


@pytest.mark.parametrize("provider", ["tushare", "ftshare", "composite", "other"])
def test_private_scope_does_not_expand_to_other_providers(provider):
    assert not validate_provider_admission(provider, private_research=True)["operation_permitted"]


@pytest.mark.parametrize("status", ["DENIED", "REVOKED", "EXPIRED"])
def test_explicit_restrictions_are_not_bypassed_by_private_scope(status):
    evidence = {"provider": "public_composite", "interfaces": [{"name": "daily_bars", "display": {"status": status}}]}
    assert not validate_provider_admission("public_composite", evidence=evidence, private_research=True)["operation_permitted"]


def test_explicit_expired_evidence_is_not_bypassed():
    evidence = {"provider": "public_composite", "interfaces": [{"name": "daily_bars", "valid_until": "2020-01-01T00:00:00+00:00"}]}
    assert not validate_provider_admission("public_composite", evidence=evidence, private_research=True)["operation_permitted"]


def test_mock_cannot_acquire_live_private_scope():
    with pytest.raises(ValueError, match="mock provider"):
        validate_provider_admission("mock", private_research=True)


def test_optional_failure_continues_but_core_partial_stops_without_paid_fallback(monkeypatch):
    from app.core.config import Settings
    from app.workspace.local_compute import compute_local
    from app.services import task_service

    seen = []
    class StubTasks:
        def __init__(self, settings, *, execution_policy=None):
            assert settings.tushare_token == "" and settings.ftshare_enabled is False
            assert execution_policy.resolve_runtime_provider is False
            assert execution_policy.persist_task_runs is True and execution_policy.persist_provider_audits is True
        def run(self, db, task, **kwargs):
            seen.append(task)
            if task == "refresh_market_context":
                raise RuntimeError("synthetic_optional_failure")
            return {"status": "partial" if task == "refresh_quotes" else "succeeded"}
        def close(self):
            pass

    monkeypatch.setattr(task_service, "TaskService", StubTasks)
    settings = Settings(_env_file=None, market_provider="public_composite", database_url="sqlite://",
                        tushare_token="synthetic_test_only", ftshare_enabled=True)
    results = compute_local(settings, ["510300.SH"], private_research=True)
    assert seen == ["refresh_market_context", "refresh_bars", "refresh_quotes"]
    assert results[0]["required"] is False and results[0]["availability"] == "unavailable"
    assert results[-1]["required"] is True and results[-1]["status"] == "partial"
    assert settings.tushare_token == "synthetic_test_only" and settings.ftshare_enabled is True

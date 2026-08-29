from __future__ import annotations

import sys

import pytest
from app.analysis.contracts import (
    AnalysisEnvelope,
    AnalysisOutput,
    AnalysisProvider,
    AnalysisStatus,
    DataProvenance,
    ForecastFact,
    IndicatorFact,
    InstrumentIdentity,
    PortfolioExposure,
    VerifiedAnalysisInput,
)
from app.core.config import Settings
from pydantic import ValidationError


def _output_payload() -> dict:
    return {
        "facts": ["事实"],
        "inferences": ["推断"],
        "risk_flags": ["风险"],
        "affected_themes": ["半导体"],
        "impact_horizon": "1w",
        "evidence_ids": ["news:1"],
        "confidence_statement": "仅作研究候选，不构成交易建议",
    }


def _input_payload() -> dict:
    return {
        "instrument": {
            "standard_code": "512480.SH",
            "name": "半导体 ETF",
            "theme_l1": "科技",
            "theme_l2": "半导体",
            "configured_benchmark": "000300.SH",
        },
        "provenance": {
            "source": "composite",
            "source_timestamp": "2026-08-28T09:30:00+08:00",
            "data_cutoff": "2026-08-28T09:29:00+08:00",
            "freshness": "fresh",
            "degraded": False,
            "mock": False,
            "strategy_version": "strategy-v1",
            "indicator_version": "indicator-v1",
            "forecast_version": "forecast-v1",
        },
        "indicators": [{"name": "risk_score", "value": 0.2, "unit": "score", "version": "indicator-v1"}],
        "signal_state": "hold",
        "portfolio_exposure": {"shares": 10, "cost": 1.2, "current_weight": 0.1, "target_weight": 0.2},
        "forecast_statistics": [
            {
                "horizon": "1w",
                "p_up": 0.6,
                "expected_return": 0.02,
                "q10": -0.03,
                "q50": 0.01,
                "q90": 0.06,
                "sample_count": 30,
                "confidence": "low",
                "model_version": "forecast-v1",
                "calibration_status": "not_calibrated",
                "data_cutoff": "2026-08-28T09:29:00+08:00",
            }
        ],
        "news_title": "行业新闻",
        "news_body": "未经验证的新闻正文",
        "evidence_ids": ["news:1", "quote:1"],
        "prompt_version": "analysis-v1",
        "schema_version": "analysis-v1",
    }


def _settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_analysis_output_allows_only_text_and_provenance_fields() -> None:
    result = AnalysisOutput.model_validate(_output_payload())
    assert set(result.model_fields_set) == {
        "facts",
        "inferences",
        "risk_flags",
        "affected_themes",
        "impact_horizon",
        "evidence_ids",
        "confidence_statement",
    }


def test_analysis_output_accepts_explicit_provenance_fields() -> None:
    result = AnalysisOutput.model_validate(
        {
            **_output_payload(),
            "provider": "codex_openai_responses",
            "model": "verified-model",
            "prompt_version": "analysis-v1",
        }
    )
    assert result.provider is AnalysisProvider.CODEX_OPENAI_RESPONSES
    assert result.model == "verified-model"


def test_analysis_output_requires_substantive_text_and_confidence() -> None:
    with pytest.raises(ValidationError):
        AnalysisOutput.model_validate({**_output_payload(), "facts": [], "inferences": [], "risk_flags": []})
    with pytest.raises(ValidationError):
        AnalysisOutput.model_validate({**_output_payload(), "confidence_statement": "   "})


@pytest.mark.parametrize("field", ["impact_score", "price", "expected_return", "p_up", "position", "trade_action"])
def test_analysis_output_rejects_numeric_decision_and_arbitrary_fields(field: str) -> None:
    payload = _output_payload()
    payload[field] = 1
    with pytest.raises(ValidationError):
        AnalysisOutput.model_validate(payload)


def test_verified_input_forbids_extra_fields_and_hashes_equivalent_ordering() -> None:
    first = VerifiedAnalysisInput.model_validate(_input_payload())
    reordered = dict(reversed(list(_input_payload().items())))
    second = VerifiedAnalysisInput.model_validate(reordered)
    assert first.canonical_hash == second.canonical_hash
    with pytest.raises(ValidationError):
        VerifiedAnalysisInput.model_validate({**_input_payload(), "price": 1})


def test_analysis_envelope_carries_provenance_without_raw_exception() -> None:
    envelope = AnalysisEnvelope(
        status=AnalysisStatus.COMPLETED,
        provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
        model="verified-model",
        latency_ms=12.5,
        input_hash=VerifiedAnalysisInput(**_input_payload()).canonical_hash,
        prompt_version="analysis-v1",
        schema_version="analysis-v1",
        output=AnalysisOutput(**_output_payload()),
        result_hash=AnalysisOutput(**_output_payload()).result_hash,
    )
    assert envelope.result_hash
    assert "exception" not in type(envelope).model_fields
    with pytest.raises(ValidationError):
        AnalysisEnvelope.model_validate({**envelope.model_dump(), "raw_exception": "secret"})


@pytest.mark.parametrize(
    "flags",
    [
        {},
        {"analysis_codex_enabled": True, "analysis_anthropic_enabled": True},
        {"analysis_anthropic_enabled": True},
    ],
)
def test_enabled_analysis_requires_exactly_one_matching_provider_flag(flags: dict) -> None:
    with pytest.raises(ValidationError):
        _settings(
            analysis_enabled=True,
            analysis_primary_provider="codex_openai_responses",
            analysis_primary_model="verified-model",
            openai_api_key="server-secret",
            **flags,
        )


def test_deepseek_primary_rejects_anthropic_messages_mode() -> None:
    with pytest.raises(ValidationError):
        _settings(
            analysis_enabled=True,
            analysis_primary_provider="deepseek_openai_compatible",
            analysis_primary_model="verified-model",
            analysis_primary_mode="messages",
            analysis_deepseek_enabled=True,
            deepseek_api_key="server-secret",
        )


@pytest.mark.parametrize(
    "failure_class",
    [
        "TimeoutError",
        "httpx.TimeoutException",
    ],
)
def test_analysis_envelope_accepts_sanitized_failure_class_identifier(failure_class: str) -> None:
    envelope = {
        "status": AnalysisStatus.ANALYSIS_UNAVAILABLE,
        "provider": AnalysisProvider.CODEX_OPENAI_RESPONSES,
        "model": "verified-model",
        "latency_ms": 1,
        "input_hash": "a" * 64,
        "prompt_version": "analysis-v1",
        "schema_version": "analysis-v1",
        "failure_class": failure_class,
    }
    assert AnalysisEnvelope.model_validate(envelope).failure_class == failure_class


@pytest.mark.parametrize(
    "failure_class",
    ["TimeoutError: secret", "has spaces", "a=b", "https://example.invalid", "token-secret", "TimeoutError\nraw"],
)
def test_analysis_envelope_rejects_raw_or_secret_bearing_failure_text(failure_class: str) -> None:
    with pytest.raises(ValidationError):
        AnalysisEnvelope.model_validate(
            {
                "status": AnalysisStatus.ANALYSIS_UNAVAILABLE,
                "provider": AnalysisProvider.CODEX_OPENAI_RESPONSES,
                "model": "verified-model",
                "latency_ms": 1,
                "input_hash": "a" * 64,
                "prompt_version": "analysis-v1",
                "schema_version": "analysis-v1",
                "failure_class": failure_class,
            }
        )


def test_enabled_analysis_requires_one_configured_primary() -> None:
    settings = _settings(
        analysis_enabled=True,
        analysis_primary_provider="codex_openai_responses",
        analysis_primary_model="verified-model",
        analysis_codex_enabled=True,
        openai_api_key="server-secret",
    )
    assert settings.analysis_primary_provider == AnalysisProvider.CODEX_OPENAI_RESPONSES

    with pytest.raises(ValidationError):
        _settings(
            analysis_enabled=True,
            analysis_primary_provider="codex_openai_responses",
            analysis_primary_model="verified-model",
            analysis_codex_enabled=True,
            analysis_anthropic_enabled=True,
            openai_api_key="server-secret",
            anthropic_api_key="other-secret",
        )


@pytest.mark.parametrize(
    "values",
    [
        {"analysis_primary_provider": "unknown"},
        {
            "analysis_primary_provider": "codex_openai_responses",
            "analysis_codex_enabled": True,
            "openai_api_key": "server-secret",
        },
        {
            "analysis_primary_provider": "codex_openai_responses",
            "analysis_primary_model": "verified-model",
            "analysis_codex_enabled": True,
        },
        {
            "analysis_primary_provider": "codex_openai_responses",
            "analysis_primary_model": "verified-model",
            "analysis_primary_mode": "chat_completions",
            "analysis_codex_enabled": True,
            "openai_api_key": "server-secret",
        },
    ],
)
def test_enabled_analysis_rejects_unknown_or_incomplete_primary(values: dict) -> None:
    with pytest.raises(ValidationError):
        _settings(analysis_enabled=True, **values)


def test_verified_input_uses_frozen_typed_nested_models_and_rejects_arbitrary_keys() -> None:
    identity = InstrumentIdentity(
        standard_code="512480.SH",
        name="半导体 ETF",
        theme_l1="科技",
        theme_l2="半导体",
        configured_benchmark="000300.SH",
    )
    provenance = DataProvenance(
        source="composite",
        source_timestamp="2026-08-28T09:30:00+08:00",
        data_cutoff="2026-08-28T09:29:00+08:00",
        freshness="fresh",
        degraded=False,
        mock=False,
        strategy_version="strategy-v1",
        indicator_version="indicator-v1",
        forecast_version="forecast-v1",
    )
    indicator = IndicatorFact(name="risk_score", value=0.2, unit="score", version="indicator-v1")
    exposure = PortfolioExposure(shares=10, cost=1.2, current_weight=0.1, target_weight=0.2)
    forecast = ForecastFact(
        horizon="1w",
        p_up=0.6,
        expected_return=0.02,
        q10=-0.03,
        q50=0.01,
        q90=0.06,
        sample_count=30,
        confidence="low",
        model_version="forecast-v1",
        calibration_status="not_calibrated",
        data_cutoff="2026-08-28T09:29:00+08:00",
    )
    result = VerifiedAnalysisInput(
        instrument=identity,
        provenance=provenance,
        indicators=(indicator,),
        signal_state="hold",
        portfolio_exposure=exposure,
        forecast_statistics=(forecast,),
        news_title="行业新闻",
        news_body="未经验证的新闻正文",
        evidence_ids=("news:1", "quote:1"),
        prompt_version="analysis-v1",
        schema_version="analysis-v1",
    )
    assert result.canonical_hash == VerifiedAnalysisInput.model_validate(result.model_dump()).canonical_hash
    with pytest.raises(ValidationError):
        VerifiedAnalysisInput.model_validate({**result.model_dump(), "credentials": "secret"})
    with pytest.raises(ValidationError):
        IndicatorFact.model_validate({"name": "x", "value": 1, "metadata": {"secret": "x"}})


def test_forecast_numeric_facts_are_input_only() -> None:
    ForecastFact(
        horizon="1w",
        p_up=0.5,
        expected_return=0.0,
        q10=-0.1,
        q50=0.0,
        q90=0.1,
        sample_count=10,
        confidence="low",
        model_version="v1",
        calibration_status="not_calibrated",
        data_cutoff="2026-08-28T00:00:00Z",
    )
    for field in ("p_up", "expected_return", "q10", "q50", "q90", "sample_count"):
        with pytest.raises(ValidationError):
            AnalysisOutput.model_validate({**_output_payload(), field: 0.5})


def test_nested_input_is_frozen_and_hash_is_cross_process_stable() -> None:
    payload = {
        "instrument": {
            "standard_code": "512480.SH",
            "name": "半导体 ETF",
            "theme_l1": "科技",
            "theme_l2": "半导体",
            "configured_benchmark": "000300.SH",
        },
        "provenance": {
            "source": "composite",
            "source_timestamp": "2026-08-28T09:30:00+08:00",
            "data_cutoff": "2026-08-28T09:29:00+08:00",
            "freshness": "fresh",
            "strategy_version": "s1",
            "indicator_version": "i1",
            "forecast_version": "f1",
        },
        "indicators": [{"name": "risk_score", "value": 0.2}],
        "evidence_ids": ["news:1"],
    }
    result = VerifiedAnalysisInput.model_validate(payload)
    original_hash = result.canonical_hash
    with pytest.raises(ValidationError):
        result.instrument.name = "changed"
    assert result.canonical_hash == original_hash
    script = (
        "import sys; from app.analysis.contracts import VerifiedAnalysisInput; "
        "print(VerifiedAnalysisInput.model_validate(eval(sys.stdin.read())).canonical_hash)"
    )
    child = __import__("subprocess").run(
        [sys.executable, "-c", script],
        input=repr(dict(reversed(list(payload.items())))),
        text=True,
        capture_output=True,
        check=True,
        env={**__import__("os").environ, "PYTHONPATH": "backend"},
        cwd=str(__import__("pathlib").Path.cwd()),
    )
    assert child.stdout.strip() == original_hash


def test_typed_contract_rejects_sets_and_arbitrary_objects() -> None:
    with pytest.raises(ValidationError):
        VerifiedAnalysisInput.model_validate({"evidence_ids": {"news:1"}})
    with pytest.raises(ValidationError):
        VerifiedAnalysisInput.model_validate({"indicators": [{"name": "x", "value": object()}]})


def test_envelope_hash_format_matching_and_status_coherence() -> None:
    valid_input_hash = "a" * 64
    output = AnalysisOutput(**_output_payload())
    base = {
        "provider": AnalysisProvider.CODEX_OPENAI_RESPONSES,
        "model": "verified-model",
        "latency_ms": 1,
        "input_hash": valid_input_hash,
        "prompt_version": "analysis-v1",
        "schema_version": "analysis-v1",
    }
    completed = AnalysisEnvelope(
        **base,
        status=AnalysisStatus.COMPLETED,
        output=output,
        result_hash=output.result_hash,
    )
    assert completed.result_hash == output.result_hash
    with pytest.raises(ValidationError):
        AnalysisEnvelope(**base, status=AnalysisStatus.COMPLETED, output=output)
    with pytest.raises(ValidationError):
        AnalysisEnvelope(**base, status=AnalysisStatus.COMPLETED, output=output, result_hash="b" * 64)
    with pytest.raises(ValidationError):
        AnalysisEnvelope(**{**base, "input_hash": "not-a-hash"}, status=AnalysisStatus.COMPLETED, output=output, result_hash=output.result_hash)
    for status in (AnalysisStatus.ANALYSIS_UNAVAILABLE, AnalysisStatus.INVALID_RESPONSE, AnalysisStatus.FAILED):
        AnalysisEnvelope(**base, status=status, failure_class="TimeoutError")
        with pytest.raises(ValidationError):
            AnalysisEnvelope(**base, status=status, output=output, result_hash=output.result_hash, failure_class="TimeoutError")
        with pytest.raises(ValidationError):
            AnalysisEnvelope(**base, status=status)


def test_disabled_analysis_does_not_require_a_key() -> None:
    settings = _settings(analysis_enabled=False)
    assert settings.analysis_enabled is False


@pytest.mark.parametrize(
    "field",
    [
        "analysis_codex_timeout_seconds",
        "analysis_anthropic_timeout_seconds",
        "analysis_deepseek_timeout_seconds",
    ],
)
@pytest.mark.parametrize("value", [0, -1, 301, float("inf"), float("nan"), 1e99])
def test_analysis_provider_timeout_is_finite_and_bounded(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        _settings(**{field: value})


def test_analysis_max_input_chars_is_bounded() -> None:
    assert _settings(analysis_max_input_chars=120000).analysis_max_input_chars == 120000
    for value in (120001, 10**99):
        with pytest.raises(ValidationError):
            _settings(analysis_max_input_chars=value)


@pytest.mark.parametrize("field", ["analysis_primary_model", "analysis_prompt_version", "analysis_schema_version"])
def test_analysis_identifiers_are_limited_to_512_characters(field: str) -> None:
    assert getattr(_settings(**{field: "x" * 512}), field) == "x" * 512
    with pytest.raises(ValidationError):
        _settings(**{field: "x" * 513})


def test_legacy_llm_settings_map_to_compatible_primary_without_repr_secret() -> None:
    settings = _settings(
        llm_enabled=True,
        llm_api_key="legacy-secret",
        llm_model="legacy-model",
        llm_api_mode="chat_completions",
    )
    assert settings.analysis_enabled is True
    assert settings.analysis_primary_provider == AnalysisProvider.DEEPSEEK_OPENAI_COMPATIBLE
    assert settings.analysis_primary_model == "legacy-model"
    assert "legacy-secret" not in repr(settings)


def test_legacy_key_is_excluded_from_settings_dumps() -> None:
    settings = _settings(llm_api_key="legacy-secret")
    assert "llm_api_key" not in settings.model_dump()
    assert "legacy-secret" not in settings.model_dump_json()


def test_explicit_new_analysis_config_is_not_overridden_by_legacy_bridge() -> None:
    with pytest.raises(ValidationError):
        _settings(
            llm_enabled=True,
            llm_api_key="legacy-secret",
            llm_model="legacy-model",
            llm_api_mode="responses",
            analysis_enabled=True,
            analysis_primary_provider="codex_openai_responses",
            analysis_primary_model="new-model",
            analysis_primary_mode="responses",
            analysis_codex_enabled=True,
            openai_api_key="new-secret",
        )


def test_analysis_model_id_rejects_whitespace_only() -> None:
    with pytest.raises(ValidationError):
        _settings(
            analysis_enabled=True,
            analysis_primary_provider="codex_openai_responses",
            analysis_primary_model="   ",
            analysis_primary_mode="responses",
            analysis_codex_enabled=True,
            openai_api_key="server-secret",
        )


@pytest.mark.parametrize(
    "partial_analysis",
    [
        {"analysis_primary_provider": "codex_openai_responses"},
        {"openai_api_key": "new-secret"},
        {"analysis_primary_model": "new-model"},
        {"analysis_primary_mode": "responses"},
        {"analysis_codex_enabled": True},
    ],
)
def test_legacy_and_any_partial_new_analysis_config_is_rejected(partial_analysis: dict) -> None:
    with pytest.raises(ValidationError):
        _settings(llm_enabled=True, llm_api_key="legacy-secret", llm_model="legacy-model", **partial_analysis)


def test_complete_mixed_legacy_and_new_analysis_config_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(
            llm_enabled=True,
            llm_api_key="same-secret",
            llm_model="same-model",
            llm_api_mode="responses",
            analysis_enabled=True,
            analysis_primary_provider="codex_openai_responses",
            analysis_primary_model="same-model",
            analysis_primary_mode="responses",
            analysis_codex_enabled=True,
            openai_api_key="same-secret",
        )


def test_unrelated_existing_string_field_preserves_whitespace() -> None:
    settings = _settings(app_name="  custom app  ")
    assert settings.app_name == "  custom app  "


def test_analysis_identifiers_are_trimmed_before_validation() -> None:
    settings = _settings(
        analysis_enabled=True,
        analysis_primary_provider=" codex_openai_responses ",
        analysis_primary_model=" verified-model ",
        analysis_primary_mode=" responses ",
        analysis_prompt_version=" prompt-v1 ",
        analysis_codex_enabled=True,
        openai_api_key="server-secret",
    )
    assert settings.analysis_primary_provider == AnalysisProvider.CODEX_OPENAI_RESPONSES
    assert settings.analysis_primary_model == "verified-model"
    assert settings.analysis_primary_mode == "responses"
    assert settings.analysis_prompt_version == "prompt-v1"


@pytest.mark.parametrize(
    "factory,field",
    [
        (lambda: IndicatorFact(name="rsi", value="0.2"), "indicator.value"),
        (lambda: PortfolioExposure(shares="10"), "portfolio.shares"),
        (
            lambda: ForecastFact(
                horizon="1w",
                p_up="0.5",
                model_version="v1",
                calibration_status="not_calibrated",
            ),
            "forecast.p_up",
        ),
        (
            lambda: ForecastFact(
                horizon="1w",
                sample_count="10",
                model_version="v1",
                calibration_status="not_calibrated",
            ),
            "forecast.sample_count",
        ),
    ],
)
def test_numeric_fact_fields_reject_numeric_strings(factory, field: str) -> None:
    with pytest.raises(ValidationError, match=field.split(".")[-1]):
        factory()


def test_design_environment_aliases_configure_analysis_without_key_repr(monkeypatch) -> None:
    monkeypatch.setenv("ANALYSIS_ENABLED", "true")
    monkeypatch.setenv("ANALYSIS_PRIMARY_PROVIDER", "codex_openai_responses")
    monkeypatch.setenv("ANALYSIS_PRIMARY_MODEL", "env-model")
    monkeypatch.setenv("ANALYSIS_PRIMARY_MODE", "responses")
    monkeypatch.setenv("ANALYSIS_CODEX_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "env-secret")
    settings = Settings(_env_file=None)
    assert settings.analysis_primary_model == "env-model"
    assert "env-secret" not in repr(settings)

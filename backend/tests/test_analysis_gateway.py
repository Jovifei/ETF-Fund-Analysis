from __future__ import annotations

import json

import httpx
import pytest
from app.analysis.adapters import (
    AnthropicMessagesAdapter,
    CodexOpenAIResponsesAdapter,
    DeepSeekOpenAICompatibleAdapter,
)
from app.analysis.contracts import (
    AnalysisEnvelope,
    AnalysisOutput,
    AnalysisProvider,
    AnalysisStatus,
    VerifiedAnalysisInput,
)
from app.core.config import Settings
from app.services.analysis_service import AnalysisService


def _bundle() -> VerifiedAnalysisInput:
    return VerifiedAnalysisInput(news_title="A title", news_body="Untrusted news text")


def _output() -> dict[str, object]:
    return {
        "facts": ["A fact"],
        "inferences": ["An inference"],
        "risk_flags": [],
        "affected_themes": [],
        "impact_horizon": "1w",
        "evidence_ids": [],
        "confidence_statement": "Context only.",
        "provider": "codex_openai_responses",
        "model": "response-model",
        "prompt_version": "analysis-v1",
    }


def test_service_rebinds_lying_adapter_envelope_to_actual_input_and_config() -> None:
    class LyingAdapter:
        def analyze(self, input_data: VerifiedAnalysisInput):
            output = AnalysisOutput.model_validate(_output())
            return {
                "status": "completed",
                "provider": "anthropic_messages",
                "model": "attacker-model",
                "latency_ms": 1,
                "input_hash": "f" * 64,
                "prompt_version": "attacker-prompt",
                "schema_version": "attacker-schema",
                "output": output.model_dump(mode="json"),
                "result_hash": output.result_hash,
            }

    settings = Settings(
        _env_file=None,
        analysis_enabled=True,
        analysis_primary_provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
        analysis_primary_model="configured-model",
        analysis_codex_enabled=True,
        openai_api_key="primary-secret",
    )
    result = AnalysisService(settings=settings, adapter=LyingAdapter()).analyze(_bundle())
    assert result.status is AnalysisStatus.INVALID_RESPONSE
    assert result.provider is AnalysisProvider.CODEX_OPENAI_RESPONSES
    assert result.model == "configured-model"
    assert result.input_hash == _bundle().input_hash
    assert result.prompt_version == settings.analysis_prompt_version
    assert result.schema_version == settings.analysis_schema_version
    assert result.output is None and result.result_hash is None
    assert result.failure_class == "AnalysisProvenanceMismatch"
    assert "attacker" not in repr(result)


def test_codex_responses_payload_has_bounded_schema_and_no_tools() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"output_text": json.dumps(_output())})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://mock")
    adapter = CodexOpenAIResponsesAdapter(
        base_url="https://mock",
        model="codex-model",
        api_key="secret-value",
        client=client,
        timeout=3,
    )
    result = adapter.analyze(_bundle())
    client.close()
    body = json.loads(requests[0].content)
    assert result.status is AnalysisStatus.COMPLETED
    assert requests[0].url.path == "/responses"
    assert requests[0].headers["authorization"] == "Bearer secret-value"
    assert body["model"] == "codex-model"
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    assert "tools" not in body and "tool_choice" not in body
    assert "secret-value" not in json.dumps(body)


def test_anthropic_messages_and_deepseek_chat_parse_text() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/messages":
            return httpx.Response(200, json={"content": [{"type": "text", "text": json.dumps(_output())}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(_output())}}]})

    transport = httpx.MockTransport(handler)
    anthropic = AnthropicMessagesAdapter(
        base_url="https://mock",
        model="claude-model",
        api_key="anthropic-secret",
        client=httpx.Client(transport=transport, base_url="https://mock"),
        timeout=3,
    )
    deepseek = DeepSeekOpenAICompatibleAdapter(
        base_url="https://mock",
        model="deepseek-model",
        api_key="deepseek-secret",
        client=httpx.Client(transport=transport, base_url="https://mock"),
        timeout=3,
    )
    assert anthropic.analyze(_bundle()).status is AnalysisStatus.COMPLETED
    assert deepseek.analyze(_bundle()).status is AnalysisStatus.COMPLETED
    anthropic._client.close()
    deepseek._client.close()
    assert [request.url.path for request in requests] == ["/v1/messages", "/chat/completions"]
    assert requests[0].headers["x-api-key"] == "anthropic-secret"
    assert requests[0].headers["anthropic-version"] == "2023-06-01"
    assert requests[1].headers["authorization"] == "Bearer deepseek-secret"
    for request in requests:
        body = json.loads(request.content)
        assert "tools" not in body and "tool_choice" not in body
        assert all(secret not in json.dumps(body) for secret in ("anthropic-secret", "deepseek-secret"))
    assert json.loads(requests[0].content)["messages"][0]["role"] == "user"
    assert json.loads(requests[1].content)["response_format"] == {"type": "json_object"}


def test_service_disabled_is_deterministically_unavailable_without_transport() -> None:
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    settings = Settings(_env_file=None, analysis_enabled=False)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = AnalysisService(settings=settings, client=client)
    result = service.analyze(_bundle())
    service.close()
    client.close()
    assert result.status is AnalysisStatus.ANALYSIS_UNAVAILABLE
    assert result.failure_class == "analysis_disabled"
    assert called is False


def test_service_network_failure_does_not_construct_or_call_secondary_provider() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("secret transport detail")

    settings = Settings(
        _env_file=None,
        analysis_enabled=True,
        analysis_primary_provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
        analysis_primary_model="codex-model",
        analysis_codex_enabled=True,
        openai_api_key="primary-secret",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = AnalysisService(settings=settings, client=client)
    result = service.analyze(_bundle())
    service.close()
    client.close()
    assert result.status is AnalysisStatus.ANALYSIS_UNAVAILABLE
    assert result.failure_class == "httpx.ConnectError"
    assert calls == 1
    assert "secret" not in repr(result)


@pytest.mark.parametrize("bad", ["not-json", json.dumps({"facts": [], "impact_score": 1})])
def test_invalid_model_response_is_sanitized(bad: str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output_text": bad})

    settings = Settings(
        _env_file=None,
        analysis_enabled=True,
        analysis_primary_provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
        analysis_primary_model="codex-model",
        analysis_codex_enabled=True,
        openai_api_key="primary-secret",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://mock")
    service = AnalysisService(settings=settings, client=client)
    result = service.analyze(_bundle())
    service.close()
    client.close()
    assert result.status is AnalysisStatus.INVALID_RESPONSE
    assert result.failure_class in {"invalid_json", "schema_validation_error"}
    assert result.output is None and result.result_hash is None


@pytest.mark.parametrize(
    "bad",
    [
        f"prefix {json.dumps(_output())}",
        f"{json.dumps(_output())} trailing",
        f"```json\n{json.dumps(_output())}\n```",
        "[]",
        '"scalar"',
    ],
)
def test_response_requires_exactly_one_top_level_json_object(bad: str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output_text": bad})

    settings = Settings(
        _env_file=None,
        analysis_enabled=True,
        analysis_primary_provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
        analysis_primary_model="codex-model",
        analysis_codex_enabled=True,
        openai_api_key="primary-secret",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://mock")
    service = AnalysisService(settings=settings, client=client)
    result = service.analyze(_bundle())
    service.close()
    client.close()
    assert result.status is AnalysisStatus.INVALID_RESPONSE
    assert result.output is None and result.result_hash is None


def _assert_provider_schema(node: object) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            properties = node.get("properties", {})
            assert node.get("additionalProperties") is False
            assert set(node.get("required", [])) == set(properties)
        assert "default" not in node
        for value in node.values():
            _assert_provider_schema(value)
    elif isinstance(node, list):
        for value in node:
            _assert_provider_schema(value)


def test_codex_provider_schema_is_strict_and_provider_accepts_it() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        schema = body["text"]["format"]["schema"]
        assert set(schema["properties"]) == set(AnalysisOutput.model_fields)
        assert schema["properties"]
        assert set(schema["required"]) == set(AnalysisOutput.model_fields)
        _assert_provider_schema(schema)
        return httpx.Response(200, json={"output_text": json.dumps(_output())})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://mock")
    adapter = CodexOpenAIResponsesAdapter("https://mock", "codex-model", "secret", client=client)
    assert adapter.analyze(_bundle()).status is AnalysisStatus.COMPLETED
    assert json.loads(requests[0].content)["max_output_tokens"] == 1200
    client.close()


def test_provider_payloads_have_bounded_output_tokens() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/messages":
            return httpx.Response(200, json={"content": [{"type": "text", "text": json.dumps(_output())}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(_output())}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://mock")
    adapter = AnthropicMessagesAdapter("https://mock", "model", "secret", client=client)
    assert adapter.analyze(_bundle()).status is AnalysisStatus.COMPLETED
    assert json.loads(requests[0].content)["max_tokens"] == 1200
    client.close()

    requests.clear()
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://mock")
    adapter = DeepSeekOpenAICompatibleAdapter("https://mock", "model", "secret", client=client)
    assert adapter.analyze(_bundle()).status is AnalysisStatus.COMPLETED
    assert json.loads(requests[0].content)["max_tokens"] == 1200
    client.close()


@pytest.mark.parametrize("adapter_type", [CodexOpenAIResponsesAdapter, AnthropicMessagesAdapter, DeepSeekOpenAICompatibleAdapter])
@pytest.mark.parametrize("partial", [{}, {"facts": ["A fact"], "confidence_statement": "Context only."}])
def test_every_adapter_rejects_empty_or_partial_output(adapter_type, partial) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        text = json.dumps(partial)
        return httpx.Response(200, json={"output_text": text, "content": [{"type": "text", "text": text}], "choices": [{"message": {"content": text}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://mock")
    adapter = adapter_type("https://mock", "model", "secret", client=client)
    result = adapter.analyze(_bundle())
    client.close()
    assert result.status is AnalysisStatus.INVALID_RESPONSE
    assert result.output is None and result.result_hash is None


class _TrackingClient(httpx.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1
        super().close()


def test_adapter_and_service_close_only_owned_clients() -> None:
    injected = _TrackingClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    adapter = CodexOpenAIResponsesAdapter("https://mock", "model", "secret", client=injected)
    adapter.close()
    assert injected.close_count == 0
    injected.close()
    assert injected.close_count == 1

    settings = Settings(
        _env_file=None,
        analysis_enabled=True,
        analysis_primary_provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
        analysis_primary_model="model",
        analysis_codex_enabled=True,
        openai_api_key="primary-secret",
    )
    service = AnalysisService(settings=settings, transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    owned = service._adapter
    assert owned is not None
    service.close()
    assert owned._client.is_closed


def test_oversized_bundle_and_version_mismatch_make_zero_http_calls() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"output_text": json.dumps(_output())})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://mock")
    adapter = CodexOpenAIResponsesAdapter("https://mock", "model", "secret", client=client, max_input_chars=10)
    too_large = VerifiedAnalysisInput(news_body="this exceeds ten characters")
    oversized = adapter.analyze(too_large)
    mismatch = adapter.analyze(VerifiedAnalysisInput(prompt_version="other"))
    client.close()
    assert calls == 0
    assert oversized.status is AnalysisStatus.INVALID_RESPONSE
    assert oversized.failure_class == "AnalysisInputTooLarge"
    assert mismatch.status is AnalysisStatus.INVALID_RESPONSE
    assert mismatch.failure_class == "AnalysisVersionMismatch"


@pytest.mark.parametrize("field", ["model", "prompt_version", "schema_version"])
def test_adapter_rejects_overlong_identifiers_before_request(field: str) -> None:
    values = {"base_url": "https://mock", "model": "model", "api_key": "secret"}
    values[field] = "x" * 513
    with pytest.raises(ValueError, match="identifier"):
        CodexOpenAIResponsesAdapter(**values)


def test_service_invalid_overlong_config_returns_sanitized_envelope_without_request() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"output_text": json.dumps(_output())})

    settings = Settings(
        _env_file=None,
        analysis_enabled=True,
        analysis_primary_provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
        analysis_primary_model="model",
        analysis_codex_enabled=True,
        openai_api_key="primary-secret",
    )
    settings.analysis_primary_model = "x" * 513
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://mock")
    service = AnalysisService(settings=settings, client=client)
    result = service.analyze(_bundle())
    service.close()
    client.close()
    assert calls == 0
    assert result.status is AnalysisStatus.ANALYSIS_UNAVAILABLE
    assert "ValidationError" not in repr(result)
    assert "x" * 513 not in repr(result)


@pytest.mark.parametrize("caller", [None, [], "scalar", 7, object(), {"unknown": "field"}])
def test_service_rejects_malformed_callers_without_provider_request(caller: object) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"output_text": json.dumps(_output())})

    settings = Settings(
        _env_file=None,
        analysis_enabled=True,
        analysis_primary_provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
        analysis_primary_model="model",
        analysis_codex_enabled=True,
        openai_api_key="primary-secret",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://mock")
    service = AnalysisService(settings=settings, client=client)
    result = service.analyze(caller)
    repeated = service.analyze(caller)
    service.close()
    client.close()

    assert calls == 0
    assert result.status is AnalysisStatus.INVALID_RESPONSE
    assert result.failure_class == "invalid_input"
    assert result.output is None and result.result_hash is None
    assert result.input_hash == repeated.input_hash
    assert len(result.input_hash) == 64
    assert result.provider is settings.analysis_primary_provider
    assert result.model == settings.analysis_primary_model
    assert result.prompt_version == settings.analysis_prompt_version
    assert result.schema_version == settings.analysis_schema_version
    assert "unknown" not in repr(result)
    assert "scalar" not in repr(result)


def test_service_valid_mapping_is_validated_before_adapter_call() -> None:
    calls = []

    class Adapter:
        def analyze(self, value):
            calls.append(value)
            return AnalysisEnvelope(
                status=AnalysisStatus.ANALYSIS_UNAVAILABLE,
                provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
                model="model",
                latency_ms=0,
                input_hash=value.input_hash,
                prompt_version="analysis-v1",
                schema_version="analysis-v1",
                failure_class="test_unavailable",
            )

    settings = Settings(
        _env_file=None,
        analysis_enabled=True,
        analysis_primary_provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
        analysis_primary_model="model",
        analysis_codex_enabled=True,
        openai_api_key="primary-secret",
    )
    service = AnalysisService(settings=settings, adapter=Adapter())
    result = service.analyze(_bundle().model_dump(mode="json"))

    assert result.status is AnalysisStatus.ANALYSIS_UNAVAILABLE
    assert len(calls) == 1
    assert isinstance(calls[0], VerifiedAnalysisInput)

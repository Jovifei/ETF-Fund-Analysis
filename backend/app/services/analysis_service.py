"""Single-primary analysis gateway."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping

import httpx

from app.analysis.adapters import (
    AnthropicMessagesAdapter,
    CodexOpenAIResponsesAdapter,
    DeepSeekOpenAICompatibleAdapter,
    serialize_analysis_input,
)
from app.analysis.contracts import (
    AnalysisAdapter,
    AnalysisEnvelope,
    AnalysisProvider,
    AnalysisStatus,
    VerifiedAnalysisInput,
)
from app.core.config import Settings, get_settings

_INVALID_INPUT_HASH = hashlib.sha256(b"analysis-invalid-input-v1").hexdigest()


def _failure_class(exc: BaseException) -> str:
    module = "".join(char for char in type(exc).__module__ if char.isalnum() or char == ".")
    name = "".join(char for char in type(exc).__name__ if char.isalnum() or char == "_")
    return f"{module}.{name}" if module else name


def _safe_identifier(value: object, fallback: str) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized and len(normalized) <= 512:
            return normalized
    return fallback


class AnalysisAdapterRegistry:
    """Construct exactly the configured primary adapter, never a fallback."""

    @staticmethod
    def create_primary(
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> AnalysisAdapter:
        provider = settings.analysis_primary_provider
        if provider is AnalysisProvider.CODEX_OPENAI_RESPONSES:
            return CodexOpenAIResponsesAdapter(
                base_url=settings.analysis_codex_base_url,
                model=settings.analysis_primary_model,
                api_key=settings.openai_api_key,
                client=client,
                transport=transport,
                timeout=settings.analysis_codex_timeout_seconds,
                prompt_version=settings.analysis_prompt_version,
                schema_version=settings.analysis_schema_version,
                max_input_chars=settings.analysis_max_input_chars,
            )
        if provider is AnalysisProvider.ANTHROPIC_MESSAGES:
            return AnthropicMessagesAdapter(
                base_url=settings.analysis_anthropic_base_url,
                model=settings.analysis_primary_model,
                api_key=settings.anthropic_api_key,
                client=client,
                transport=transport,
                timeout=settings.analysis_anthropic_timeout_seconds,
                prompt_version=settings.analysis_prompt_version,
                schema_version=settings.analysis_schema_version,
                max_input_chars=settings.analysis_max_input_chars,
            )
        if provider is AnalysisProvider.DEEPSEEK_OPENAI_COMPATIBLE:
            return DeepSeekOpenAICompatibleAdapter(
                base_url=settings.analysis_deepseek_base_url,
                model=settings.analysis_primary_model,
                api_key=settings.deepseek_api_key,
                client=client,
                transport=transport,
                timeout=settings.analysis_deepseek_timeout_seconds,
                prompt_version=settings.analysis_prompt_version,
                schema_version=settings.analysis_schema_version,
                max_input_chars=settings.analysis_max_input_chars,
            )
        raise ValueError("analysis primary provider is not configured")


class AnalysisService:
    """Run one configured direct adapter and return a provenance envelope."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        adapter: AnalysisAdapter | None = None,
        adapter_factory: Callable[[Settings], AnalysisAdapter] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._adapter: AnalysisAdapter | None = None
        self._construction_failure: str | None = None
        if self.settings.analysis_enabled:
            try:
                if adapter is not None:
                    self._adapter = adapter
                elif adapter_factory is not None:
                    self._adapter = adapter_factory(self.settings)
                else:
                    self._adapter = AnalysisAdapterRegistry.create_primary(
                        self.settings, client=client, transport=transport
                    )
            except Exception as exc:  # keep invalid configuration out of envelope details
                self._construction_failure = _failure_class(exc)

    def _provider(self) -> AnalysisProvider:
        return self.settings.analysis_primary_provider or AnalysisProvider.CODEX_OPENAI_RESPONSES

    def _model(self) -> str:
        return _safe_identifier(self.settings.analysis_primary_model, "analysis-invalid-config")

    def _bound_envelope(
        self,
        input_data: VerifiedAnalysisInput,
        envelope: object,
    ) -> AnalysisEnvelope | None:
        """Validate an adapter result against this call's input and live config.

        Adapters are an untrusted boundary too: a custom/injected adapter can
        return a syntactically valid envelope that is bound to another input or
        provider.  Only a fully matching envelope may leave this gateway.
        """
        try:
            validated = (
                envelope
                if isinstance(envelope, AnalysisEnvelope)
                else AnalysisEnvelope.model_validate(envelope)
            )
            if (
                validated.input_hash.lower() != input_data.input_hash.lower()
                or validated.provider is not self._provider()
                or validated.model != self._model()
                or validated.prompt_version != _safe_identifier(
                    self.settings.analysis_prompt_version, "analysis-invalid-config"
                )
                or validated.schema_version != _safe_identifier(
                    self.settings.analysis_schema_version, "analysis-invalid-config"
                )
                or (
                    validated.output is not None
                    and (
                        validated.output.provider is not self._provider()
                        or validated.output.model != self._model()
                        or validated.output.prompt_version
                        != _safe_identifier(
                            self.settings.analysis_prompt_version, "analysis-invalid-config"
                        )
                    )
                )
            ):
                return None
            return validated
        except Exception:
            # Do not let malformed adapter objects or their values cross the
            # boundary, and do not include provider response text in diagnostics.
            return None

    def _unavailable(
        self,
        input_data: VerifiedAnalysisInput,
        *,
        status: AnalysisStatus = AnalysisStatus.ANALYSIS_UNAVAILABLE,
        failure_class: str,
        started: float | None = None,
    ) -> AnalysisEnvelope:
        latency_ms = 0.0 if started is None else max(0.0, (time.perf_counter() - started) * 1000.0)
        return AnalysisEnvelope(
            status=status,
            provider=self._provider(),
            model=self._model(),
            latency_ms=latency_ms,
            input_hash=input_data.canonical_hash,
            prompt_version=_safe_identifier(self.settings.analysis_prompt_version, "analysis-invalid-config"),
            schema_version=_safe_identifier(self.settings.analysis_schema_version, "analysis-invalid-config"),
            failure_class=failure_class,
        )

    def _invalid_input(self) -> AnalysisEnvelope:
        """Return a fixed, sanitized envelope for an untrusted caller value."""
        return AnalysisEnvelope(
            status=AnalysisStatus.INVALID_RESPONSE,
            provider=self._provider(),
            model=self._model(),
            latency_ms=0.0,
            input_hash=_INVALID_INPUT_HASH,
            prompt_version=_safe_identifier(
                self.settings.analysis_prompt_version, "analysis-invalid-config"
            ),
            schema_version=_safe_identifier(
                self.settings.analysis_schema_version, "analysis-invalid-config"
            ),
            failure_class="invalid_input",
        )

    @staticmethod
    def _validate_input(value: object) -> VerifiedAnalysisInput | None:
        if isinstance(value, VerifiedAnalysisInput):
            return value
        if not isinstance(value, Mapping):
            return None
        try:
            return VerifiedAnalysisInput.model_validate(value)
        except Exception:
            return None

    def analyze(self, input_data: VerifiedAnalysisInput | Mapping[str, object] | object) -> AnalysisEnvelope:
        validated_input = self._validate_input(input_data)
        if validated_input is None:
            return self._invalid_input()
        input_data = validated_input
        if not self.settings.analysis_enabled:
            return self._unavailable(input_data, failure_class="analysis_disabled")
        if self._construction_failure is not None:
            return self._unavailable(input_data, failure_class=self._construction_failure)
        if self._adapter is None:
            return self._unavailable(input_data, failure_class="primary_not_configured")
        if input_data.prompt_version != self.settings.analysis_prompt_version or input_data.schema_version != self.settings.analysis_schema_version:
            return self._unavailable(
                input_data,
                status=AnalysisStatus.INVALID_RESPONSE,
                failure_class="AnalysisVersionMismatch",
            )
        if len(serialize_analysis_input(input_data)) > self.settings.analysis_max_input_chars:
            return self._unavailable(
                input_data,
                status=AnalysisStatus.INVALID_RESPONSE,
                failure_class="AnalysisInputTooLarge",
            )
        started = time.perf_counter()
        try:
            envelope = self._adapter.analyze(input_data)
        except Exception as exc:  # defensive boundary; never expose exception text
            return self._unavailable(input_data, failure_class=_failure_class(exc), started=started)
        bound = self._bound_envelope(input_data, envelope)
        if bound is None:
            return self._unavailable(
                input_data,
                status=AnalysisStatus.INVALID_RESPONSE,
                failure_class="AnalysisProvenanceMismatch",
                started=started,
            )
        return bound

    def close(self) -> None:
        if self._adapter is not None:
            close = getattr(self._adapter, "close", None)
            if callable(close):
                close()

    def __enter__(self) -> AnalysisService:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()


# Compatibility name for callers that describe the registry as a factory.
AnalysisAdapterFactory = AnalysisAdapterRegistry

__all__ = ["AnalysisAdapterFactory", "AnalysisAdapterRegistry", "AnalysisService"]

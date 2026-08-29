"""Compatibility façade for the provider-neutral analysis gateway.

The original service exposed a news-specific client and a numeric impact field.
Those APIs are intentionally retired: model output is now an ``AnalysisOutput``
candidate and deterministic impact fields remain owned by ``NewsService``.
"""

from __future__ import annotations

from app.analysis.contracts import (
    AnalysisEnvelope,
    AnalysisOutput,
    AnalysisProvider,
    AnalysisStatus,
    VerifiedAnalysisInput,
)
from app.core.config import Settings, get_settings
from app.services.analysis_service import AnalysisService

# Preserve the import name for callers that only need the validated text
# candidate.  It deliberately has no numeric decision fields.
NewsAnalysis = AnalysisOutput


class OpenAICompatibleClient:
    """Legacy-shaped wrapper backed solely by :class:`AnalysisService`.

    ``analyze_news`` returns a validated candidate for completed runs and
    ``None`` for unavailable or invalid runs, matching the old optional return
    shape without reintroducing a second transport implementation.
    """

    def __init__(self, settings: Settings | None = None, *, service: AnalysisService | None = None) -> None:
        self.settings = settings or get_settings()
        self._service = service if service is not None else AnalysisService(self.settings)
        self._owns_service = service is None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.analysis_enabled)

    def analyze_news(
        self,
        input_data: VerifiedAnalysisInput,
    ) -> AnalysisEnvelope:
        return self._service.analyze(input_data)

    def analyze(self, input_data: VerifiedAnalysisInput) -> AnalysisEnvelope:
        """Expose the A1 gateway contract for newer compatibility callers."""
        return self._service.analyze(input_data)

    def close(self) -> None:
        if self._owns_service:
            self._service.close()


__all__ = [
    "AnalysisEnvelope",
    "AnalysisOutput",
    "AnalysisProvider",
    "AnalysisService",
    "AnalysisStatus",
    "NewsAnalysis",
    "OpenAICompatibleClient",
    "VerifiedAnalysisInput",
]

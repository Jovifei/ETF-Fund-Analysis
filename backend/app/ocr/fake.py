from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from app.ocr.contracts import OCRLine, OCRResult


class FakeOCRBackend:
    """Deterministic injectable OCR backend for synthetic tests only."""

    def __init__(self, lines: Sequence[OCRLine] = (), *, model: str = "fixture", version: str = "1") -> None:
        self._lines = tuple(lines)
        self._model = model
        self._version = version

    def recognize(self, image: bytes) -> OCRResult:
        del image
        return OCRResult(
            lines=self._lines,
            backend="fake",
            model=self._model,
            version=self._version,
            # A fixed timestamp keeps fixture output byte-for-byte deterministic.
            processed_at=datetime(2000, 1, 1, tzinfo=UTC),
        )

    run = recognize

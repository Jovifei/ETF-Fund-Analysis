"""Private, bounded OCR building blocks for holding imports.

This package intentionally contains no upload endpoint or holding-write logic.
"""

from app.ocr.contracts import (
    HoldingCandidate,
    NormalizedCandidate,
    NormalizedHoldingCandidate,
    OCRBox,
    OCRLine,
    OCRResult,
    OCRUnavailable,
)

__all__ = [
    "HoldingCandidate",
    "NormalizedCandidate",
    "NormalizedHoldingCandidate",
    "OCRBox",
    "OCRLine",
    "OCRResult",
    "OCRUnavailable",
]

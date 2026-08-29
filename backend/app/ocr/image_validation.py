from __future__ import annotations

import hashlib
import io
import struct
from dataclasses import dataclass
from typing import BinaryIO

from PIL import Image
from PIL.Image import DecompressionBombError, DecompressionBombWarning

SUPPORTED_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
_SIGNATURES = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "image/webp": b"RIFF",
}


class ImageValidationError(ValueError):
    """Safe public image-validation error without decoder/filename details."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.error_code = code
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class ImageMetadata:
    sha256: str
    mime_type: str
    byte_size: int
    width: int
    height: int
    total_pixels: int

    @property
    def mime(self) -> str:
        return self.mime_type

    @property
    def detected_mime(self) -> str:
        return self.mime_type

    @property
    def size_bytes(self) -> int:
        return self.byte_size


@dataclass(frozen=True, slots=True)
class ValidatedImage:
    """In-memory validated artifact passed to a local OCR adapter."""

    payload: bytes
    metadata: ImageMetadata

    def __post_init__(self) -> None:
        if not isinstance(self.payload, bytes):
            raise TypeError("validated image payload must be immutable bytes")
        if self.metadata.byte_size != len(self.payload):
            raise ValueError("validated image metadata does not match payload")


def _detected_mime(payload: bytes) -> str:
    if payload.startswith(_SIGNATURES["image/png"]):
        return "image/png"
    if payload.startswith(_SIGNATURES["image/jpeg"]):
        return "image/jpeg"
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "image/webp"
    raise ImageValidationError("unsupported_format", "unsupported image format")


def _reject_trailing_bytes(payload: bytes, mime_type: str) -> None:
    if mime_type == "image/png":
        # PNG's IEND chunk is the final legal chunk.  Reject polyglot/trailing data.
        position = 8
        iend_end = None
        while position + 12 <= len(payload):
            length = struct.unpack(">I", payload[position : position + 4])[0]
            end = position + 12 + length
            if end > len(payload):
                raise ImageValidationError("decode_failed", "image decode failed")
            chunk = payload[position + 4 : position + 8]
            position = end
            if chunk == b"IEND":
                iend_end = end
                break
        if iend_end is None or iend_end != len(payload):
            raise ImageValidationError("trailing_bytes", "image has trailing bytes")
    elif mime_type == "image/jpeg":
        # Locate the first genuine EOI, skipping marker-segment payloads and
        # byte-stuffed entropy data.  Looking only at the last EOI permits a
        # polyglot ending in a second fabricated EOI marker.
        position = 2
        genuine_eoi = None
        while position + 1 < len(payload):
            if payload[position] != 0xFF:
                position += 1
                continue
            while position < len(payload) and payload[position] == 0xFF:
                position += 1
            if position >= len(payload):
                break
            marker = payload[position]
            if marker == 0xD9:
                genuine_eoi = position + 1
                break
            if marker == 0xDA:  # start of scan; parse entropy until its EOI
                if position + 2 >= len(payload):
                    break
                segment_length = struct.unpack(">H", payload[position + 1 : position + 3])[0]
                if segment_length < 2 or position + 1 + segment_length > len(payload):
                    break
                position = position + 1 + segment_length
                while position + 1 < len(payload):
                    if payload[position] != 0xFF:
                        position += 1
                        continue
                    code_position = position + 1
                    while code_position < len(payload) and payload[code_position] == 0xFF:
                        code_position += 1
                    if code_position >= len(payload):
                        break
                    code = payload[code_position]
                    if code == 0x00 or 0xD0 <= code <= 0xD7:
                        position = code_position + 1
                        continue
                    if code == 0xD9:
                        genuine_eoi = code_position + 1
                    else:
                        position = code_position
                    break
                if genuine_eoi is not None:
                    break
                continue
            if marker in {0xD8, 0x01} or 0xD0 <= marker <= 0xD7:
                position += 1
                continue
            if position + 2 >= len(payload):
                break
            segment_length = struct.unpack(">H", payload[position + 1 : position + 3])[0]
            if segment_length < 2 or position + 1 + segment_length > len(payload):
                break
            position = position + 1 + segment_length
        if genuine_eoi != len(payload):
            raise ImageValidationError("trailing_bytes", "image has trailing bytes")
    else:
        # RIFF file size excludes the first eight bytes and must match exactly.
        if len(payload) < 8 or struct.unpack("<I", payload[4:8])[0] + 8 != len(payload):
            raise ImageValidationError("trailing_bytes", "image has trailing bytes")


def read_limited_bytes(stream: BinaryIO, *, max_bytes: int) -> bytes:
    """Read at most max_bytes+1, allowing callers to reject an oversized stream."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    chunks: list[bytes] = []
    total = 0
    while total <= max_bytes:
        chunk = stream.read(min(64 * 1024, max_bytes + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ImageValidationError("too_large", "image is too large")
        chunks.append(chunk)
    return b"".join(chunks)


def validate_image_bytes(
    payload: bytes,
    *,
    declared_mime: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    max_width: int = 12_000,
    max_height: int = 12_000,
    max_pixels: int = 40_000_000,
) -> ImageMetadata:
    if not isinstance(payload, bytes):
        raise ImageValidationError("invalid_payload", "image payload must be bytes")
    if len(payload) == 0 or len(payload) > max_bytes:
        raise ImageValidationError("too_large", "image is too large")
    if declared_mime is not None and declared_mime not in SUPPORTED_MIME_TYPES:
        raise ImageValidationError("mime_mismatch", "declared mime type is unsupported")
    detected = _detected_mime(payload)
    if declared_mime is not None and declared_mime != detected:
        raise ImageValidationError("mime_mismatch", "declared mime type does not match image")
    _reject_trailing_bytes(payload, detected)

    # Never modify Pillow's process-global decoder settings: C2 can validate
    # concurrent uploads safely while another component uses Pillow.
    def _open() -> Image.Image:
        try:
            return Image.open(io.BytesIO(payload))
        except (DecompressionBombError, DecompressionBombWarning):
            raise ImageValidationError("pixel_limit", "pixel limit exceeded") from None
        except Exception:
            raise ImageValidationError("decode_failed", "image decode failed") from None

    with _open() as image:
        try:
            image.verify()
        except (DecompressionBombError, DecompressionBombWarning):
            raise ImageValidationError("pixel_limit", "pixel limit exceeded") from None
        except Exception:
            raise ImageValidationError("decode_failed", "image decode failed") from None
    with _open() as image:
        try:
            width, height = image.size
            pixels = width * height
            if width <= 0 or height <= 0 or width > max_width or height > max_height:
                raise ImageValidationError("dimension_limit", "image dimensions exceed limits")
            if pixels > max_pixels:
                raise ImageValidationError("pixel_limit", "pixel limit exceeded")
            image.load()
        except ImageValidationError:
            raise
        except (DecompressionBombError, DecompressionBombWarning):
            raise ImageValidationError("pixel_limit", "pixel limit exceeded") from None
        except Exception:
            raise ImageValidationError("decode_failed", "image decode failed") from None

    return ImageMetadata(
        sha256=hashlib.sha256(payload).hexdigest(),
        mime_type=detected,
        byte_size=len(payload),
        width=width,
        height=height,
        total_pixels=pixels,
    )


def validate_image_stream(
    stream: BinaryIO,
    *,
    declared_mime: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    max_width: int = 12_000,
    max_height: int = 12_000,
    max_pixels: int = 40_000_000,
) -> ImageMetadata:
    payload = read_limited_bytes(stream, max_bytes=max_bytes)
    return validate_image_bytes(
        payload,
        declared_mime=declared_mime,
        max_bytes=max_bytes,
        max_width=max_width,
        max_height=max_height,
        max_pixels=max_pixels,
    )


def validate_image_artifact(
    payload: bytes,
    *,
    declared_mime: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    max_width: int = 12_000,
    max_height: int = 12_000,
    max_pixels: int = 40_000_000,
) -> ValidatedImage:
    metadata = validate_image_bytes(
        payload,
        declared_mime=declared_mime,
        max_bytes=max_bytes,
        max_width=max_width,
        max_height=max_height,
        max_pixels=max_pixels,
    )
    return ValidatedImage(payload=payload, metadata=metadata)


# Explicit alias for callers that validate an already bounded UploadFile read.
validate_image = validate_image_bytes
read_bounded_bytes = read_limited_bytes
read_limited_stream = read_limited_bytes

"""Strict, deterministic JSON serialization for persisted evidence payloads."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

_MEMO_KEYS = frozenset({"summary", "evidence_ids", "risk_flags", "limitations"})
_SENSITIVE_CONTENT = re.compile(
    r"(?ix)"
    r"(?:https?://|www\.)"
    r"|(?:\bbearer\s+\S+)"
    r"|(?:\b(?:api[_-]?key|password|passwd|secret|token)\s*[:=])"
    r"|(?:\b(?:api[_-]?key|password|passwd|secret|token|cookie|authorization)\b\s+\S+)"
    r"|(?:\b(?:traceback|stack\s+trace)\b)"
    r"|(?:[A-Za-z]:[\\/]|\\\\|(?<!\w)/(?:[\w. -]+[\\/])+[^\s]*)"
    r"|(?:(?<![\w.-])(?:\.\.?[\\/]|~[\\/])[^\s]+)"
    r"|(?:(?<![\w.-])[\w.-]+(?:[\\/])[\w./-]+)"
    r"|(?:\b(?:powershell|pwsh|cmd(?:\.exe)?|bash|sh)\b(?:\s|$))"
    r"|(?:\b(?:rm|del|erase|remove-item|invoke-(?:expression|webrequest)|curl|wget)\b\s+)"
)


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def canonical_loads(value: str, *, object_only: bool = False) -> Any:
    """Decode JSON while rejecting NaN/Infinity and optionally requiring an object."""
    if not isinstance(value, str):
        raise ValueError("canonical JSON input must be text")
    try:
        parsed = json.loads(value, parse_constant=_reject_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid strict JSON") from exc
    if object_only and not isinstance(parsed, dict):
        raise ValueError("canonical JSON value must be an object")
    return parsed


def canonical_dumps(value: Any, *, object_only: bool = False) -> str:
    """Encode JSON with one stable representation and no non-standard numbers."""
    if object_only and not isinstance(value, Mapping):
        raise ValueError("canonical JSON value must be an object")
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("value is not strict JSON serializable") from exc


def canonical_hash_text(value: str) -> str:
    """Hash the exact UTF-8 JSON text stored in the database."""
    if not isinstance(value, str):
        raise ValueError("hash input must be text")
    # Hashes bind the exact canonical representation, not merely an arbitrary
    # JSON-looking string.  This also makes NaN/Infinity impossible to smuggle
    # through a caller that bypasses canonical_dumps.
    parsed = canonical_loads(value, object_only=True)
    if canonical_dumps(parsed, object_only=True) != value:
        raise ValueError("hash input must be canonical JSON text")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_hash(value: Any, *, object_only: bool = False) -> str:
    return canonical_hash_text(canonical_dumps(value, object_only=object_only))


def validate_safe_text(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("memo text must be a non-empty string")
    if _SENSITIVE_CONTENT.search(value):
        raise ValueError("memo contains sensitive, path, URL, stack, or command content")
    return value.strip()


def validate_review_memo_payload(value: Any) -> dict[str, Any]:
    """Validate the persistence-level shape even when bypassing Pydantic/ORM setters."""
    if not isinstance(value, dict) or not set(value).issubset(_MEMO_KEYS) or "summary" not in value:
        raise ValueError("memo must contain only summary/evidence_ids/risk_flags/limitations")
    summary = validate_safe_text(value["summary"])
    if len(summary) > 4000:
        raise ValueError("memo summary is too long")
    normalized: dict[str, Any] = {"summary": summary}
    limits = {"evidence_ids": (128, 512), "risk_flags": (32, 2000), "limitations": (32, 2000)}
    for key, (max_items, max_chars) in limits.items():
        if key not in value:
            continue
        entries = value[key]
        if not isinstance(entries, (list, tuple)) or len(entries) > max_items:
            raise ValueError(f"memo {key} must be a bounded ordered sequence")
        normalized[key] = []
        for entry in entries:
            item = validate_safe_text(entry)
            if len(item) > max_chars:
                raise ValueError(f"memo {key} entry is too long")
            normalized[key].append(item)
    return normalized


# Explicit aliases make the helper convenient without reintroducing permissive json defaults.
dumps = canonical_dumps
loads = canonical_loads

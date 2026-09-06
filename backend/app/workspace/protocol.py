"""Versioned, bounded research contracts. Model output has NO action authority."""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Code = Annotated[str, StringConstraints(pattern=r"^\d{6}\.(SH|SZ|BJ)$")]
Hash = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
JobId = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]
BoundedText = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
EvidenceId = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_.:-]{1,128}$")]
_SECRET = re.compile(r"(?i)(?:\bsk-[a-z0-9_-]{16,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|\bBearer\s+[a-z0-9._~-]{16,}|(?:api[_-]?key|password|secret|token)\s*[=:]\s*[\"']?[a-z0-9_./+~-]{16,})")


def safe_text(value: str) -> str:
    if _SECRET.search(value) or "\x00" in value:
        raise ValueError("sensitive or invalid text rejected")
    return value


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_hash(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Claim(StrictModel):
    text: BoundedText
    evidence_ids: list[EvidenceId] = Field(min_length=1, max_length=32)

    @field_validator("text")
    @classmethod
    def safe(cls, value: str) -> str:
        return safe_text(value)


class ResearchResult(StrictModel):
    schema_version: Literal["etf-research-result-v1"]
    job_id: JobId
    input_hash: Hash
    producer: Literal["manual", "codex", "vibe", "claude"]
    producer_version: str = Field(min_length=1, max_length=96)
    model: str = Field(min_length=1, max_length=96)
    summary: BoundedText
    facts: list[Claim] = Field(default_factory=list, max_length=64)
    inferences: list[Claim] = Field(default_factory=list, max_length=64)
    risks: list[BoundedText] = Field(default_factory=list, max_length=32)
    conflicts: list[BoundedText] = Field(default_factory=list, max_length=32)
    limitations: list[BoundedText] = Field(min_length=1, max_length=32)
    evidence_ids: list[EvidenceId] = Field(default_factory=list, max_length=128)
    report_markdown: str = Field(default="", max_length=50000)
    input_tokens: int | None = Field(default=None, ge=0, le=20_000_000)
    output_tokens: int | None = Field(default=None, ge=0, le=2_000_000)
    duration_seconds: float | None = Field(default=None, ge=0, le=7200, allow_inf_nan=False)

    @field_validator("summary", "report_markdown", "producer_version", "model")
    @classmethod
    def safe_scalar(cls, value: str) -> str:
        return safe_text(value)

    @field_validator("risks", "conflicts", "limitations")
    @classmethod
    def safe_list(cls, values: list[str]) -> list[str]:
        return [safe_text(value) for value in values]


class ResearchRequest(StrictModel):
    kind: Literal["etf", "daily"] = "etf"
    ts_code: Code | None = None
    include_holdings: bool = False
    request_key: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{16,64}$")


class ReviewRequest(StrictModel):
    result_hash: Hash
    note: str = Field(default="", max_length=1000)

    @field_validator("note")
    @classmethod
    def safe(cls, value: str) -> str:
        return safe_text(value)


class DataRequest(StrictModel):
    task: Literal["refresh", "onboard", "factors", "validate", "shadow_audit"]
    codes: list[Code] = Field(default_factory=list, max_length=30)
    lookback_days: int = Field(default=420, ge=30, le=1800)
    request_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,64}$")


class Preferences(StrictModel):
    daily_review: bool = False
    sidebar: Literal["expanded", "compact", "hidden"] = "expanded"
    reduce_motion: bool = False


class PairRequest(StrictModel):
    pairing_code: str = Field(min_length=20, max_length=128)


class DeviceRequest(StrictModel):
    label: str = Field(default="本地研究设备", min_length=1, max_length=64)

    @field_validator("label")
    @classmethod
    def safe(cls, value: str) -> str:
        return safe_text(value)


class Heartbeat(StrictModel):
    bridge_version: str = Field(max_length=64)
    runner_version: str | None = Field(default=None, max_length=64)
    login_state: Literal["unknown", "logged_in", "logged_out", "unavailable"] = "unknown"
    mode: Literal["manual", "codex_no_tools", "vibe_export"] = "manual"

    @field_validator("bridge_version", "runner_version")
    @classmethod
    def safe(cls, value: str | None) -> str | None:
        return safe_text(value) if value else value


class DeviceResult(StrictModel):
    lease_id: JobId
    result: ResearchResult


class DeviceFailure(StrictModel):
    lease_id: JobId
    reason: Literal["runner_unavailable", "login_required", "timeout", "budget_exceeded", "invalid_output", "runner_failed", "interrupted"]

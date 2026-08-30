from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, StringConstraints, field_validator

from app.services.review_service import ReviewMemo

SHA256Hash = Annotated[StrictStr, StringConstraints(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")]
ReviewRunner = Literal["codex_review_runner", "claude_code_review_runner"]


class HoldingUpsert(BaseModel):
    ts_code: str = Field(min_length=6, max_length=32)
    shares: float = Field(ge=0)
    cost_price: float = Field(ge=0)
    target_weight: float | None = Field(default=None, ge=0, le=1)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("ts_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class RuntimeUpdate(BaseModel):
    quote_refresh_minutes: int | None = Field(default=None, ge=1, le=60)
    signal_refresh_minutes: int | None = Field(default=None, ge=5, le=120)
    news_refresh_minutes: int | None = Field(default=None, ge=5, le=240)
    lunch_news_refresh_minutes: int | None = Field(default=None, ge=3, le=120)
    signal_center_coefficient: float | None = Field(default=None, ge=0.5, le=1.5)
    market_data_tier: Literal["usable", "complete"] | None = None
    tushare_token: str | None = None
    clear_tushare_token: bool = False

    def compact(self) -> dict[str, Any]:
        data = self.model_dump()
        compact: dict[str, Any] = {}
        for key, value in data.items():
            if key == "clear_tushare_token":
                if value:
                    compact[key] = True
                continue
            if key == "tushare_token":
                if isinstance(value, str) and value.strip():
                    compact[key] = value
                continue
            if value is not None:
                compact[key] = value
        return compact


class MarketProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tushare_token: str | None = None
    market_data_tier: Literal["usable", "complete"] | None = None


class BoardFundAdd(BaseModel):
    ts_code: str = Field(min_length=8, max_length=16)
    name: str | None = Field(default=None, max_length=64)

    @field_validator("ts_code")
    @classmethod
    def normalize_board_code(cls, value: str) -> str:
        return value.strip().upper()


class TaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lookback_days: int | None = Field(default=None, ge=30, le=5000)
    since_hours: int | None = Field(default=None, ge=1, le=720)
    codes: list[str] | tuple[str, ...] | None = None
    report: bool | None = None
    limit: int | None = Field(default=None, ge=0, le=1000)
    force: bool | None = None

    @field_validator("codes", mode="before")
    @classmethod
    def normalize_codes(cls, value: object) -> list[str] | None:
        if value is None:
            return None
        if not isinstance(value, (list, tuple)):
            raise ValueError("codes must be a list or tuple")
        if len(value) > 200:
            raise ValueError("codes cannot contain more than 200 entries")
        normalized: list[str] = []
        for code in value:
            if not isinstance(code, str):
                raise ValueError("codes must contain strings")
            item = code.strip().upper()
            if len(item) > 32 or not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,31}", item):
                raise ValueError("code must be at most 32 safe characters")
            normalized.append(item)
        return normalized

    def compact(self) -> dict[str, Any]:
        return {key: value for key, value in self.model_dump().items() if value is not None}


class DemoLoadRequest(BaseModel):
    """The demo loader deliberately has no provider or execution controls."""

    model_config = ConfigDict(extra="forbid")


class ReviewEnqueueRequest(BaseModel):
    """Hash-bound review input; the raw candidate bundle never crosses this API."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    runner: ReviewRunner
    bundle_hash: SHA256Hash
    memo: ReviewMemo
    memo_hash: SHA256Hash | None = None


class ReviewTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    note: StrictStr | None = Field(default=None, max_length=2000)


class ReviewCandidateResponse(BaseModel):
    """Public review record projection, deliberately excluding ORM internals."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    runner: ReviewRunner
    bundle_hash: SHA256Hash
    memo_hash: SHA256Hash
    memo: ReviewMemo
    review_status: Literal["pending", "accepted", "rejected"]
    created_at: datetime
    updated_at: datetime | None = None
    accepted_at: datetime | None = None
    rejected_at: datetime | None = None
    review_note: str | None = None


class HoldingImportFieldConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    field: Literal["ts_code", "name", "shares", "cost_price", "target_weight"]
    confidence: float = Field(ge=0, le=1)


class HoldingImportCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    row_index: int
    ts_code: str | None = None
    name: str | None = None
    shares: float | None = None
    cost_price: float | None = None
    target_weight: float | None = None
    user_note: str | None = None
    match_status: Literal["matched", "ambiguous", "unmatched", "low_confidence", "duplicate"]
    status: Literal["pending", "reviewed", "rejected", "confirmed"]
    action: Literal["none", "confirm", "reject"]
    safe_alternatives: list[str]
    field_confidence: list[HoldingImportFieldConfidence]
    selected_code: str | None = None


class HoldingImportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    status: Literal["pending", "processing", "ready", "editing", "confirming", "confirmed", "cancelled", "expired", "failed"]
    candidate_count: int
    expires_at: datetime
    confirmed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cloud_consent: bool
    cloud_consent_at: datetime | None = None
    ocr_mode: str
    ocr_backend: str
    ocr_model: str
    ocr_version: str
    candidates: list[HoldingImportCandidateResponse]


class HoldingImportCandidatePatch(BaseModel):
    # Decimal fields intentionally accept JSON integers/floats and immediately
    # normalize in Pydantic; string/code fields remain strict and bounded.
    model_config = ConfigDict(extra="forbid", strict=False, str_strip_whitespace=True)

    ts_code: StrictStr | None = Field(default=None, min_length=9, max_length=32)
    name: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    shares: Decimal | None = Field(default=None, ge=0, le=Decimal("1000000000"))
    cost_price: Decimal | None = Field(default=None, ge=0, le=Decimal("1000000000"))
    target_weight: Decimal | None = Field(default=None, ge=0, le=1)
    user_note: StrictStr | None = Field(default=None, min_length=1, max_length=2000)
    selected_code: StrictStr | None = Field(default=None, min_length=9, max_length=32)
    action: Literal["reject"] | None = None

    @field_validator("ts_code", "selected_code")
    @classmethod
    def normalize_import_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not re.fullmatch(r"[0-9]{6}\.(SH|SZ|BJ)", value):
            raise ValueError("holding import code must include a known exchange")
        return value

    @field_validator("name", "user_note")
    @classmethod
    def reject_control_text(cls, value: str | None) -> str | None:
        if value is not None and any(ord(char) < 32 for char in value):
            raise ValueError("holding import text contains a control character")
        return value


class HoldingImportCloudConsent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    consent: bool

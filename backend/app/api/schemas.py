from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


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

    def compact(self) -> dict[str, Any]:
        return {key: value for key, value in self.model_dump().items() if value is not None}


class TaskRequest(BaseModel):
    lookback_days: int | None = Field(default=None, ge=30, le=5000)
    since_hours: int | None = Field(default=None, ge=1, le=720)
    codes: list[str] | None = None
    report: bool | None = None

    def compact(self) -> dict[str, Any]:
        return {key: value for key, value in self.model_dump().items() if value is not None}

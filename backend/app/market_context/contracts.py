from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

ContextIdentifier = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9-]*$")
]
BoundedText = Annotated[StrictStr, StringConstraints(min_length=1, max_length=512)]
SourceSymbol = Annotated[StrictStr, StringConstraints(min_length=1, max_length=128)]
Numeric = StrictInt | StrictFloat


class ContextKind(StrEnum):
    SECTOR_BREADTH = "sector_breadth"
    INDEX = "index"
    TRADABLE_PROXY = "tradable_proxy"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class _ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("context timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _finite(value: Numeric | None, name: str) -> Numeric | None:
    if value is not None and not isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


class MarketContextItem(_ContractModel):
    """Configuration for a visible context card and its provider capability."""

    context_id: ContextIdentifier
    label: BoundedText
    region: BoundedText
    context_kind: ContextKind
    source_symbol: SourceSymbol | None = None
    display_code: SourceSymbol | None = None
    is_tradable_proxy: StrictBool = False
    enabled: StrictBool = False
    display_order: StrictInt = Field(ge=1, le=10_000)
    source_priority: tuple[BoundedText, ...] = Field(default=(), max_length=32)
    freshness_rule: BoundedText = "provider_defined"
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED

    @field_validator("source_priority", mode="before")
    @classmethod
    def reject_untyped_source_priority(cls, value: object) -> object:
        if isinstance(value, (set, frozenset, Mapping)):
            raise ValueError("source_priority must be an ordered sequence")
        return value

    @model_validator(mode="after")
    def validate_capability_gate(self) -> MarketContextItem:
        if (self.context_kind is ContextKind.TRADABLE_PROXY) != self.is_tradable_proxy:
            raise ValueError("context_kind=tradable_proxy requires is_tradable_proxy=True, and vice versa")
        if self.display_code is not None and not self.is_tradable_proxy:
            raise ValueError("display_code is only valid for a tradable proxy")
        if self.enabled:
            if self.verification_status is not VerificationStatus.VERIFIED:
                raise ValueError("enabled context item must be verified")
            if self.source_symbol is None:
                raise ValueError("enabled context item requires source_symbol")
        if self.is_tradable_proxy:
            if self.verification_status is VerificationStatus.VERIFIED and self.display_code is None:
                raise ValueError("verified tradable proxy requires display_code")
            if self.verification_status is VerificationStatus.UNVERIFIED and (
                self.source_symbol is not None or self.display_code is not None
            ):
                raise ValueError("unverified tradable proxy must not contain source or display codes")
        return self


class RegistryConfig(_ContractModel):
    items: tuple[MarketContextItem, ...] = Field(min_length=1, max_length=128)

    @field_validator("items", mode="before")
    @classmethod
    def reject_untyped_items(cls, value: object) -> object:
        if isinstance(value, (set, frozenset, Mapping)):
            raise ValueError("items must be an ordered sequence")
        return value

    @model_validator(mode="after")
    def validate_unique_registry_keys(self) -> RegistryConfig:
        context_ids = [item.context_id for item in self.items]
        orders = [item.display_order for item in self.items]
        if len(set(context_ids)) != len(context_ids):
            raise ValueError("context_id values must be unique")
        if len(set(orders)) != len(orders):
            raise ValueError("display_order values must be unique")
        if orders != sorted(orders):
            raise ValueError("items must be sorted by display_order")
        return self

    def item_by_id(self, context_id: str) -> MarketContextItem:
        for item in self.items:
            if item.context_id == context_id:
                return item
        raise KeyError(context_id)


class MarketContextObservation(_ContractModel):
    """One provider observation; source and fetched timestamps are distinct."""

    context_id: ContextIdentifier
    source_symbol: SourceSymbol
    observed_value: Numeric = Field(ge=-1_000_000_000_000_000, le=1_000_000_000_000_000)
    today_pct_change: Numeric = Field(ge=-100_000, le=100_000)
    price: Numeric | None = Field(default=None, ge=0, le=1_000_000_000_000_000)
    source: BoundedText
    source_timestamp: datetime
    fetched_at: datetime
    freshness: FreshnessStatus = FreshnessStatus.UNKNOWN
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    is_mock: StrictBool = False
    degraded_reason: BoundedText | None = None

    _normalize_timestamps = field_validator("source_timestamp", "fetched_at")(_utc)

    @field_validator("observed_value", "today_pct_change", "price")
    @classmethod
    def finite_values(cls, value: Numeric | None, info) -> Numeric | None:
        return _finite(value, info.field_name)

    @model_validator(mode="after")
    def validate_provenance(self) -> MarketContextObservation:
        if self.source_timestamp > self.fetched_at:
            raise ValueError("source_timestamp must not be later than fetched_at")
        if self.is_mock:
            if self.verification_status is not VerificationStatus.UNVERIFIED:
                raise ValueError("mock observation must be unverified")
            if self.freshness is not FreshnessStatus.DEGRADED:
                raise ValueError("mock observation must be degraded")
            if not self.degraded_reason:
                raise ValueError("mock observation requires degraded_reason")
        if self.freshness in {FreshnessStatus.DEGRADED, FreshnessStatus.UNAVAILABLE} and not self.degraded_reason:
            raise ValueError("degraded or unavailable observation requires degraded_reason")
        if self.freshness in {FreshnessStatus.FRESH, FreshnessStatus.STALE} and self.degraded_reason:
            raise ValueError("fresh or stale observation must not contain degraded_reason")
        return self

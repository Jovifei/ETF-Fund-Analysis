"""Display vs research series contract for corporate actions.

Raw OHLC is the only display series. An unexplained close-to-close gap blocks
indicator and forecast paths. Fund-manager announcements are evidence, not a
license to rewrite stored bars or to certify a total-return series.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
from types import SimpleNamespace

from app.providers.data_contract import RESEARCH_ADJUST, finite, price_history_issue

DISPLAY_SERIES = "raw_unadjusted_display"
RAW_RESEARCH_SERIES = "raw_unadjusted_research"
RESEARCH_SERIES = "total_return_or_adjusted_research"


@dataclass(frozen=True, slots=True)
class CorporateActionEvent:
    ts_code: str
    record_date: date
    ex_date: date
    split_ratio: str
    evidence_id: str

    @property
    def ratio(self) -> Fraction:
        numerator, denominator = self.split_ratio.split(":", 1)
        return Fraction(int(numerator), int(denominator))


# These are official fund split notices, not ratios inferred from prices.
_OFFICIAL_ACTIONS = {
    "512200.SH": (
        CorporateActionEvent("512200.SH", date(2024, 8, 9), date(2024, 8, 12), "100000000:35806260", "sse_512200_20240806_RYUS"),
    ),
    "512800.SH": (
        CorporateActionEvent("512800.SH", date(2025, 7, 4), date(2025, 7, 7), "1:2", "sse_512800_20250707_PJ9L"),
    ),
    "515220.SH": (
        CorporateActionEvent("515220.SH", date(2024, 4, 11), date(2024, 4, 12), "1:2", "sse_515220_20240412_5CZN"),
    ),
    "512000.SH": (
        CorporateActionEvent("512000.SH", date(2025, 8, 1), date(2025, 8, 4), "1:2", "sse_512000_20250729"),
    ),
    "512480.SH": (
        CorporateActionEvent("512480.SH", date(2026, 7, 2), date(2026, 7, 3), "1:2", "sse_512480_20260629"),
    ),
    "515880.SH": (
        CorporateActionEvent("515880.SH", date(2026, 1, 30), date(2026, 2, 3), "1:3", "sse_515880_20260203"),
        CorporateActionEvent("515880.SH", date(2026, 7, 3), date(2026, 7, 6), "1:2", "sse_515880_20260706"),
    ),
    "588200.SH": (
        CorporateActionEvent("588200.SH", date(2026, 7, 20), date(2026, 7, 21), "1:3", "sse_588200_20260721"),
    ),
}


def official_corporate_actions(ts_code: str) -> tuple[CorporateActionEvent, ...]:
    return _OFFICIAL_ACTIONS.get(str(ts_code or "").strip().upper(), ())


def research_price_basis(
    ts_code: str,
    adjustment: str | None,
    *,
    effective_through: date | None = None,
    consider_corporate_actions: bool = True,
) -> dict[str, object]:
    """Return stable economic basis identity, independent of a read window."""

    from app.utils.hashing import stable_hash

    events = official_corporate_actions(ts_code) if consider_corporate_actions else ()
    effective_events = [
        event for event in events
        if effective_through is None or event.ex_date <= effective_through
    ]
    effective_ids = [event.evidence_id for event in effective_events]
    normalized_adjustment = adjustment or "ambiguous"
    use_official_research_adjustment = (
        normalized_adjustment == "none" and consider_corporate_actions and bool(effective_ids)
    )
    if use_official_research_adjustment:
        basis = "official_split_adjusted_price_research_not_total_return"
    else:
        basis = f"source_adjustment:{normalized_adjustment}"
    descriptor = {
        "code": str(ts_code or "").strip().upper(),
        "series_kind": RESEARCH_SERIES if use_official_research_adjustment else RAW_RESEARCH_SERIES,
        "adjustment_contract_version": "corporate-action-research-v1",
        "adjustment": normalized_adjustment,
        "basis": basis,
        "effective_evidence_ids": effective_ids if use_official_research_adjustment else [],
    }
    return {**descriptor, "price_basis_id": stable_hash(descriptor)}


def research_history_rows(
    rows,
    ts_code: str,
    *,
    effective_through: date | None = None,
):
    """Build an evidence-bound split-adjusted research view without mutating raw bars.

    With ``effective_through``, only corporate actions effective on or before
    that market date are applied. ``None`` preserves the historical all-known
    events behavior for callers that do not request an as-of series.
    """

    events = official_corporate_actions(ts_code)
    if effective_through is not None:
        events = tuple(event for event in events if event.ex_date <= effective_through)
    ordered = sorted(rows or (), key=lambda row: row.trade_date)
    if not events:
        return list(ordered)
    if {getattr(row, "adjust", "none") for row in ordered} != {"none"}:
        return list(ordered)
    result = []
    previous_close = None
    for row in ordered:
        price_scale = Fraction(1, 1)
        for event in events:
            if row.trade_date < event.ex_date:
                price_scale *= event.ratio
        price_multiplier = float(price_scale)
        volume_multiplier = 1.0 / price_multiplier
        values = {
            "trade_date": row.trade_date,
            "open": float(row.open) * price_multiplier,
            "high": float(row.high) * price_multiplier,
            "low": float(row.low) * price_multiplier,
            "close": float(row.close) * price_multiplier,
            "pre_close": float(row.pre_close) * price_multiplier if finite(getattr(row, "pre_close", None)) else None,
            "volume": float(row.volume) * volume_multiplier if finite(getattr(row, "volume", None)) else None,
            "amount": float(row.amount) if finite(getattr(row, "amount", None)) else None,
            "pct_change": None,
            "adjust": RESEARCH_ADJUST,
            "source": row.source,
            "fetched_at": getattr(row, "fetched_at", None),
            "quality_hash": getattr(row, "quality_hash", None),
        }
        if previous_close is not None and values["close"] > 0:
            values["pct_change"] = (values["close"] / previous_close - 1.0) * 100.0
        previous_close = values["close"]
        result.append(SimpleNamespace(**values))
    return result


@dataclass(frozen=True, slots=True)
class SeriesRewriteDecision:
    allowed: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ResearchReturnSeriesStatus:
    display_allowed: bool
    research_allowed: bool
    total_return_certified: bool
    display_closes: tuple[float, ...]
    series_kind: str
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class CanonicalResearchHistory:
    rows: tuple[object, ...]
    allowed: bool
    reason: str | None
    source_adjustment: str | None
    price_basis_id: str | None
    price_basis: str | None
    corporate_action_adjusted: bool


def canonical_research_history(
    rows,
    ts_code: str,
    *,
    effective_through: date | None = None,
) -> CanonicalResearchHistory:
    """Select one unambiguous research price basis and apply evidence-bound actions.

    Mixed source adjustment variants are never resolved by fetched-at recency.
    """
    ordered = tuple(sorted(rows or (), key=lambda row: row.trade_date))
    if not ordered:
        return CanonicalResearchHistory((), False, "history_missing", None, None, None, False)
    adjustments = {getattr(row, "adjust", None) for row in ordered}
    if len(adjustments) != 1:
        return CanonicalResearchHistory((), False, "ambiguous_price_basis", None, None, None, False)
    adjustment = next(iter(adjustments))
    if adjustment not in {"none", "qfq", "hfq", RESEARCH_ADJUST}:
        return CanonicalResearchHistory((), False, "unknown_price_basis", str(adjustment), None, None, False)

    horizon = effective_through or ordered[-1].trade_date
    research_rows = tuple(research_history_rows(ordered, ts_code, effective_through=effective_through))
    issue = price_history_issue(research_rows)
    basis = research_price_basis(ts_code, str(adjustment), effective_through=horizon)
    adjusted = any(getattr(row, "adjust", None) == RESEARCH_ADJUST for row in research_rows)
    return CanonicalResearchHistory(
        research_rows if issue is None else (),
        issue is None,
        issue,
        str(adjustment),
        str(basis["price_basis_id"]),
        str(basis["basis"]),
        adjusted,
    )


def documented_588200_split_fixture() -> dict:
    """External announcement metadata plus the unmodified raw gap.

    Record date 2026-07-20 / ex-date 2026-07-21 / 1:3 split is documented in
    docs/audits/REFERENCES_20260913.md. This fixture does not prove the two
    stored closes, does not write an adjusted series, and must not be used to
    rescale production rows.
    """

    raw_rows = (
        SimpleNamespace(
            trade_date=date(2026, 7, 20),
            open=3.539,
            high=3.539,
            low=3.539,
            close=3.539,
            volume=None,
            amount=None,
            source="akshare:em:v101",
            adjust="none",
        ),
        SimpleNamespace(
            trade_date=date(2026, 7, 21),
            open=1.349,
            high=1.349,
            low=1.349,
            close=1.349,
            volume=None,
            amount=None,
            source="akshare:em:v101",
            adjust="none",
        ),
    )
    return {
        "raw_rows": list(raw_rows),
        "announcement": {
            "ts_code": "588200.SH",
            "record_date": date(2026, 7, 20),
            "ex_date": date(2026, 7, 21),
            "split_ratio": "1:3",
            "certifies_database_prices": False,
            "rewrites_history": False,
        },
    }


def reject_rewritten_history(original_rows, candidate_rows) -> SeriesRewriteDecision:
    original_closes = tuple(float(row.close) for row in original_rows or ())
    candidate_closes = tuple(float(row.close) for row in candidate_rows or ())
    if original_closes != candidate_closes:
        return SeriesRewriteDecision(False, ("history_rewrite_forbidden",))
    return SeriesRewriteDecision(True, ())


def research_return_series_status(rows, *, ts_code=None, announcement=None, adjusted_series=None) -> ResearchReturnSeriesStatus:
    display_closes = tuple(float(row.close) for row in rows or ())
    reasons: list[str] = ["raw_unadjusted_is_not_total_return"]
    research_rows = research_history_rows(rows, ts_code) if ts_code else list(rows or ())
    issue = price_history_issue(research_rows)
    research_allowed = issue is None and bool(rows)
    if ts_code and official_corporate_actions(ts_code) and issue is None:
        reasons.append("official_corporate_action_reconciled_for_research")
        research_allowed = bool(rows)
    if issue:
        reasons.append(issue)
        if issue == "unexplained_price_discontinuity":
            reasons.append("unexplained_discontinuity_blocks_indicator_forecast")
        research_allowed = False
    if announcement:
        reasons.append("announcement_does_not_rewrite_or_certify_total_return")
        if issue:
            research_allowed = False
    if adjusted_series is not None:
        rewrite = reject_rewritten_history(rows, adjusted_series)
        if not rewrite.allowed:
            reasons.extend(rewrite.reasons)
        reasons.append("adjusted_series_not_independently_certified")
        research_allowed = False
    return ResearchReturnSeriesStatus(
        display_allowed=True,
        research_allowed=research_allowed,
        total_return_certified=False,
        display_closes=display_closes,
        series_kind=RAW_RESEARCH_SERIES if research_allowed else DISPLAY_SERIES,
        reasons=tuple(dict.fromkeys(reasons)),
    )

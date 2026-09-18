"""Display vs research series contract for corporate actions.

Raw OHLC is the only display series. An unexplained close-to-close gap blocks
indicator and forecast paths. Fund-manager announcements are evidence, not a
license to rewrite stored bars or to certify a total-return series.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace

from app.providers.data_contract import price_history_issue

DISPLAY_SERIES = "raw_unadjusted_display"
RESEARCH_SERIES = "total_return_or_adjusted_research"


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


def research_return_series_status(rows, *, announcement=None, adjusted_series=None) -> ResearchReturnSeriesStatus:
    display_closes = tuple(float(row.close) for row in rows or ())
    reasons: list[str] = ["raw_unadjusted_is_not_total_return"]
    issue = price_history_issue(rows or [])
    research_allowed = issue is None and bool(rows)
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
        series_kind=DISPLAY_SERIES if not research_allowed else RESEARCH_SERIES,
        reasons=tuple(dict.fromkeys(reasons)),
    )

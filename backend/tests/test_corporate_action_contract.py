"""Display prices stay raw; unexplained gaps block research without rewriting history."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from app.core.config import get_settings
from app.providers.corporate_action_contract import (
    RAW_RESEARCH_SERIES,
    RESEARCH_SERIES,
    documented_588200_split_fixture,
    reject_rewritten_history,
    research_return_series_status,
)
from app.providers.data_contract import price_history_issue
from app.services.qualification_gate import qualify_1430


def _bar(trade_date, close, **kwargs):
    payload = dict(
        trade_date=trade_date,
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=1000,
        amount=close * 1000,
        source="akshare:em:v101",
        adjust="none",
    )
    payload.update(kwargs)
    return SimpleNamespace(**payload)


def test_588200_documented_gap_blocks_research_and_keeps_raw_display():
    fixture = documented_588200_split_fixture()
    rows = fixture["raw_rows"]
    assert rows[0].close == 3.539 and rows[1].close == 1.349
    assert price_history_issue(rows) == "unexplained_price_discontinuity"

    status = research_return_series_status(rows, announcement=fixture["announcement"])
    assert status.display_allowed is True
    assert status.research_allowed is False
    assert status.display_closes == (3.539, 1.349)
    assert status.total_return_certified is False
    assert "unexplained_price_discontinuity" in status.reasons
    assert "unexplained_discontinuity_blocks_indicator_forecast" in status.reasons
    assert "announcement_does_not_rewrite_or_certify_total_return" in status.reasons
    assert rows[0].close == 3.539 and rows[1].close == 1.349


def test_announcement_plus_guessed_split_rewrite_is_rejected():
    fixture = documented_588200_split_fixture()
    rewritten = [
        _bar(date(2026, 7, 20), 3.539 * 3),
        _bar(date(2026, 7, 21), 1.349 * 3),
    ]
    decision = reject_rewritten_history(fixture["raw_rows"], rewritten)
    assert decision.allowed is False
    assert "history_rewrite_forbidden" in decision.reasons
    assert fixture["raw_rows"][0].close == 3.539

    status = research_return_series_status(
        fixture["raw_rows"],
        announcement=fixture["announcement"],
        adjusted_series=rewritten,
    )
    assert status.research_allowed is False
    assert status.total_return_certified is False
    assert "adjusted_series_not_independently_certified" in status.reasons
    assert status.display_closes == (3.539, 1.349)


def test_continuous_raw_series_is_not_a_certified_total_return_path():
    rows = [_bar(date(2026, 8, 20) + timedelta(days=i), 1.2 + i * 0.001) for i in range(5)]
    status = research_return_series_status(rows)
    assert status.display_allowed is True
    assert status.research_allowed is True
    assert status.total_return_certified is False
    assert status.series_kind == RAW_RESEARCH_SERIES
    assert status.series_kind != RESEARCH_SERIES
    assert "raw_unadjusted_is_not_total_return" in status.reasons
    assert price_history_issue(rows) is None


def test_qualify_1430_blocks_forecast_path_on_unexplained_gap():
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    now = datetime(2026, 8, 31, 14, 30, tzinfo=settings.timezone)
    quote = SimpleNamespace(
        source="fixture:realtime",
        price=1.349,
        quote_time=now,
        is_realtime=True,
        timestamp_verified=True,
        degraded_reason=None,
    )
    result = qualify_1430(
        settings,
        quote,
        now,
        {"inside": True, "maximum_quote_age_minutes": 8},
        bars=documented_588200_split_fixture()["raw_rows"],
    )
    assert result["actionable"] is False
    assert "unexplained_price_discontinuity" in result["reasons"]
    assert "research_return_series_blocked" in result["reasons"]

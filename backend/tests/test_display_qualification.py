from types import SimpleNamespace

from app.core.config import get_settings
from app.providers.data_contract import assess_history, price_history_issue
from app.services.qualification_gate import qualify_1430
from app.workspace.read_model import compact_row, quote_view


def _quote(**kwargs):
    payload = dict(
        source="akshare:em:v101",
        price=1.2,
        pct_change=0.5,
        quote_time=None,
        fetched_at=None,
        timestamp_verified=True,
        is_realtime=True,
        degraded_reason=None,
    )
    payload.update(kwargs)
    return SimpleNamespace(**payload)


def test_quote_view_marks_mock_and_never_actionable() -> None:
    settings = get_settings().model_copy(update={"market_provider": "mock"})
    view = quote_view(_quote(source="mock:demo"), settings)
    assert view["is_mock"] is True
    assert view["status"] == "mock"
    assert view["actionable"] is False
    assert view["is_realtime"] is False


def test_quote_view_marks_degraded_unverified_as_visible() -> None:
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    view = quote_view(_quote(timestamp_verified=False, degraded_reason="source_timestamp_missing"), settings)
    assert view["status"] in {"unverified", "stale", "degraded"}
    assert view["actionable"] is False
    assert view["is_mock"] is False


def test_compact_row_keeps_degraded_status_and_derived_research_fields() -> None:
    row = compact_row({
        "ts_code": "510300.SH",
        "name": "沪深300ETF",
        "grade": "观望",
        "freshness": "stale",
        "data_status": "quote_unverified_or_degraded",
        "quote": {"source": "mock:demo", "actionable": True},
        "entry_exit_ref": {"actionable": False, "position": "inside_band"},
        "theme_relative_strength": {"rank": 1, "actionable": False},
        "history": [{"close": 1.2, "is_forecast": False}],
        "actionable": True,
    })
    assert row["freshness"] == "stale"
    assert row["data_status"] == "quote_unverified_or_degraded"
    assert row["actionable"] is False
    assert row["entry_exit_ref"]["position"] == "inside_band"
    assert row["theme_relative_strength"]["rank"] == 1


def test_vwap_looking_amount_never_clears_unverified_units() -> None:
    row = SimpleNamespace(
        trade_date=__import__("datetime").date(2026, 7, 20),
        open=1.2, high=1.21, low=1.19, close=1.2,
        volume=1000, amount=1200, source="akshare:sina:v102", adjust="none",
    )
    reasons = assess_history([row])
    assert "sina_absolute_units_unverified" in reasons
    assert price_history_issue([row]) is None


def test_1430_gate_stays_false_even_when_inputs_look_ready() -> None:
    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    now = __import__("datetime").datetime(2026, 8, 31, 14, 30, tzinfo=settings.timezone)
    quote = _quote(
        quote_time=now,
        timestamp_verified=True,
        is_realtime=True,
        source="fixture:realtime",
    )
    result = qualify_1430(settings, quote, now, {"inside": True, "maximum_quote_age_minutes": 8})
    assert result["actionable"] is False
    assert "historical_1430_backtest_not_qualified" in result["reasons"]

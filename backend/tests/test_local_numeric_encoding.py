"""Lossless JSON number encoding changes bytes, never research content."""
import copy
from datetime import datetime, timezone
from math import copysign, isinf, isnan

import pytest
from sqlalchemy import create_engine

from app.core.config import Settings
from app.db.base import Base
from app.workspace import local_compute as lc
from app.workspace.local_display_contract import verify_bundle_integrity
from app.workspace.shadow_bundle import canonical, digest


def test_numeric_encoding_preserves_every_field_value_bar_and_input():
    original = {"charts": {"510300.SH": {"bars": [{"date": "2026-10-15", "open": 2.0,
        "close": 2.125, "volume": 1000.0, "source": "synthetic", "indicators": {"td_buy_setup": 3.0}}],
        "research_bars": [{"open": 4.0, "close": 4.25}], "research_only": True}}, "text": "2.0"}
    before = copy.deepcopy(original)
    encoded = lc._display_numbers(original)
    assert original == before and encoded == before
    bar = encoded["charts"]["510300.SH"]["bars"][0]
    assert type(bar["open"]) is int and type(bar["volume"]) is int
    assert type(bar["close"]) is float and encoded["text"] == "2.0"
    assert encoded["charts"]["510300.SH"]["research_only"] is True
    assert len(canonical(encoded)) < len(canonical(original))


@pytest.mark.parametrize("value", [-0.0, 2.125, float(2**53), -float(2**53), float("nan"), float("inf"), -float("inf")])
def test_special_floats_are_not_reencoded_or_rounded(value):
    actual = lc._display_numbers(value)
    assert type(actual) is float
    if isnan(value): assert isnan(actual)
    elif isinf(value): assert actual == value
    else: assert actual == value and copysign(1, actual) == copysign(1, value)


@pytest.mark.parametrize("value", [0.0, 2.0, -2.0, float(2**53-1), -float(2**53-1)])
def test_safe_integral_floats_use_integer_json_without_numeric_change(value):
    actual = lc._display_numbers(value)
    assert type(actual) is int and actual == value


def test_encoding_budget_boundary_does_not_trim_data_or_increase_cap(monkeypatch):
    original = {"parts": {"charts": {"bars": [{"volume": 1000.0}] * 20}}}
    encoded = lc._display_numbers(original)
    limit = len(canonical(encoded))
    monkeypatch.setattr(lc, "EXPORT_MAX_BYTES", limit)
    with pytest.raises(ValueError, match="producer export budget"):
        lc._checked_export(original)
    assert lc._checked_export(encoded) == original
    monkeypatch.setattr(lc, "EXPORT_MAX_BYTES", limit-1)
    with pytest.raises(ValueError, match="producer export budget"):
        lc._checked_export(encoded)
    assert len(encoded["parts"]["charts"]["bars"]) == 20


def test_export_hashes_encoded_parts_and_receiver_accepts_without_numeric_changes(tmp_path, monkeypatch):
    database = tmp_path / "synthetic.sqlite3"
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    Base.metadata.create_all(engine); engine.dispose()
    now = datetime.now(timezone.utc)
    settings = Settings(_env_file=None, database_url=f"sqlite:///{database.as_posix()}", market_provider="mock")
    monkeypatch.setattr(lc.DecisionBoardService, "read_latest", lambda *a, **kw: {"generated_at": now.isoformat()})
    monkeypatch.setattr(lc, "overview", lambda *a, **kw: {"rows": [{"ts_code": "510300.SH", "price": 2.0}],
        "generated_at": now.isoformat()})
    monkeypatch.setattr(lc, "instrument_detail", lambda *a, **kw: {"instrument": {"ts_code": "510300.SH"},
        "indicator_values": {"td_buy_setup": 3.0}, "forecasts": {"1": {"q50": 0.125}}})
    chart = {"ts_code": "510300.SH", "interval": "1d", "available": True, "bars": [
        {"date": "2026-10-15", "open": 2.0, "high": 2.0, "low": 2.0, "close": 2.0,
         "volume": 1000.0, "amount": 2000.0, "indicators": {"td_buy_setup": 3.0}}],
        "actionable": False, "research_only": True}
    monkeypatch.setattr(lc, "chart_data", lambda *a, **kw: copy.deepcopy(chart))
    monkeypatch.setattr(lc, "transform_chart", lambda c, period, *a, **kw: {**c, "interval": period})
    bundle = lc.export_local_v2(settings, sequence=1, code_sha="a"*40, universe=["510300.SH"], now=now,
        private_research=True, unavailable_parts=["sectors", "market_context"])
    assert bundle["manifest"]["number_encoding_version"] == "safe-integral-json-v1"
    assert bundle["manifest"]["export_projection_version"] == "local-display-projection-v1.2"
    assert type(bundle["parts"]["charts"]["510300.SH"]["bars"][0]["volume"]) is int
    assert bundle["parts"]["details"]["510300.SH"]["forecasts"]["1"]["q50"] == 0.125
    assert bundle["manifest"]["parts_hashes"] == {key: digest(value) for key, value in bundle["parts"].items()}
    assert verify_bundle_integrity(bundle)

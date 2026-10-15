"""Display-only projection preserves numeric research while removing internals."""
import copy
import pytest

from app.workspace import local_compute
from app.workspace.shadow_bundle import canonical


def source_row():
    level = {"price": 1.25, "zone_low": 1.2, "zone_high": 1.3,
             "methods": ["MA20"], "groups": ["MA"], "strength": 2.5, "internal": "x" * 50000}
    return {"ts_code": "510300.SH", "price": 1.4,
            "entry_exit_ref": {"support_zone": {"low": 1.2, "high": 1.3}, "position": "near_support"},
            "theme_relative_strength": {"label": "synthetic", "rank": 2},
            "forecasts": {"1": {"q10": -0.02, "q50": 0.01, "q90": 0.03}},
            "support_resistance": {"levels": [level], "nearest_support": level,
                "nearest_resistance": None, "current_price": 1.4, "source_as_of_date": "2026-10-14",
                "input_hash": "b" * 64, "version": "test-sr-v1", "method_version": "sr-test-method",
                "revision_id": "c" * 64, "snapshot_source": "persisted_snapshot", "structures": {"internal": "x" * 50000}},
            "history": [{"date": "2026-10-13", "close": 1.1, "is_forecast": False},
                        {"date": "2026-10-14", "close": 1.2, "is_forecast": False},
                        {"date": "2026-10-15", "close": 1.4, "is_provisional": True, "is_forecast": False}],
            "internal_debug": "not for display"}


def test_row_projection_preserves_levels_references_forecasts_and_true_last_close():
    row = source_row()
    before = copy.deepcopy(row)
    projected = local_compute._display_row(row)
    assert row == before
    assert projected["history"] == [row["history"][1]]
    assert projected["price"] == row["price"] and projected["forecasts"] == row["forecasts"]
    assert projected["entry_exit_ref"] == row["entry_exit_ref"]
    assert projected["theme_relative_strength"] == row["theme_relative_strength"]
    sr = projected["support_resistance"]
    assert "structures" not in sr and "internal_debug" not in projected
    assert sr["source_as_of_date"] == "2026-10-14" and sr["input_hash"] == "b" * 64
    assert sr["method_version"] == "sr-test-method" and sr["revision_id"] == "c" * 64
    for key in ("price", "zone_low", "zone_high", "methods", "groups", "strength"):
        assert sr["levels"][0][key] == row["support_resistance"]["levels"][0][key]
        assert sr["nearest_support"][key] == row["support_resistance"]["nearest_support"][key]
    assert len(canonical(projected)) < len(canonical(row)) // 10


def test_compact_overview_recovers_only_confirmed_history_from_original_row():
    original = source_row()
    compact = {"ts_code": original["ts_code"], "price": 1.4, "quote": {"price": 99}}
    projected = local_compute._display_row(compact, history_source=original)
    assert projected["history"] == [original["history"][1]]
    assert local_compute._display_row(compact)["history"] == []


@pytest.mark.parametrize("flag", ["not_actual", "is_partial"])
def test_display_close_never_uses_synthetic_or_partial_daily_tail(flag):
    row = source_row()
    row["history"].append({"date": "2026-10-16", "close": 99, flag: True})
    assert local_compute._display_row(row)["history"] == [row["history"][1]]


def test_export_budget_is_canonical_and_fails_without_scope_or_bar_changes(monkeypatch):
    assert local_compute.EXPORT_MAX_BYTES == 16 * 1024 * 1024
    bundle = {"parts": {"charts": {"510300.SH": {"bars": [{"close": 1.2}]}}}}
    before = copy.deepcopy(bundle)
    monkeypatch.setattr(local_compute, "EXPORT_MAX_BYTES", len(canonical(bundle)))
    assert local_compute._checked_export(bundle) == bundle
    monkeypatch.setattr(local_compute, "EXPORT_MAX_BYTES", len(canonical(bundle)) - 1)
    with pytest.raises(ValueError, match="producer export budget"):
        local_compute._checked_export(bundle)
    assert bundle == before


def test_legacy_numeric_support_levels_preserve_values():
    row = {"support_resistance": {"levels": [1.2, {"price": 1.5, "zone_low": 1.4, "zone_high": 1.6}],
                                 "nearest_support": 1.2, "nearest_resistance": 1.5}}
    sr = local_compute._display_row(row)["support_resistance"]
    assert sr["levels"] == row["support_resistance"]["levels"]
    assert sr["nearest_support"] == 1.2 and sr["nearest_resistance"] == 1.5


@pytest.mark.parametrize("value", [True, float("nan"), float("inf")])
def test_invalid_numeric_support_level_cannot_enter_projection(value):
    with pytest.raises(ValueError):
        local_compute._display_row({"support_resistance": {"levels": [], "nearest_support": value}})

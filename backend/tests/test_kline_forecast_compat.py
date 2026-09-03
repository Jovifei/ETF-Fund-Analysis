from app.services.kline_stabilization_service import _forecast_note


def test_forecast_note_accepts_legacy_diagnostics_shapes() -> None:
    assert _forecast_note([{"neighbor": "x"}]) == "persisted ForecastSnapshot"
    assert _forecast_note(None) == "persisted ForecastSnapshot"
    assert _forecast_note({"note": "  verified note  "}) == "verified note"
    assert _forecast_note({"note": []}) == "persisted ForecastSnapshot"

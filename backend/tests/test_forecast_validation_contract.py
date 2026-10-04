from __future__ import annotations

import pandas as pd

from app.models import Instrument
from app.services.forecast_service import ForecastService
from app.services.validation_service import ForecastValidationService


def test_validation_reuses_formal_forecast_frame_contract(db_session, monkeypatch):
    sentinel = {7: pd.DataFrame({"trade_date": ["2026-09-01"], "close": [1.0]})}

    def fake_frames(self, db, instruments):
        self._frame_history_hashes = {7: "formal-history-hash"}
        return sentinel

    monkeypatch.setattr(ForecastService, "_frames", fake_frames)
    service = ForecastValidationService()
    result = service._frames(db_session, [Instrument(id=7, ts_code="TEST.SH", name="Test", kind="ETF")])
    assert result is sentinel
    assert service._frame_history_hashes == {7: "formal-history-hash"}

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import select

from app.core.config import get_settings
from app.models import DailyBar, Instrument
from app.services.backtest_service import RotationBacktestService
from app.services.backtest_v05_service import RotationBacktestV05Service


def _history(rows: int = 140, *, missing_volume_at: int | None = None, missing_amount_at: int | None = None) -> pd.DataFrame:
    x = np.arange(rows, dtype=float)
    close = 100.0 + x * 0.15 + np.sin(x / 6.0)
    volume = 1000.0 + x * 5
    amount = volume * close
    if missing_volume_at is not None:
        volume[missing_volume_at] = np.nan
    if missing_amount_at is not None:
        amount[missing_amount_at] = np.nan
    return pd.DataFrame({
        "open": close - 0.2,
        "high": close + 0.8,
        "low": close - 0.8,
        "close": close,
        "volume": volume,
        "amount": amount,
        "source": "fixture",
        "fetched_at": pd.Timestamp("2026-10-04"),
    }, index=pd.bdate_range("2026-01-02", periods=rows).date)


def test_percentile_rank_preserves_missing_factor_evidence():
    ranked = RotationBacktestService._percentile_rank(pd.Series([1.0, np.nan, 3.0]))
    assert pd.isna(ranked.iloc[1])
    assert ranked.iloc[0] < ranked.iloc[2]


def test_v05_unknown_volume_is_not_zero_flow_and_price_structure_survives():
    service = RotationBacktestV05Service()
    history = _history(missing_volume_at=-3, missing_amount_at=-2)
    values = service._latest_flow_structure(history)
    for key in ("cmf20", "mfi14", "volume_ratio", "amount_ratio", "vwap_distance", "pullback"):
        assert pd.isna(values[key]), key
    for key in ("breakout20", "breakout55", "box_position", "box_range", "rsrs_z"):
        assert np.isfinite(values[key]), key


def test_zero_weight_missing_flow_does_not_poison_price_only_ablation_score():
    service = RotationBacktestV05Service()
    valid = _history()
    missing = _history(missing_volume_at=-3, missing_amount_at=-2)
    as_of = valid.index[-1]

    full = service._feature_table({"VALID.SH": valid, "MISSING.SH": missing}, as_of)
    assert np.isfinite(full.loc["VALID.SH", "score"])
    assert pd.isna(full.loc["MISSING.SH", "score"])

    original = deepcopy(service.config)
    service.config = deepcopy(original)
    service.config["factor_weights"] = {
        "return_5": .15, "return_20": .35, "return_60": .25,
        "trend_20": .15, "low_volatility": .10,
        "volume_flow": 0, "breakout": 0, "rsrs": 0, "structure": 0, "pullback": 0,
    }
    try:
        price_only = service._feature_table({"VALID.SH": valid, "MISSING.SH": missing}, as_of)
    finally:
        service.config = original
    assert np.isfinite(price_only.loc["MISSING.SH", "score"])
    assert np.isfinite(price_only.loc["MISSING.SH", "absolute_momentum"])


def test_backtest_loader_preserves_unknown_quantity_instead_of_zero(db_session):
    marker = uuid4().hex
    occupied = set(db_session.scalars(select(Instrument.ts_code).where(Instrument.ts_code.like("98%.SH"))).all())
    code = next((f"{value:06d}.SH" for value in range(980000, 990000) if f"{value:06d}.SH" not in occupied), None)
    assert code is not None
    inst = Instrument(ts_code=code, symbol=code[:6], name=marker, kind="ETF", enabled=True)
    db_session.add(inst)
    db_session.flush()
    day = date(2026, 1, 5)
    for idx in range(3):
        db_session.add(DailyBar(
            instrument_id=inst.id, trade_date=day + timedelta(days=idx),
            open=1.0 + idx * .01, high=1.1 + idx * .01, low=.9 + idx * .01, close=1.0 + idx * .01,
            volume=None if idx == 2 else 1000.0,
            amount=None if idx == 2 else 1000.0,
            source="fixture", adjust="none", quality_hash=f"{marker}-{idx}",
        ))
    db_session.flush()
    _, frames, exclusions, universe = RotationBacktestService()._load_frames(db_session)
    assert code not in {item["ts_code"] for item in exclusions}
    assert universe["survivorship_bias_controlled"] is False
    assert pd.isna(frames[code].iloc[-1]["volume"])
    assert pd.isna(frames[code].iloc[-1]["amount"])
    db_session.rollback()

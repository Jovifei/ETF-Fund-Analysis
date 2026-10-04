from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import DailyBar, Instrument
from app.providers import corporate_action_contract
from app.providers.corporate_action_contract import (
    CorporateActionEvent,
    canonical_research_history,
)
from app.services.backtest_service import RotationBacktestService
from app.services.factor_analysis_service import FactorAnalysisService


def _bar(day: date, close: float, *, adjust: str = "none", volume: float = 1000.0):
    return SimpleNamespace(
        trade_date=day,
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        pre_close=None,
        volume=volume,
        amount=close * volume,
        pct_change=None,
        adjust=adjust,
        source="akshare:em:v101",
        fetched_at=None,
        quality_hash="fixture",
    )


def test_canonical_research_history_reconciles_documented_split_but_rejects_mixed_basis():
    before = _bar(date(2025, 8, 1), 1.138, volume=500)
    after = _bar(date(2025, 8, 4), 0.572, volume=1000)
    selection = canonical_research_history([before, after], "512000.SH")
    assert selection.allowed is True
    assert selection.corporate_action_adjusted is True
    assert selection.price_basis == "official_split_adjusted_price_research_not_total_return"
    assert len(selection.price_basis_id or "") == 64
    assert [row.close for row in selection.rows] == pytest.approx([0.569, 0.572])

    mixed = canonical_research_history(
        [before, _bar(date(2025, 8, 4), 0.572, adjust="qfq")],
        "512000.SH",
    )
    assert mixed.allowed is False
    assert mixed.reason == "ambiguous_price_basis"


def test_transaction_backtest_refuses_adjusted_mixed_and_corporate_action_execution_series():
    service = RotationBacktestService()
    plain = [_bar(date(2026, 1, 5) + timedelta(days=i), 1.0 + i * .001) for i in range(5)]
    assert service._execution_history_issue(plain, "999991.SH") is None

    adjusted = [_bar(date(2026, 1, 5) + timedelta(days=i), 1.0, adjust="qfq") for i in range(5)]
    assert service._execution_history_issue(adjusted, "999991.SH") == "execution_requires_raw_unadjusted_prices"

    mixed = plain + [_bar(plain[-1].trade_date, 1.0, adjust="qfq")]
    assert service._execution_history_issue(mixed, "999991.SH") == "ambiguous_price_basis"

    split_rows = [
        _bar(date(2025, 8, 1), 1.138, volume=500),
        _bar(date(2025, 8, 4), 0.572, volume=1000),
    ]
    assert (
        service._execution_history_issue(split_rows, "512000.SH")
        == "corporate_action_position_accounting_not_implemented"
    )


def test_factor_panel_uses_evidence_bound_split_research_basis(monkeypatch, db_session):
    marker = uuid4().hex
    occupied = set(db_session.scalars(
        select(Instrument.ts_code).where(Instrument.ts_code.like("97%.SH"))
    ).all())
    code = next(
        (f"{value:06d}.SH" for value in range(970000, 980000) if f"{value:06d}.SH" not in occupied),
        None,
    )
    assert code is not None
    inst = Instrument(ts_code=code, symbol=code[:6], name=marker, kind="ETF", enabled=True)
    db_session.add(inst)
    db_session.flush()

    start = date(2025, 1, 2)
    ex_date = start + timedelta(days=90)
    monkeypatch.setitem(
        corporate_action_contract._OFFICIAL_ACTIONS,
        code,
        (CorporateActionEvent(code, ex_date - timedelta(days=1), ex_date, "1:2", "fixture_split_evidence"),),
    )

    for idx in range(180):
        day = start + timedelta(days=idx)
        adjusted_close = 1.0 + idx * 0.001
        before_split = day < ex_date
        raw_close = adjusted_close * (2.0 if before_split else 1.0)
        raw_volume = 500.0 if before_split else 1000.0
        db_session.add(DailyBar(
            instrument_id=inst.id,
            trade_date=day,
            open=raw_close,
            high=raw_close * 1.01,
            low=raw_close * .99,
            close=raw_close,
            volume=raw_volume,
            amount=adjusted_close * 1000.0,
            source="akshare:em:v101",
            adjust="none",
            quality_hash=f"{marker}-{idx}",
        ))
    db_session.flush()

    settings = get_settings().model_copy(update={"market_provider": "akshare"})
    panel = FactorAnalysisService(settings)._panel(db_session, instrument_ids={inst.id})
    assert not panel.empty
    assert set(panel["ts_code"]) == {code}
    assert panel["price_basis"].nunique() == 1
    assert panel["price_basis"].iloc[0] == "official_split_adjusted_price_research_not_total_return"
    assert panel["price_basis_id"].str.len().eq(64).all()
    contract = panel.attrs["research_input_contract"]
    assert contract["policy"] == "canonical_research_history_v1"
    assert contract["basis_by_instrument"][code]["corporate_action_adjusted"] is True
    assert not contract["excluded"]
    returns = panel["close"].pct_change().dropna()
    assert returns.abs().max() < 0.05
    db_session.rollback()

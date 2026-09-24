from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd

from app.core.config import Settings
from app.providers.akshare import AKShareProvider
from app.providers.composite import CompositeProvider
from app.providers.factory import build_provider
from app.providers.types import BarRecord
from app.providers.tencent import TencentProvider
from app.providers.unit_certification import DOCUMENTED_ENDPOINT_FIELDS


def test_tencent_history_normalizes_documented_share_and_cny_units() -> None:
    calls = []

    def history(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame([
            {"date": date(2026, 9, 17), "open": 1.0, "close": 1.1, "high": 1.2,
             "low": 0.9, "volume": 1000, "amount": 1100},
            {"date": date(2026, 9, 18), "open": 1.1, "close": 1.2, "high": 1.3,
             "low": 1.0, "volume": 1200, "amount": 1440},
        ])

    provider = TencentProvider(Settings(_env_file=None), ak_client=SimpleNamespace(stock_zh_a_hist_tx=history))
    rows = provider.fetch_daily_bars("510300.SH", date(2026, 9, 17), date(2026, 9, 18))

    assert [row.trade_date for row in rows] == [date(2026, 9, 17), date(2026, 9, 18)]
    assert rows[-1].volume == 1200
    assert rows[-1].amount == 1440
    assert rows[-1].raw_volume == 1200
    assert rows[-1].raw_amount == 1440
    assert rows[-1].source == "tencent:stock_zh_a_hist_tx:v101"
    assert rows[-1].source_upstream == "tencent"
    assert calls[0]["symbol"] == "sh510300"


def test_sina_preserves_raw_fields_without_promoting_unverified_amount() -> None:
    provider = AKShareProvider(
        Settings(_env_file=None),
        ak_client=SimpleNamespace(
            fund_etf_hist_em=lambda **_: [],
            fund_etf_hist_sina=lambda **_: [
                {"date": "2026-09-18", "open": 1.1, "high": 1.3, "low": 1.0,
                 "close": 1.2, "volume": 12, "amount": 1440},
            ],
        ),
    )

    rows = provider.fetch_daily_bars("510300.SH", date(2026, 9, 18), date(2026, 9, 18))

    assert rows[0].source == "akshare:sina:v101"
    assert rows[0].raw_volume == 12
    assert rows[0].raw_amount == 1440
    assert rows[0].volume is None
    assert rows[0].amount is None
    assert rows[0].source_upstream == "sina"


def test_public_composite_contains_tencent_independent_candidate() -> None:
    provider = build_provider(Settings(_env_file=None, market_provider="public_composite"))

    assert isinstance(provider, CompositeProvider)
    assert [item.name for item in provider.providers] == ["akshare", "sina", "tencent"]


def test_tencent_endpoint_contract_is_explicit() -> None:
    contract = DOCUMENTED_ENDPOINT_FIELDS["tencent:stock_zh_a_hist_tx:v101"]

    assert contract["volume_raw_unit"] == "shares"
    assert contract["amount_raw_unit"] == "cny"
    assert contract["volume_to_shares"] == 1
    assert contract["amount_to_cny"] == 1


def test_composite_prefers_complete_tencent_batch_over_sina_price_only() -> None:
    day = date(2026, 9, 18)
    sina = SimpleNamespace(
        name="akshare",
        fetch_daily_bars=lambda *_: [BarRecord(
            ts_code="510300.SH", trade_date=day, open=1.1, high=1.3, low=1.0, close=1.2,
            source="akshare:sina:v101", raw_volume=20, raw_amount=2400,
        )],
    )
    tencent = SimpleNamespace(
        name="tencent",
        fetch_daily_bars=lambda *_: [BarRecord(
            ts_code="510300.SH", trade_date=day, open=1.1, high=1.3, low=1.0, close=1.2,
            volume=2000, amount=2400, source="tencent:stock_zh_a_hist_tx:v101",
            raw_volume=2000, raw_amount=2400,
        )],
    )

    rows = CompositeProvider([sina, tencent]).fetch_daily_bars("510300.SH", day, day)

    assert rows[0].source == "tencent:stock_zh_a_hist_tx:v101"

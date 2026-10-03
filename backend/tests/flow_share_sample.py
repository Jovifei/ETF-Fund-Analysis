"""Fixed synthetic inputs captured against 422c5c4 before WU2 v2 changes."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

AS_OF = datetime(2026, 9, 2, 14, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

def add_sample(db):
    from app.models import EtfShareScale, IndicatorSnapshot, Instrument, QuoteSnapshot
    instrument = Instrument(
        ts_code="510390.SH", symbol="510390", name="流量样本",
        kind="ETF", exchange="SH", enabled=True,
    )
    db.add(instrument)
    db.flush()
    db.add(QuoteSnapshot(
        instrument_id=instrument.id, quote_time=AS_OF, fetched_at=AS_OF,
        timestamp_verified=False, price=2.4, pct_change=2.0, premium_rate=-0.5,
        iopv=2.41, latest_shares=1000, main_net_inflow=20,
        super_large_net_inflow=5, large_net_inflow=15,
        medium_net_inflow=-3, small_net_inflow=-17,
        flow_contract="etf-spot-flow-v1", source="akshare:em:v101",
        is_realtime=False, degraded_reason="public_quote_not_qualified",
        quality_hash="flow-golden-quote",
    ))
    db.add(EtfShareScale(
        instrument_id=instrument.id, trade_date=date(2026, 9, 2),
        shares=900, previous_trade_date=date(2026, 9, 1), previous_shares=1000,
        share_delta=-100, share_delta_ratio=-0.1, day_over_day=True,
        proxy="份额减少", source="akshare:fund_etf_scale_sse", exchange="SH",
        fetched_at=AS_OF, quality_hash="flow-golden-scale",
    ))
    db.add(IndicatorSnapshot(
        instrument_id=instrument.id, as_of_date=date(2026, 9, 2),
        version="ind-test", generated_at=AS_OF,
        values_json={
            "close": 2.4, "ma5": 2.4, "ma10": 2.35, "ma20": 2.22,
            "ma30": 2.1, "macd_dif": 0.02, "macd_dea": 0.01,
            "macd_hist": 0.01, "kdj_k": 55, "kdj_d": 50, "kdj_j": 70,
            "rsi14": 55, "volume_ratio": 1.5, "return_1d": 0.02,
            "return_5d": 0.03, "td_buy_setup": 0, "td_sell_setup": 0,
        },
        technical_score=70, risk_score=30, trend_label="up", data_quality=80,
        input_hash="ind-flow-golden",
    ))
    db.flush()
    return instrument

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.core.config import Settings, get_settings
from app.providers.base import CapabilityUnavailable, MarketProvider
from app.providers.bounded_sdk import BoundedSDK
from app.providers.types import BarRecord, InstrumentRecord
from app.utils.numbers import finite_or_none


class TencentProvider(MarketProvider):
    """Bounded Tencent daily history adapter for independent public evidence."""

    name = "tencent"
    source = "tencent:stock_zh_a_hist_tx:v101"

    def __init__(self, settings: Settings | None = None, *, ak_client: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self.ak = ak_client or BoundedSDK("akshare", self.settings.akshare_timeout_seconds)
        self._watchlist = self.settings.load_watchlist()["instruments"]

    @staticmethod
    def _date(value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value or "")[:10]
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return None

    @staticmethod
    def _symbol(ts_code: str) -> str:
        symbol, exchange = ts_code.upper().split(".", 1)
        if exchange not in {"SH", "SZ"}:
            raise CapabilityUnavailable("exchange_not_supported")
        return exchange.lower() + symbol

    def list_instruments(self, codes: list[str] | None = None) -> list[InstrumentRecord]:
        selected = {code.upper() for code in codes} if codes else None
        return [
            InstrumentRecord(
                ts_code=item["ts_code"].upper(),
                symbol=item["symbol"],
                name=item["name"],
                kind=item.get("kind", "ETF"),
                exchange=item["ts_code"].split(".")[-1],
                theme_l1=item.get("theme_l1"),
                theme_l2=item.get("theme_l2"),
                benchmark=item.get("benchmark"),
                enabled=bool(item.get("enabled", True)),
                metadata={"provider": self.name},
            )
            for item in self._watchlist
            if not selected or item["ts_code"].upper() in selected or item["symbol"] in selected
        ]

    def fetch_daily_bars(self, ts_code: str, start_date: date, end_date: date) -> list[BarRecord]:
        frame = self.ak.stock_zh_a_hist_tx(
            symbol=self._symbol(ts_code),
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            adjust="",
            timeout=min(15.0, self.settings.akshare_timeout_seconds),
        )
        records = frame.to_dict(orient="records") if hasattr(frame, "to_dict") else list(frame or [])
        rows: list[BarRecord] = []
        for item in records:
            trade_date = self._date(item.get("date"))
            values = {
                key: finite_or_none(item.get(key))
                for key in ("open", "high", "low", "close", "volume", "amount")
            }
            if trade_date is None or not start_date <= trade_date <= end_date:
                continue
            if any(values[key] is None for key in ("open", "high", "low", "close")):
                continue
            rows.append(
                BarRecord(
                    ts_code=ts_code,
                    trade_date=trade_date,
                    open=values["open"] or 0,
                    high=values["high"] or 0,
                    low=values["low"] or 0,
                    close=values["close"] or 0,
                    volume=values["volume"],
                    amount=values["amount"],
                    adjust="none",
                    source=self.source,
                    raw_volume=values["volume"],
                    raw_amount=values["amount"],
                    volume_raw_unit="shares",
                    amount_raw_unit="cny",
                    source_upstream="tencent",
                    endpoint_version="stock_zh_a_hist_tx:v101",
                )
            )
        rows.sort(key=lambda item: item.trade_date)
        for index, row in enumerate(rows):
            if index and row.pre_close is None:
                row.pre_close = rows[index - 1].close
        return rows

    def fetch_spot_quotes(self, codes: list[str]):
        raise CapabilityUnavailable("quotes_unavailable")

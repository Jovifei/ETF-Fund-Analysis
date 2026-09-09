from __future__ import annotations

import logging
import time as time_module
from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.core.config import Settings, get_settings
from app.providers.base import CapabilityUnavailable, MarketProvider, ProviderError
from app.providers.types import BarRecord, InstrumentRecord, NewsRecord, QuoteRecord
from app.utils.numbers import finite_or_none
from app.providers.bounded_sdk import BoundedSDK, first

logger = logging.getLogger(__name__)


class TushareProvider(MarketProvider):
    name = "tushare"

    def __init__(self, settings: Settings | None = None, *, pro_client=None) -> None:
        self.settings = settings or get_settings()
        if pro_client is None and not self.settings.tushare_token:
            raise CapabilityUnavailable("credentials_missing")
        self.ts = None
        self.pro = pro_client if pro_client is not None else BoundedSDK("tushare", self.settings.tushare_timeout_seconds, self.settings.tushare_token)
        self.tz = ZoneInfo(self.settings.timezone_name)
        self._watchlist = self.settings.load_watchlist()["instruments"]

    @staticmethod
    def _date_text(value: date) -> str:
        return value.strftime("%Y%m%d")

    @staticmethod
    def _records(frame: Any) -> list[dict[str, Any]]:
        if frame is None:
            return []
        if hasattr(frame, "to_dict"):
            return frame.to_dict(orient="records")
        if isinstance(frame, list):
            return frame
        return []

    def resolve_instrument(self, code: str) -> InstrumentRecord | None:
        """按代码在上游 fund_basic 全量场内基金中解析一个标的。

        支持三种输入：`512480.SH` 完整代码、`512480` 6 位 symbol。
        上游不可达/未命中返回 None，由调用方决定是否允许人工确认后入库。
        """
        needle = code.strip().upper()
        if not needle:
            return None
        try:
            frame = self.pro.fund_basic(market="E")
        except Exception as exc:  # 权限或网络问题按能力缺失处理
            logger.warning("Tushare resolve_instrument unavailable: %s", type(exc).__name__)
            return None
        for row in self._records(frame):
            ts_code = str(row.get("ts_code") or "").upper()
            symbol = ts_code.split(".", 1)[0]
            if ts_code != needle and symbol != needle:
                continue
            name = str(row.get("name") or "")
            kind = "ETF" if "ETF" in name.upper() else ("LOF" if "LOF" in name.upper() else None)
            if kind is None or ts_code.split(".")[-1] not in {"SH", "SZ"}:
                return None
            return InstrumentRecord(
                ts_code=ts_code,
                symbol=symbol,
                name=name or ts_code,
                kind=kind,
                exchange=ts_code.split(".", 1)[-1] if "." in ts_code else None,
                enabled=True,
                metadata={
                    "management": row.get("management"),
                    "found_date": row.get("found_date"),
                    "list_date": row.get("list_date"),
                    "m_fee": row.get("m_fee"),
                    "c_fee": row.get("c_fee"),
                },
            )
        return None

    def fetch_index_bars(self, symbol, start_date, end_date):
        from app.providers.index_history import tushare_index
        return tushare_index(self, symbol, start_date, end_date)

    def list_instruments(self, codes: list[str] | None = None) -> list[InstrumentRecord]:
        selected = {c.upper() for c in codes} if codes else None
        config_items = [
            item
            for item in self._watchlist
            if not selected or item["ts_code"].upper() in selected or item["symbol"] in selected
        ]
        enrich: dict[str, dict[str, Any]] = {}
        try:
            frame = self.pro.fund_basic(market="E", status="L")
            for row in self._records(frame):
                code = str(row.get("ts_code") or "").upper()
                if code:
                    enrich[code] = row
        except Exception as exc:  # permission varies by account
            logger.warning("Tushare fund_basic enrichment unavailable: %s", type(exc).__name__)

        result: list[InstrumentRecord] = []
        for item in config_items:
            row = enrich.get(item["ts_code"].upper(), {})
            name = str(row.get("name") or item["name"])
            exchange = item["ts_code"].split(".")[-1]
            metadata = {
                "management": row.get("management"),
                "custodian": row.get("custodian"),
                "fund_type": row.get("fund_type"),
                "found_date": row.get("found_date"),
                "due_date": row.get("due_date"),
                "list_date": row.get("list_date"),
                "issue_amount": row.get("issue_amount"),
                "m_fee": row.get("m_fee"),
                "c_fee": row.get("c_fee"),
            }
            result.append(
                InstrumentRecord(
                    ts_code=item["ts_code"].upper(),
                    symbol=item["symbol"],
                    name=name,
                    kind=item.get("kind", "ETF"),
                    exchange=exchange,
                    theme_l1=item.get("theme_l1"),
                    theme_l2=item.get("theme_l2"),
                    benchmark=item.get("benchmark"),
                    enabled=bool(item.get("enabled", True)),
                    metadata={k: v for k, v in metadata.items() if v not in (None, "")},
                )
            )
        return result

    def fetch_daily_bars(self, ts_code: str, start_date: date, end_date: date) -> list[BarRecord]:
        try:
            frame = self.pro.fund_daily(
                ts_code=ts_code,
                start_date=self._date_text(start_date),
                end_date=self._date_text(end_date),
            )
        except Exception as exc:
            raise ProviderError(f"Tushare fund_daily failed for {ts_code}: {type(exc).__name__}") from exc
        rows = self._records(frame)
        if len(rows) >= 5000:
            raise ProviderError("daily_response_may_be_truncated")
        result: list[BarRecord] = []
        for row in rows:
            if row.get("ts_code") and str(row["ts_code"]).upper() != ts_code.upper():
                raise ProviderError("history_identity_mismatch")
            raw_date = str(row.get("trade_date") or "")
            if len(raw_date) != 8:
                continue
            trade_date = datetime.strptime(raw_date, "%Y%m%d").date()
            if not start_date <= trade_date <= end_date:
                continue
            close = finite_or_none(row.get("close"))
            open_price = finite_or_none(row.get("open"))
            high = finite_or_none(row.get("high"))
            low = finite_or_none(row.get("low"))
            if None in (close, open_price, high, low):
                continue
            result.append(
                BarRecord(
                    ts_code=ts_code,
                    trade_date=trade_date,
                    open=open_price or 0,
                    high=high or 0,
                    low=low or 0,
                    close=close or 0,
                    pre_close=finite_or_none(row.get("pre_close")),
                    volume=(finite_or_none(first(row, "vol", "volume")) * 100 if finite_or_none(first(row, "vol", "volume")) is not None else None),
                    amount=(finite_or_none(row.get("amount")) * 1000 if finite_or_none(row.get("amount")) is not None else None),
                    pct_change=finite_or_none(first(row, "pct_chg", "pct_change")),
                    adjust="none",
                    source="tushare:fund_daily:v101",
                )
            )
        result.sort(key=lambda item: item.trade_date)
        return result

    def fetch_minute_bars(self, ts_code: str, interval: str, start_date: date, end_date: date) -> list[BarRecord]:
        """Permission-dependent official ETF minutes; no synthetic daily fallback.

        etf_mins uses shares/CNY already. Read-only history, not an assertion of
        point-in-time availability or execution qualification.
        """
        if interval not in {"30m", "60m"}:
            raise CapabilityUnavailable("minute_interval_not_enabled")
        if (end_date - start_date).days > 30 or start_date > end_date:
            raise ValueError("minute_request_window_must_be_0_to_30_days")
        rows = self._records(self.pro.etf_mins(ts_code=ts_code, freq=interval.removesuffix("m") + "min",
            start_date=start_date.isoformat() + " 09:00:00", end_date=end_date.isoformat() + " 15:30:00"))
        if len(rows) >= 8000:
            raise ProviderError("minute_response_may_be_truncated")
        result = []
        for row in rows:
            if str(row.get("ts_code", "")).upper() != ts_code.upper():
                raise ProviderError("minute_identity_mismatch")
            observed = self._parse_datetime(row.get("trade_time"))
            if observed is None:
                raise ProviderError("minute_source_time_missing")
            values = {key: finite_or_none(row.get(key)) for key in ("open", "high", "low", "close")}
            if any(value is None for value in values.values()):
                raise ProviderError("minute_ohlc_missing")
            result.append(BarRecord(ts_code=ts_code, trade_date=observed, **values,
                volume=finite_or_none(first(row, "vol", "volume")), amount=finite_or_none(row.get("amount")),
                source="tushare:etf_mins:v101"))
        return sorted(result, key=lambda item: item.trade_date)

    def _call_candidate(self, name: str, codes: list[str]) -> list[dict[str, Any]]:
        # No speculative stock/legacy endpoints, no missing SH topic. Batch at
        # most two exchange requests; filter wildcard results by exact identity.
        if name != "rt_etf_k" or not codes:
            return []
        rows = []
        fields = "ts_code,name,pre_close,high,open,low,close,vol,amount,trade_time"
        for exchange in ("SH", "SZ"):
            group = [code for code in dict.fromkeys(codes) if code.endswith("." + exchange)]
            if not group:
                continue
            params = {"ts_code": group[0] if len(group) == 1 else ("5*.SH" if exchange == "SH" else "1*.SZ"), "fields": fields}
            if exchange == "SH":
                params["topic"] = "HQ_FND_TICK"
            try:
                rows.extend(self._records(self.pro.rt_etf_k(**params)))
            except Exception as exc:
                logger.info("Tushare ETF realtime %s unavailable: %s", exchange, type(exc).__name__)
        return rows

    @staticmethod
    def _row_code(row: dict[str, Any]) -> str:
        value = str(
            row.get("ts_code")
            or row.get("code")
            or row.get("symbol")
            or row.get("代码")
            or ""
        ).upper()
        if value and "." not in value and len(value) == 6:
            suffix = "SH" if value.startswith(("5", "6")) else "SZ"
            value = f"{value}.{suffix}"
        return value

    def _quote_timestamp(self, row: dict[str, Any], fallback: datetime) -> datetime | None:
        combined_date = row.get("trade_date") or row.get("date") or row.get("交易日")
        combined_time = row.get("trade_time") or row.get("time") or row.get("更新时间")
        if combined_date and combined_time:
            parsed = self._parse_datetime(f"{combined_date} {combined_time}")
            if parsed is not None:
                return parsed
        for key in ("datetime", "trade_datetime", "timestamp", "更新时间", "update_time"):
            parsed = self._parse_datetime(row.get(key))
            if parsed is not None:
                return parsed
        # A time-of-day cannot establish the date: never attach today's date
        # to Friday's cached quote on a weekend or after a source failure.
        if combined_time and len(str(combined_time).strip()) > 10:
            return self._parse_datetime(combined_time)
        return None

    def fetch_spot_quotes(self, codes: list[str], *, allow_daily_fallback: bool = True) -> list[QuoteRecord]:
        rows: list[dict[str, Any]] = []
        resolved_by: str | None = None
        for name in [item.strip() for item in self.settings.tushare_realtime_candidates.split(",") if item.strip()]:
            rows = self._call_candidate(name, codes)
            if rows:
                resolved_by = name
                break

        now = datetime.now(self.tz)
        quotes: list[QuoteRecord] = []
        if rows:
            by_code = {self._row_code(row): row for row in rows if self._row_code(row)}
            for code in codes:
                row = by_code.get(code.upper())
                if not row:
                    continue
                price = finite_or_none(
                    row.get("price") or row.get("close") or row.get("最新价") or row.get("PRICE")
                )
                if price is None:
                    continue
                pre_close = finite_or_none(row.get("pre_close") or row.get("昨收") or row.get("PRE_CLOSE"))
                pct = finite_or_none(first(row, "pct_chg", "pct_change", "涨跌幅"))
                if pct is None and pre_close:
                    pct = (price / pre_close - 1) * 100
                source_time = self._quote_timestamp(row, now)
                quotes.append(
                    QuoteRecord(
                        ts_code=code,
                        quote_time=source_time or now,
                        price=price,
                        open=finite_or_none(row.get("open") or row.get("今开")),
                        high=finite_or_none(row.get("high") or row.get("最高")),
                        low=finite_or_none(row.get("low") or row.get("最低")),
                        pre_close=pre_close,
                        pct_change=pct,
                        volume=finite_or_none(first(row, "vol", "volume", "成交量")),
                        amount=finite_or_none(first(row, "amount", "成交额")),
                        premium_rate=finite_or_none(row.get("premium_rate") or row.get("溢价率")),
                        source=f"{self.name}:{resolved_by}:v101",
                        is_realtime=source_time is not None,
                        degraded_reason=(
                            None if source_time is not None else
                            "source_timestamp_missing_observed_at_fetch"
                        ),
                    )
                )
        if quotes:
            return quotes

        if not allow_daily_fallback:
            raise CapabilityUnavailable("realtime_unavailable_try_next_provider")

        # Permission-safe degradation: latest official fund_daily close, explicitly marked non-realtime.
        degraded: list[QuoteRecord] = []
        for code in codes:
            bars = self.fetch_daily_bars(code, now.date() - timedelta(days=12), now.date())
            if not bars:
                continue
            latest = bars[-1]
            degraded.append(
                QuoteRecord(
                    ts_code=code,
                    quote_time=datetime.combine(latest.trade_date, datetime.min.time(), tzinfo=self.tz),
                    price=latest.close,
                    open=latest.open,
                    high=latest.high,
                    low=latest.low,
                    pre_close=latest.pre_close,
                    pct_change=latest.pct_change,
                    volume=latest.volume,
                    amount=latest.amount,
                    premium_rate=None,
                    source="tushare:fund_daily:v101",
                    is_realtime=False,
                    degraded_reason="账户实时 ETF/LOF 接口不可用，退化为最近交易日日线收盘；不可作为盘中操作依据",
                )
            )
        if not degraded:
            raise CapabilityUnavailable("Tushare 实时与日线行情均不可用")
        return degraded

    def fetch_current_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        """Composite must try another current source before any per-ETF daily I/O."""
        return self.fetch_spot_quotes(codes, allow_daily_fallback=False)

    def fetch_news(self, since_hours: int = 24) -> list[NewsRecord]:
        now = datetime.now(self.tz)
        start = now - timedelta(hours=since_hours)
        candidates = ["news", "major_news", "cctv_news"]
        errors: list[str] = []
        successful_call = False
        for name in candidates:
            function = getattr(self.pro, name, None)
            if not function:
                continue
            variants = [
                {"start_date": start.strftime("%Y-%m-%d %H:%M:%S"), "end_date": now.strftime("%Y-%m-%d %H:%M:%S")},
                {"start_date": start.strftime("%Y%m%d"), "end_date": now.strftime("%Y%m%d")},
            ]
            for params in variants:
                started = time_module.perf_counter()
                try:
                    rows = self._records(function(**params))
                    successful_call = True
                    if not rows:
                        continue
                    result: list[NewsRecord] = []
                    for idx, row in enumerate(rows):
                        title = str(row.get("title") or row.get("content") or row.get("新闻标题") or "").strip()
                        if not title:
                            continue
                        raw_time = row.get("datetime") or row.get("pub_time") or row.get("date")
                        published = self._parse_datetime(raw_time)
                        if published is None or not start <= published <= now:
                            continue
                        source_id = str(row.get("id") or row.get("news_id") or f"{name}-{published.timestamp()}-{idx}")
                        result.append(
                            NewsRecord(
                                source=f"tushare:{name}",
                                source_id=source_id,
                                title=title[:500],
                                summary=str(row.get("content") or "")[:4000] or None,
                                url=row.get("url"),
                                published_at=published,
                            )
                        )
                    if result:
                        logger.info("Tushare news %s returned %s in %.0fms", name, len(result), (time_module.perf_counter() - started) * 1000)
                        return result
                except Exception as exc:
                    errors.append(f"{name}: {type(exc).__name__}")
                    logger.info("Tushare news candidate %s failed: %s", name, type(exc).__name__)
        if not successful_call and errors:
            raise CapabilityUnavailable("Tushare 新闻接口均不可用；" + "; ".join(errors))
        return []

    def _parse_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.astimezone(self.tz) if value.tzinfo else value.replace(tzinfo=self.tz)
        text = str(value).strip()
        if len(text) >= 19 and ("T" in text or "+" in text or text.endswith("Z")):
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
                return parsed.replace(tzinfo=self.tz) if parsed.tzinfo is None else parsed.astimezone(self.tz)
            except ValueError:
                pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d %H:%M:%S", "%Y%m%d%H%M%S", "%Y-%m-%d", "%Y%m%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed.replace(tzinfo=self.tz)
            except ValueError:
                continue
        return None

    def is_trade_day(self, day: date) -> bool:
        try:
            frame = self.pro.trade_cal(
                exchange="SSE", start_date=self._date_text(day), end_date=self._date_text(day)
            )
            rows = self._records(frame)
            if rows:
                return str(rows[0].get("is_open")) in {"1", "True", "true"}
        except Exception as exc:
            logger.warning("Tushare trade_cal failed, weekday fallback: %s", type(exc).__name__)
        return day.weekday() < 5

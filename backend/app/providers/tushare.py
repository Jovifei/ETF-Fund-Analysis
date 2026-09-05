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

logger = logging.getLogger(__name__)


class TushareProvider(MarketProvider):
    name = "tushare"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.tushare_token:
            raise ProviderError("TUSHARE_TOKEN 未配置")
        try:
            import tushare as ts  # type: ignore
        except ImportError as exc:
            raise ProviderError("未安装 tushare；请安装 market 可选依赖") from exc
        self.ts = ts
        self.pro = ts.pro_api(self.settings.tushare_token)
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
            logger.warning("Tushare resolve_instrument unavailable: %s", exc)
            return None
        for row in self._records(frame):
            ts_code = str(row.get("ts_code") or "").upper()
            symbol = ts_code.split(".", 1)[0]
            if ts_code != needle and symbol != needle:
                continue
            name = str(row.get("name") or "")
            kind = "ETF" if "ETF" in name else ("LOF" if "LOF" in name else "ETF")
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
            logger.warning("Tushare fund_basic enrichment unavailable: %s", exc)

        result: list[InstrumentRecord] = []
        for item in config_items:
            row = enrich.get(item["ts_code"].upper(), {})
            name = str(row.get("name") or item["name"])
            exchange = str(row.get("market") or item["ts_code"].split(".")[-1])
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
            raise ProviderError(f"Tushare fund_daily failed for {ts_code}: {exc}") from exc
        rows = self._records(frame)
        result: list[BarRecord] = []
        for row in rows:
            raw_date = str(row.get("trade_date") or "")
            if len(raw_date) != 8:
                continue
            trade_date = datetime.strptime(raw_date, "%Y%m%d").date()
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
                    volume=finite_or_none(row.get("vol") or row.get("volume")),
                    amount=finite_or_none(row.get("amount")),
                    pct_change=finite_or_none(row.get("pct_chg") or row.get("pct_change")),
                    adjust="none",
                    source=self.name,
                )
            )
        result.sort(key=lambda item: item.trade_date)
        return result

    def _call_candidate(self, name: str, codes: list[str]) -> list[dict[str, Any]]:
        function: Callable[..., Any] | None = getattr(self.pro, name, None) or getattr(self.ts, name, None)
        if function is None:
            return []
        params_variants = [
            {"ts_code": ",".join(codes)},
            {"ts_code": codes[0]} if len(codes) == 1 else {},
            {"symbols": ",".join(code.split(".")[0] for code in codes)},
        ]
        for params in params_variants:
            if not params:
                continue
            try:
                frame = function(**params)
                rows = self._records(frame)
                if rows:
                    return rows
            except Exception as exc:
                logger.info("Tushare realtime candidate %s params=%s failed: %s", name, list(params), exc)
        return []

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
        if combined_time:
            text = str(combined_time).strip()
            for fmt in ("%H:%M:%S", "%H:%M"):
                try:
                    parsed_time = datetime.strptime(text, fmt).time()
                    return datetime.combine(fallback.date(), parsed_time, tzinfo=self.tz)
                except ValueError:
                    continue
        return None

    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
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
                row = by_code.get(code.upper()) or next(
                    (item for key, item in by_code.items() if key.split(".")[0] == code.split(".")[0]),
                    None,
                )
                if not row:
                    continue
                price = finite_or_none(
                    row.get("price") or row.get("close") or row.get("最新价") or row.get("PRICE")
                )
                if price is None:
                    continue
                pre_close = finite_or_none(row.get("pre_close") or row.get("昨收") or row.get("PRE_CLOSE"))
                pct = finite_or_none(row.get("pct_chg") or row.get("pct_change") or row.get("涨跌幅"))
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
                        volume=finite_or_none(row.get("vol") or row.get("volume") or row.get("成交量")),
                        amount=finite_or_none(row.get("amount") or row.get("成交额")),
                        premium_rate=finite_or_none(row.get("premium_rate") or row.get("溢价率")),
                        source=f"{self.name}:{resolved_by}",
                        is_realtime=source_time is not None,
                        degraded_reason=(
                            None if source_time is not None else
                            "上游实时接口未提供可验证行情时间；不可作为盘中操作依据"
                        ),
                    )
                )
        if quotes:
            return quotes

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
                    source=f"{self.name}:fund_daily",
                    is_realtime=False,
                    degraded_reason="账户实时 ETF/LOF 接口不可用，退化为最近交易日日线收盘；不可作为盘中操作依据",
                )
            )
        if not degraded:
            raise CapabilityUnavailable("Tushare 实时与日线行情均不可用")
        return degraded

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
                        published = self._parse_datetime(raw_time) or now
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
                    errors.append(f"{name}: {type(exc).__name__}: {exc}")
                    logger.info("Tushare news candidate %s failed: %s", name, exc)
        if not successful_call and errors:
            raise CapabilityUnavailable("Tushare 新闻接口均不可用；" + "; ".join(errors))
        return []

    def _parse_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.astimezone(self.tz) if value.tzinfo else value.replace(tzinfo=self.tz)
        text = str(value).strip()
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
            logger.warning("Tushare trade_cal failed, weekday fallback: %s", exc)
        return day.weekday() < 5

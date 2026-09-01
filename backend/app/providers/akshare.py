from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import Settings, get_settings
from app.providers.base import MarketProvider, ProviderError
from app.providers.types import BarRecord, InstrumentRecord, QuoteRecord, SectorRecord
from app.utils.numbers import finite_or_none

logger = logging.getLogger(__name__)


class AKShareProvider(MarketProvider):
    name = "akshare"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        try:
            import akshare as ak  # type: ignore
        except ImportError as exc:
            raise ProviderError("未安装 akshare；请安装 market 可选依赖") from exc
        self.ak = ak
        self.tz = ZoneInfo(self.settings.timezone_name)
        self._watchlist = self.settings.load_watchlist()["instruments"]

    @staticmethod
    def _records(frame: Any) -> list[dict[str, Any]]:
        if frame is None:
            return []
        return frame.to_dict(orient="records") if hasattr(frame, "to_dict") else list(frame)

    def list_instruments(self, codes: list[str] | None = None) -> list[InstrumentRecord]:
        selected = {c.upper() for c in codes} if codes else None
        result: list[InstrumentRecord] = []
        for item in self._watchlist:
            if selected and item["ts_code"].upper() not in selected and item["symbol"] not in selected:
                continue
            result.append(
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
            )
        return result

    def fetch_daily_bars(self, ts_code: str, start_date: date, end_date: date) -> list[BarRecord]:
        symbol = ts_code.split(".")[0]
        kind = next((item.get("kind", "ETF") for item in self._watchlist if item["symbol"] == symbol), "ETF")
        function = self.ak.fund_etf_hist_em if kind.upper() == "ETF" else self.ak.fund_lof_hist_em
        try:
            frame = function(
                symbol=symbol,
                period="daily",
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust="",
            )
        except TypeError:
            frame = function(symbol=symbol, period="daily", start_date=start_date.strftime("%Y%m%d"), end_date=end_date.strftime("%Y%m%d"))
        except Exception as exc:
            raise ProviderError(f"AKShare history failed for {ts_code}: {exc}") from exc
        result: list[BarRecord] = []
        for row in self._records(frame):
            raw_date = row.get("日期") or row.get("date")
            try:
                trade_date = raw_date.date() if hasattr(raw_date, "date") else datetime.strptime(str(raw_date)[:10], "%Y-%m-%d").date()
            except Exception:
                continue
            close = finite_or_none(row.get("收盘") or row.get("close"))
            open_price = finite_or_none(row.get("开盘") or row.get("open"))
            high = finite_or_none(row.get("最高") or row.get("high"))
            low = finite_or_none(row.get("最低") or row.get("low"))
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
                    pre_close=None,
                    volume=finite_or_none(row.get("成交量") or row.get("volume")),
                    amount=finite_or_none(row.get("成交额") or row.get("amount")),
                    pct_change=finite_or_none(row.get("涨跌幅") or row.get("pct_change")),
                    adjust="none",
                    source=self.name,
                )
            )
        result.sort(key=lambda item: item.trade_date)
        for idx, item in enumerate(result):
            if idx > 0 and item.pre_close is None:
                item.pre_close = result[idx - 1].close
        return result

    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        wanted = {code.split(".")[0]: code for code in codes}
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        for function_name in ("fund_etf_spot_em", "fund_lof_spot_em"):
            function = getattr(self.ak, function_name, None)
            if function is None:
                continue
            try:
                rows.extend(self._records(function()))
            except Exception as exc:
                errors.append(f"{function_name}: {type(exc).__name__}: {exc}")
        now = datetime.now(self.tz)
        result: list[QuoteRecord] = []
        for row in rows:
            symbol = str(row.get("代码") or row.get("symbol") or row.get("基金代码") or "")
            ts_code = wanted.get(symbol)
            if not ts_code:
                continue
            price = finite_or_none(row.get("最新价") or row.get("price") or row.get("当前价"))
            if price is None:
                continue
            pre_close = finite_or_none(row.get("昨收") or row.get("pre_close"))
            pct = finite_or_none(row.get("涨跌幅") or row.get("pct_change"))
            if pct is None and pre_close:
                pct = (price / pre_close - 1) * 100
            result.append(
                QuoteRecord(
                    ts_code=ts_code,
                    quote_time=now,
                    price=price,
                    open=finite_or_none(row.get("今开") or row.get("开盘")),
                    high=finite_or_none(row.get("最高")),
                    low=finite_or_none(row.get("最低")),
                    pre_close=pre_close,
                    pct_change=pct,
                    volume=finite_or_none(row.get("成交量")),
                    amount=finite_or_none(row.get("成交额")),
                    premium_rate=finite_or_none(row.get("溢价率")),
                    source=self.name,
                    is_realtime=True,
                )
            )
        if not result:
            raise ProviderError("AKShare spot returned no matching rows; " + "; ".join(errors))
        return result

    # 板块数据源优先级：东财（含平盘家数）→ 同花顺（无平盘家数，total 按 up+down 计）。
    # 两者都走 AKShare 公开函数，不在业务层硬编码网页接口。
    _SECTOR_SOURCES = (
        ("em", "stock_board_industry_name_em", "板块名称"),
        ("ths", "stock_board_industry_summary_ths", "板块"),
    )

    def fetch_sector_snapshots(self, trade_date: date | None = None) -> list[SectorRecord]:
        """获取行业板块涨跌家数快照（K线企稳看板用）。

        主源为 AKShare 东财行业板块实时行情（stock_board_industry_name_em）；
        东财不可达或返回空时自动降级到同花顺行业汇总（stock_board_industry_summary_ths）。
        两个源都失败才抛 ProviderError，由调用方决定降级（板块列显示 "—"）。

        Args:
            trade_date: 目标交易日，缺省为本地时区今天。

        Returns:
            SectorRecord 列表（每板块一条）。
        """
        target = trade_date or date.today()
        errors: list[str] = []
        for source_key, func_name, name_field in self._SECTOR_SOURCES:
            function = getattr(self.ak, func_name, None)
            if function is None:
                errors.append(f"{source_key}: 接口不可用（akshare 版本过旧）")
                continue
            try:
                frame = function()
            except Exception as exc:
                errors.append(f"{source_key}: {exc}")
                logger.warning("sector source %s failed: %s", source_key, exc)
                continue
            result = self._parse_sector_frame(frame, target, name_field)
            if not result:
                errors.append(f"{source_key}: 返回空数据")
                logger.warning("sector source %s returned no rows", source_key)
                continue
            logger.info("sector snapshots from %s: %d rows", source_key, len(result))
            return result
        raise ProviderError("AKShare sector fetch failed: " + "; ".join(errors))

    def _parse_sector_frame(
        self,
        frame: Any,
        target: date,
        name_field: str,
    ) -> list[SectorRecord]:
        """把板块 DataFrame 归一化为 SectorRecord 列表。

        Args:
            frame: AKShare 返回的板块 DataFrame。
            target: 目标交易日。
            name_field: 板块名称列名（东财 "板块名称" / 同花顺 "板块"）。

        Returns:
            SectorRecord 列表；无有效行时返回空列表。
        """
        result: list[SectorRecord] = []
        for row in self._records(frame):
            name = str(row.get(name_field) or row.get("板块名称") or row.get("name") or "").strip()
            if not name:
                continue
            up_count = finite_or_none(row.get("上涨家数") or row.get("up_count")) or 0
            down_count = finite_or_none(row.get("下跌家数") or row.get("down_count")) or 0
            flat_count = finite_or_none(row.get("平盘家数") or row.get("flat_count")) or 0
            total = int(up_count + down_count + flat_count)
            result.append(
                SectorRecord(
                    sector_name=name,
                    trade_date=target,
                    up_count=int(up_count),
                    down_count=int(down_count),
                    flat_count=int(flat_count),
                    total_count=total,
                    pct_change=finite_or_none(row.get("涨跌幅") or row.get("pct_change")),
                    source=self.name,
                )
            )
        return result

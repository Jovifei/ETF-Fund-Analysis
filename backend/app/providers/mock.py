from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import Settings, get_settings
from app.market_context.contracts import (
    FreshnessStatus,
    MarketContextItem,
    MarketContextObservation,
    VerificationStatus,
)
from app.providers.base import MarketProvider
from app.providers.types import BarRecord, InstrumentRecord, NewsRecord, QuoteRecord, SectorRecord


class MockProvider(MarketProvider):
    name = "mock"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.tz = ZoneInfo(self.settings.timezone_name)
        self._watchlist = self.settings.load_watchlist()["instruments"]

    def list_instruments(self, codes: list[str] | None = None) -> list[InstrumentRecord]:
        selected = {c.upper() for c in codes} if codes else None
        result: list[InstrumentRecord] = []
        for item in self._watchlist:
            if selected and item["ts_code"].upper() not in selected and item["symbol"] not in selected:
                continue
            exchange = item["ts_code"].split(".")[-1] if "." in item["ts_code"] else None
            result.append(
                InstrumentRecord(
                    ts_code=item["ts_code"],
                    symbol=item["symbol"],
                    name=item["name"],
                    kind=item.get("kind", "ETF"),
                    exchange=exchange,
                    theme_l1=item.get("theme_l1"),
                    theme_l2=item.get("theme_l2"),
                    benchmark=item.get("benchmark"),
                    enabled=bool(item.get("enabled", True)),
                    metadata={"mock": True},
                )
            )
        return result

    def resolve_instrument(self, code: str) -> InstrumentRecord | None:
        """Mock 只能解析其内置 watchlist 内的标的（含 6 位 symbol）。"""
        needle = code.strip().upper()
        for item in self._watchlist:
            if item["ts_code"].upper() == needle or item["symbol"] == needle:
                exchange = item["ts_code"].split(".")[-1] if "." in item["ts_code"] else None
                return InstrumentRecord(
                    ts_code=item["ts_code"],
                    symbol=item["symbol"],
                    name=item["name"],
                    kind=item.get("kind", "ETF"),
                    exchange=exchange,
                    theme_l1=item.get("theme_l1"),
                    theme_l2=item.get("theme_l2"),
                    benchmark=item.get("benchmark"),
                    enabled=bool(item.get("enabled", True)),
                    metadata={"mock": True},
                )
        return None

    @staticmethod
    def _seed(ts_code: str) -> int:
        return sum(ord(ch) * (i + 1) for i, ch in enumerate(ts_code))

    def fetch_daily_bars(self, ts_code: str, start_date: date, end_date: date) -> list[BarRecord]:
        seed = self._seed(ts_code)
        rng = random.Random(seed)
        all_days: list[date] = []
        cursor = start_date
        while cursor <= end_date:
            if cursor.weekday() < 5:
                all_days.append(cursor)
            cursor += timedelta(days=1)
        if not all_days:
            return []

        base = 0.8 + (seed % 600) / 100.0
        drift = ((seed % 17) - 8) / 100000.0
        vol = 0.008 + (seed % 9) / 1000.0
        close = base
        records: list[BarRecord] = []
        for idx, day in enumerate(all_days):
            cycle = 0.0015 * math.sin(idx / (13 + seed % 7)) + 0.001 * math.cos(idx / 31)
            shock = rng.gauss(drift + cycle, vol)
            pre_close = close
            close = max(0.2, pre_close * (1 + shock))
            open_price = max(0.2, pre_close * (1 + rng.gauss(0, vol / 3)))
            high = max(open_price, close) * (1 + abs(rng.gauss(0, vol / 2)))
            low = min(open_price, close) * (1 - abs(rng.gauss(0, vol / 2)))
            volume = 2_000_000 + abs(rng.gauss(0, 900_000)) + (idx % 21) * 25_000
            amount = volume * close
            records.append(
                BarRecord(
                    ts_code=ts_code,
                    trade_date=day,
                    open=round(open_price, 4),
                    high=round(high, 4),
                    low=round(max(0.01, low), 4),
                    close=round(close, 4),
                    pre_close=round(pre_close, 4),
                    volume=round(volume, 2),
                    amount=round(amount, 2),
                    pct_change=round((close / pre_close - 1) * 100, 4),
                    adjust="none",
                    source=self.name,
                )
            )
        return records

    def fetch_spot_quotes(self, codes: list[str]) -> list[QuoteRecord]:
        now = datetime.now(self.tz)
        result: list[QuoteRecord] = []
        for code in codes:
            bars = self.fetch_daily_bars(code, now.date() - timedelta(days=45), now.date())
            latest = bars[-1]
            seed = self._seed(code) + int(now.timestamp() // 180)
            rng = random.Random(seed)
            intraday = rng.gauss(0, 0.0025)
            price = max(0.01, latest.close * (1 + intraday))
            pct = ((price / (latest.pre_close or latest.close)) - 1) * 100
            result.append(
                QuoteRecord(
                    ts_code=code,
                    quote_time=now,
                    price=round(price, 4),
                    open=latest.open,
                    high=max(latest.high, price),
                    low=min(latest.low, price),
                    pre_close=latest.pre_close,
                    pct_change=round(pct, 4),
                    volume=(latest.volume or 0) * (0.4 + min(1.0, max(0.0, (now.hour - 9) / 6))),
                    amount=(latest.amount or 0) * (0.4 + min(1.0, max(0.0, (now.hour - 9) / 6))),
                    premium_rate=round(rng.gauss(0.05, 0.12), 4),
                    source=self.name,
                    is_realtime=True,
                    degraded_reason="演示数据，不可用于真实投资判断",
                )
            )
        return result

    def fetch_news(self, since_hours: int = 24) -> list[NewsRecord]:
        now = datetime.now(self.tz)
        samples = [
            ("政策端强调推动科技创新与先进制造，市场关注半导体和机器人产业链", "科技", 0.7),
            ("贵金属价格波动加大，黄金主题资金出现分歧", "黄金", -0.1),
            ("医药行业多项研发进展披露，创新药主题热度回升", "医药", 0.5),
        ]
        return [
            NewsRecord(
                source="mock-news",
                source_id=f"mock-{now:%Y%m%d}-{idx}",
                title=title,
                summary=f"演示新闻：{title}",
                url=None,
                published_at=now - timedelta(minutes=idx * 37),
            )
            for idx, (title, _theme, _score) in enumerate(samples)
        ]

    def fetch_market_context(self, requests: list[MarketContextItem]) -> list[MarketContextObservation]:
        """Return deterministic, explicitly degraded observations for local demonstrations."""
        fetched_at = datetime.now(self.tz)
        source_timestamp = fetched_at.replace(second=0, microsecond=0)
        observations: list[MarketContextObservation] = []
        for request in requests:
            seed = self._seed(f"context:{request.context_id}:{request.source_symbol or ''}")
            observed_value = round(90.0 + (seed % 10_000) / 100.0, 4)
            today_pct_change = round(((seed % 401) - 200) / 100.0, 4)
            price = round(0.5 + (seed % 50_000) / 100.0, 4)
            observations.append(
                MarketContextObservation(
                    context_id=request.context_id,
                    source_symbol=request.source_symbol,
                    observed_value=observed_value,
                    today_pct_change=today_pct_change,
                    price=price,
                    source=self.name,
                    source_timestamp=source_timestamp,
                    fetched_at=fetched_at,
                    freshness=FreshnessStatus.DEGRADED,
                    verification_status=VerificationStatus.UNVERIFIED,
                    is_mock=True,
                    degraded_reason="synthetic mock observation; not real market data",
                )
            )
        return observations

    def is_trade_day(self, day: date) -> bool:
        return day.weekday() < 5

    def fetch_sector_snapshots(self, trade_date: date | None = None) -> list[SectorRecord]:
        """确定性 mock 板块涨跌家数（演示用；明确标记为合成数据）。"""
        target = trade_date or date.today()
        samples = [
            ("AI应用", 390, 142, 8),
            ("商业航天", 363, 131, 6),
            ("半导体", 168, 41, 3),
            ("有色金属", 20, 180, 5),
            ("黄金", 8, 47, 2),
            ("医药", 45, 210, 10),
            ("新能源", 120, 88, 4),
            ("军工", 70, 130, 5),
        ]
        return [
            SectorRecord(
                sector_name=name,
                trade_date=target,
                up_count=up,
                down_count=down,
                flat_count=flat,
                total_count=up + down + flat,
                pct_change=round(((up - down) / max(up + down, 1)) * 100, 2),
                source="mock-sector",
            )
            for name, up, down, flat in samples
        ]

    def fetch_concept_snapshots(self, trade_date: date | None = None) -> list[SectorRecord]:
        """确定性 mock 概念板块涨跌家数（演示用；明确标记为合成数据）。"""
        target = trade_date or date.today()
        samples = [
            ("芯片", 320, 80, 5),
            ("人工智能", 290, 60, 4),
            ("新能源汽车", 150, 90, 3),
            ("机器人", 210, 70, 4),
            ("华为概念", 130, 110, 6),
            ("医药", 95, 160, 7),
            ("黄金概念", 40, 90, 3),
            ("军工", 70, 130, 5),
        ]
        return [
            SectorRecord(
                sector_name=name,
                trade_date=target,
                up_count=up,
                down_count=down,
                flat_count=flat,
                total_count=up + down + flat,
                pct_change=round(((up - down) / max(up + down, 1)) * 100, 2),
                source="mock-sector",
                board_type="concept",
            )
            for name, up, down, flat in samples
        ]

    def fetch_market_breadth(self, trade_date: date | None = None) -> SectorRecord | None:
        """确定性 mock 全市场涨跌家数（演示用；明确标记为合成数据）。"""
        target = trade_date or date.today()
        up, down, flat = 3387, 2039, 126
        total = up + down + flat
        return SectorRecord(
            sector_name="全市场",
            trade_date=target,
            up_count=up,
            down_count=down,
            flat_count=flat,
            total_count=total,
            pct_change=round((up - down) / max(total, 1) * 100, 2),
            source="mock-sector",
            board_type="market",
        )

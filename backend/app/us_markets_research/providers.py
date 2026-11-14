"""Daily-bar providers for the US research block.

Every provider returns frames with the same internal columns:
``open, high, low, close, volume, close_source`` indexed by naive US session
date. OHLC are split/dividend adjusted (``close`` is the adjusted close).
Failures are recorded in the audit list (provider, operation, ticker,
duration, rows, reason) and never replaced by invented data.

``yfinance`` is a free, unofficial source: it is imported lazily and every row
and series built from it is labelled as such. Official US indices in
production stay on the existing Sina channel (``config/market_context.json``).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd

CLOSE_SOURCE_OFFICIAL = "provider_adjusted_close"
CLOSE_SOURCE_PROVISIONAL = "provider_last_price_provisional"
FRAME_COLUMNS = ["open", "high", "low", "close", "volume", "close_source"]


@dataclass
class ProviderResult:
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    audit: list[dict[str, Any]] = field(default_factory=list)
    provisional: list[dict[str, Any]] = field(default_factory=list)
    source_label: str = ""
    source_version: str | None = None


class DailyProvider(Protocol):
    name: str

    def fetch(self, tickers: list[str], start: date, end: date) -> ProviderResult: ...


def _audit(provider: str, operation: str, ticker: str | None, started: float,
           rows: int, ok: bool, reason: str | None = None) -> dict[str, Any]:
    return {"provider": provider, "operation": operation, "ticker": ticker,
            "duration_ms": int((time.monotonic() - started) * 1000), "rows": rows, "ok": ok, "reason": reason}


def _normalize_index(index: pd.Index) -> pd.DatetimeIndex:
    idx = pd.to_datetime(index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("America/New_York").tz_localize(None)
    return idx.normalize()


def adjust_frame(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Raw OHLC + Close/Adj Close (+Volume) -> internal adjusted frame.

    Rows with missing Close OR Adj Close, invalid OHLC or adjustment factors are dropped. Returns
    ``(frame, dropped_rows)`` where dropped rows are described for the audit.
    """
    if raw is None or raw.empty:
        return pd.DataFrame(columns=FRAME_COLUMNS), []
    df = raw.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    df.index = _normalize_index(df.index)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if "adj_close" not in df.columns:
        df["adj_close"] = np.nan  # never silently treat an unadjusted price as adjusted
    if "close_source" not in df.columns:
        df["close_source"] = CLOSE_SOURCE_OFFICIAL
    for column in ("open", "high", "low", "close", "adj_close", "volume"):
        if column not in df.columns:
            df[column] = np.nan
        df[column] = pd.to_numeric(df[column], errors="coerce")
    with np.errstate(divide="ignore", invalid="ignore"):
        factor = (df["adj_close"] / df["close"]).replace([np.inf, -np.inf], np.nan)
    # No forward/backfill of adjustment factors (corporate actions must not leak).
    factor = factor.where(factor > 0)
    out = pd.DataFrame({
        "open": df["open"] * factor, "high": df["high"] * factor, "low": df["low"] * factor,
        "close": df["adj_close"], "volume": df["volume"], "close_source": df["close_source"],
    }, index=df.index)
    prices = out[["open", "high", "low", "close"]]
    missing = (~np.isfinite(prices).all(axis=1) | (prices <= 0).any(axis=1)
               | ~np.isfinite(df["close"]) | (df["close"] <= 0)
               | (out["high"] < prices.max(axis=1)) | (out["low"] > prices.min(axis=1)))
    dropped = [{"date": str(idx.date()), "reason": "missing_or_nonpositive_close"} for idx in out.index[missing]]
    out = out[~missing]
    out.index.name = "date"
    return out[FRAME_COLUMNS], dropped


def fill_provisional_close(raw: pd.DataFrame, last_price: float | None) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Fill a session row that has OHLC but no official close from ``last_price``.

    Legacy diagnostic helper ONLY, never used by YFinanceProvider/build metrics.
    Only when ``low <= last_price <= high``; the row is flagged with
    ``close_source=provider_last_price_provisional`` so it is never mistaken for
    an official close.
    """
    if raw is None or raw.empty or last_price is None or not np.isfinite(last_price):
        return raw, []
    df = raw.copy()
    df.index = _normalize_index(df.index)
    if "close_source" not in df.columns:
        df["close_source"] = CLOSE_SOURCE_OFFICIAL
    adj = df["Adj Close"] if "Adj Close" in df.columns else df["Close"]
    missing = df["Close"].isna() | adj.isna()
    fills: list[dict[str, Any]] = []
    for idx in df.index[missing]:
        low, high = df.at[idx, "Low"], df.at[idx, "High"]
        if pd.notna(low) and pd.notna(high) and float(low) <= float(last_price) <= float(high):
            if pd.isna(df.at[idx, "Close"]):
                df.at[idx, "Close"] = float(last_price)
            if "Adj Close" in df.columns and pd.isna(df.at[idx, "Adj Close"]):
                df.at[idx, "Adj Close"] = float(last_price)
            df.at[idx, "close_source"] = CLOSE_SOURCE_PROVISIONAL
            fills.append({"date": str(pd.Timestamp(idx).date()), "last_price": float(last_price),
                          "low": float(low), "high": float(high)})
    return df, fills


class YFinanceProvider:
    """Lazy yfinance adapter. Not an official exchange feed."""

    name = "yfinance"

    def fetch(self, tickers: list[str], start: date, end: date) -> ProviderResult:
        result = ProviderResult(source_label="yfinance (Yahoo Finance, 非官方免费源)")
        try:
            import yfinance as yf  # type: ignore
        except Exception as exc:  # pragma: no cover - environment dependent
            for ticker in tickers:
                result.audit.append({"provider": self.name, "operation": "import", "ticker": ticker,
                                     "duration_ms": 0, "rows": 0, "ok": False,
                                     "reason": f"yfinance_import_failed:{type(exc).__name__}"})
            return result
        result.source_version = getattr(yf, "__version__", None)
        for ticker in tickers:
            started = time.monotonic()
            try:
                raw = yf.download(ticker, start=start.isoformat(), end=end.isoformat(), auto_adjust=False,
                                  actions=False, progress=False, threads=False, group_by="column")
                raw = self._flatten(raw, ticker)
                if raw.empty:
                    result.audit.append(_audit(self.name, "download", ticker, started, 0, False, "no_rows_returned"))
                    continue
                # No last_price fallback: a live quote cannot establish a session Close,
                # much less an adjusted close. Retain only actual provider daily bars.
                fills = []
                frame, dropped = adjust_frame(raw)
                for fill in fills:
                    result.provisional.append({"ticker": ticker, **fill})
                if frame.empty:
                    result.audit.append(_audit(self.name, "download", ticker, started, 0, False, "no_valid_close"))
                    continue
                result.frames[ticker] = frame
                reason = f"dropped_rows={len(dropped)}" if dropped else None
                result.audit.append(_audit(self.name, "download", ticker, started, len(frame), True, reason))
            except Exception as exc:  # network/parse errors: record, never fabricate
                result.audit.append(_audit(self.name, "download", ticker, started, 0, False,
                                           f"{type(exc).__name__}:{str(exc)[:160]}"))
        return result

    @staticmethod
    def _flatten(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
        if raw is None or raw.empty:
            return pd.DataFrame()
        out = raw.copy()
        if isinstance(out.columns, pd.MultiIndex):
            if ticker in out.columns.get_level_values(-1):
                out = out.xs(ticker, axis=1, level=-1)
            else:
                out.columns = [c[0] for c in out.columns]
        out = out.rename(columns=lambda c: str(c).strip())
        for column in ("Open", "High", "Low", "Close"):
            if column not in out.columns:
                return pd.DataFrame()
        return out


class CsvProvider:
    """Reads a tidy long CSV (``date,ticker,Open,High,Low,Close,Adj Close,Volume[,close_source]``).

    Used for offline tests and for reproducing a published snapshot; the source
    label says so, so it can never be shown as a live feed.
    """

    name = "csv"

    def __init__(self, path: str | Path, label: str | None = None) -> None:
        self.path = Path(path)
        self.label = label or f"csv:{self.path.name}"

    def fetch(self, tickers: list[str], start: date, end: date) -> ProviderResult:
        result = ProviderResult(source_label=self.label)
        started = time.monotonic()
        try:
            table = pd.read_csv(self.path, encoding="utf-8")
        except Exception as exc:
            result.audit.append(_audit(self.name, "read_csv", None, started, 0, False, f"{type(exc).__name__}"))
            return result
        date_col = "date" if "date" in table.columns else "Date"
        table[date_col] = pd.to_datetime(table[date_col])
        for ticker in tickers:
            started = time.monotonic()
            sub = table[table["ticker"] == ticker].set_index(date_col).sort_index()
            sub = sub[(sub.index >= pd.Timestamp(start)) & (sub.index < pd.Timestamp(end))]
            if sub.empty:
                result.audit.append(_audit(self.name, "read_csv", ticker, started, 0, False, "ticker_not_in_csv"))
                continue
            frame, dropped = adjust_frame(sub.drop(columns=["ticker"]))
            if frame.empty:
                result.audit.append(_audit(self.name, "read_csv", ticker, started, 0, False, "no_valid_close"))
                continue
            flagged = frame["close_source"].astype(str).str.contains("provisional")
            frame.loc[flagged, "close_source"] = CLOSE_SOURCE_PROVISIONAL
            for idx in frame.index[flagged]:
                result.provisional.append({"ticker": ticker, "date": str(idx.date())})
            result.frames[ticker] = frame
            result.audit.append(_audit(self.name, "read_csv", ticker, started, len(frame), True))
        return result

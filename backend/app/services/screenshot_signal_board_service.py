from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import ForecastSnapshot, IndicatorSnapshot, Instrument, QuoteSnapshot, SignalSnapshot
from app.services.industry_board_service import IndustryBoardService


def _json_value(value: Any, fallback: Any) -> Any:
    return value if isinstance(value, type(fallback)) else fallback


def _float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


class ScreenshotSignalBoardService:
    """Build the colorful five-level board from persisted deterministic evidence."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.industry = IndustryBoardService(self.settings)

    def build(self, db: Session) -> dict[str, Any]:
        instruments = db.scalars(
            select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)
        ).all()
        available_codes = {item.ts_code.upper() for item in instruments}
        registry = self.industry.snapshot(available_codes)
        industry_by_code = {
            str(item.get("proxy_ts_code") or "").upper(): item
            for item in registry["industries"]
            if item.get("proxy_ts_code")
        }
        anchor_by_code = {
            str(item.get("proxy_ts_code") or "").upper(): item
            for item in registry["market_anchors"]
        }
        extended_by_code = {
            str(item.get("proxy_ts_code") or "").upper(): item
            for item in registry.get("extended_themes", [])
        }
        rows: list[dict[str, Any]] = []
        for instrument in instruments:
            quote = db.scalar(
                select(QuoteSnapshot)
                .where(QuoteSnapshot.instrument_id == instrument.id)
                .order_by(QuoteSnapshot.quote_time.desc())
                .limit(1)
            )
            indicator = db.scalar(
                select(IndicatorSnapshot)
                .where(IndicatorSnapshot.instrument_id == instrument.id)
                .order_by(IndicatorSnapshot.as_of_date.desc(), IndicatorSnapshot.generated_at.desc())
                .limit(1)
            )
            forecasts_all = db.scalars(
                select(ForecastSnapshot)
                .where(ForecastSnapshot.instrument_id == instrument.id)
                .order_by(ForecastSnapshot.as_of_date.desc(), ForecastSnapshot.generated_at.desc())
            ).all()
            latest_forecasts: dict[int, ForecastSnapshot] = {}
            for forecast in forecasts_all:
                latest_forecasts.setdefault(int(forecast.horizon), forecast)
                if len(latest_forecasts) >= 3:
                    break
            signals = db.scalars(
                select(SignalSnapshot)
                .where(SignalSnapshot.instrument_id == instrument.id)
                .order_by(SignalSnapshot.generated_at.desc())
                .limit(2)
            ).all()
            signal = signals[0] if signals else None
            previous = signals[1] if len(signals) > 1 else None
            values = _json_value(getattr(indicator, "values", None), {}) if indicator else {}
            code = instrument.ts_code.upper()
            if code in anchor_by_code:
                board_profile: dict[str, Any] = {"role": "anchor", **anchor_by_code[code]}
            elif code in industry_by_code:
                board_profile = {"role": "industry", **industry_by_code[code]}
            elif code in extended_by_code:
                board_profile = {"role": "extended_theme", **extended_by_code[code]}
            else:
                board_profile = {
                    "role": "extended_theme",
                    "name": getattr(instrument, "theme_l1", None) or instrument.name,
                    "macro_group": getattr(instrument, "theme_l2", None) or "扩展主题",
                }
            score = _float(getattr(signal, "score", None)) if signal else None
            previous_score = _float(getattr(previous, "score", None)) if previous else None
            comparison = {
                "previous_state": getattr(previous, "state", None) if previous else None,
                "previous_score": previous_score,
                "score_delta": round(score - previous_score, 2)
                if score is not None and previous_score is not None
                else None,
                "direction": "up"
                if score is not None and previous_score is not None and score > previous_score + 0.25
                else (
                    "down"
                    if score is not None and previous_score is not None and score < previous_score - 0.25
                    else "flat"
                ),
                "state_changed": bool(
                    previous and signal and getattr(previous, "state", None) != getattr(signal, "state", None)
                ),
            }
            forecast_rows: list[dict[str, Any]] = []
            for horizon in (1, 5, 20):
                item = latest_forecasts.get(horizon)
                if not item:
                    continue
                forecast_rows.append(
                    {
                        "horizon": horizon,
                        "p_up": _float(getattr(item, "p_up", None)),
                        "expected_return": _float(getattr(item, "expected_return", None)),
                        "q10": _float(getattr(item, "q10", None)),
                        "q50": _float(getattr(item, "q50", None)),
                        "q90": _float(getattr(item, "q90", None)),
                        "confidence": _float(getattr(item, "confidence", None)),
                        "sample_count": getattr(item, "sample_count", None),
                        "calibration_status": getattr(item, "calibration_status", None),
                        "model_version": getattr(item, "model_version", None),
                        "terminal_price_q50": _float(getattr(item, "terminal_price_q50", None)),
                        "path_low_price_q50": _float(getattr(item, "path_low_price_q50", None)),
                        "path_high_price_q50": _float(getattr(item, "path_high_price_q50", None)),
                    }
                )
            rows.append(
                {
                    "instrument_id": instrument.id,
                    "ts_code": instrument.ts_code,
                    "name": instrument.name,
                    "kind": getattr(instrument, "kind", None),
                    "theme_l1": getattr(instrument, "theme_l1", None),
                    "theme_l2": getattr(instrument, "theme_l2", None),
                    "board_profile": board_profile,
                    "quote": None
                    if quote is None
                    else {
                        "quote_time": quote.quote_time.isoformat() if quote.quote_time else None,
                        "source_timestamp": getattr(quote, "source_timestamp", None).isoformat()
                        if getattr(quote, "source_timestamp", None)
                        else None,
                        "fetched_at": getattr(quote, "fetched_at", None).isoformat()
                        if getattr(quote, "fetched_at", None)
                        else None,
                        "price": _float(getattr(quote, "price", None)),
                        "pct_change": _float(getattr(quote, "pct_change", None)),
                        "volume": _float(getattr(quote, "volume", None)),
                        "amount": _float(getattr(quote, "amount", None)),
                        "premium_rate": _float(getattr(quote, "premium_rate", None)),
                        "source": getattr(quote, "source", None),
                        "is_realtime": bool(getattr(quote, "is_realtime", False)),
                        "timestamp_verified": bool(getattr(quote, "timestamp_verified", False)),
                        "degraded_reason": getattr(quote, "degraded_reason", None),
                    },
                    "indicator": None
                    if indicator is None
                    else {
                        "as_of_date": indicator.as_of_date.isoformat() if indicator.as_of_date else None,
                        "generated_at": indicator.generated_at.isoformat() if indicator.generated_at else None,
                        "technical_score": _float(getattr(indicator, "technical_score", None)),
                        "risk_score": _float(getattr(indicator, "risk_score", None)),
                        "trend_label": getattr(indicator, "trend_label", None),
                        "data_quality": _float(getattr(indicator, "data_quality", None)),
                        "values": values,
                    },
                    "forecasts": forecast_rows,
                    "signal": None
                    if signal is None
                    else {
                        "state": getattr(signal, "state", None),
                        "score": score,
                        "actionable": bool(getattr(signal, "actionable", False)),
                        "reasons": _json_value(getattr(signal, "reasons", None), []),
                        "risk_flags": _json_value(getattr(signal, "risk_flags", None), []),
                        "generated_at": signal.generated_at.isoformat() if signal.generated_at else None,
                        "strategy_version": getattr(signal, "strategy_version", None),
                    },
                    "comparison": comparison,
                }
            )

        # Show the complete configured universe before it is added to the active
        # watchlist. Placeholders are deliberately non-actionable and contain no
        # fabricated quote, indicator, forecast, or signal evidence.
        known_codes = {row["ts_code"].upper() for row in rows}
        configured_profiles: list[dict[str, Any]] = []
        configured_profiles.extend(
            {"role": "industry", **item}
            for item in registry["industries"]
            if item.get("proxy_ts_code")
        )
        configured_profiles.extend(
            {"role": "anchor", **item}
            for item in registry["market_anchors"]
            if item.get("proxy_ts_code")
        )
        configured_profiles.extend(
            {"role": "extended_theme", **item}
            for item in registry.get("extended_themes", [])
            if item.get("proxy_ts_code")
        )
        for profile in configured_profiles:
            code = str(profile.get("proxy_ts_code") or "").upper()
            if not code or code in known_codes:
                continue
            rows.append(
                {
                    "instrument_id": None,
                    "ts_code": code,
                    "name": profile.get("proxy_name") or profile.get("name") or code,
                    "kind": "ETF",
                    "theme_l1": profile.get("name"),
                    "theme_l2": profile.get("macro_group") or "市场锚",
                    "board_profile": profile,
                    "quote": None,
                    "indicator": None,
                    "forecasts": [],
                    "signal": {
                        "state": "待初始化",
                        "score": None,
                        "actionable": False,
                        "reasons": ["尚未加入活动自选池或尚未完成数据初始化"],
                        "risk_flags": ["pending_real_provider_qualification"],
                        "generated_at": None,
                        "strategy_version": None,
                    },
                    "comparison": {
                        "previous_state": None,
                        "previous_score": None,
                        "score_delta": None,
                        "direction": "flat",
                        "state_changed": False,
                    },
                }
            )
            known_codes.add(code)

        breadth = self._breadth(rows)
        for row in rows:
            macro = str(
                row["board_profile"].get("macro_group")
                or row.get("theme_l2")
                or "扩展主题"
            )
            row["proxy_breadth"] = breadth.get(
                macro,
                {"label": macro, "up": 0, "down": 0, "flat": 0, "scope": "ETF代理池"},
            )
        groups: defaultdict[str, int] = defaultdict(int)
        for row in rows:
            groups[self._group(row)] += 1
        return {
            "version": registry["version"],
            "generated_at": datetime.now().astimezone().isoformat(),
            "classification": registry["classification"],
            "coverage": registry["coverage"],
            "industries": registry["industries"],
            "market_anchors": registry["market_anchors"],
            "extended_themes": registry.get("extended_themes", []),
            "signal_groups": registry["display"]["signal_groups"],
            "rows": rows,
            "group_counts": dict(groups),
            "breadth": breadth,
            "breadth_scope": "ETF代理池，不等同于行业成份股涨跌家数",
        }

    @staticmethod
    def _group(row: dict[str, Any]) -> str:
        state = str((row.get("signal") or {}).get("state") or "").lower()
        score = _float((row.get("signal") or {}).get("score"))
        values = (row.get("indicator") or {}).get("values") or {}
        j_value = _float(values.get("kdj_j"))
        if "异常" in state or "减" in state or "退出" in state or (score is not None and score < 38):
            return "reduce"
        if "加仓" in state or "增加" in state or (
            score is not None and score >= 72 and (j_value is None or j_value < 90)
        ):
            return "add"
        if "入场" in state or (score is not None and score >= 66):
            return "entry"
        if "试探" in state or (score is not None and score >= 56):
            return "probe"
        return "watch"

    @staticmethod
    def _breadth(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            macro = str(
                row["board_profile"].get("macro_group")
                or row.get("theme_l2")
                or "扩展主题"
            )
            bucket = buckets.setdefault(
                macro,
                {"label": macro, "up": 0, "down": 0, "flat": 0, "scope": "ETF代理池"},
            )
            pct = _float((row.get("quote") or {}).get("pct_change"))
            if pct is None or abs(pct) < 1e-12:
                bucket["flat"] += 1
            elif pct > 0:
                bucket["up"] += 1
            else:
                bucket["down"] += 1
        return buckets

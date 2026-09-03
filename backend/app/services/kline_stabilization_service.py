from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.models import DailyBar, ForecastSnapshot, Instrument, QuoteSnapshot, SectorSnapshot
from app.services.current_decision_service import CurrentDecisionService

try:  # optional dependency — server remains usable without chanlun
    from chanlun import Kline as ChanKline
    from chanlun import build_process_center, objects_to_query
except Exception:  # pragma: no cover - environment-specific optional import
    ChanKline = None
    build_process_center = None
    objects_to_query = None


def _finite(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None


def _pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value / 100.0, 8)


def _forecast_note(diagnostics: Any) -> str:
    """Read an optional note without assuming legacy JSON is a mapping.

    Older ForecastSnapshot rows may store diagnostics as lists. Compatibility
    readers must never fail merely because an audit payload changed shape.
    """

    if isinstance(diagnostics, dict):
        note = diagnostics.get("note")
        if isinstance(note, str) and note.strip():
            return note.strip()
    return "persisted ForecastSnapshot"


def td_setup_snapshot(frame: pd.DataFrame) -> dict[str, Any]:
    """Deterministic TD Sequential setup count (research view only)."""
    if frame.empty or len(frame) < 5:
        return {
            "label": "—",
            "direction": "none",
            "sub_label": "",
            "desc": "数据不足",
            "countdown": 0,
            "setup_length": 9,
        }
    close = frame["close"].astype(float).reset_index(drop=True)
    buy = 0
    sell = 0
    for idx in range(4, len(close)):
        if close.iloc[idx] < close.iloc[idx - 4]:
            buy += 1
            sell = 0
        elif close.iloc[idx] > close.iloc[idx - 4]:
            sell += 1
            buy = 0
        else:
            buy = 0
            sell = 0
    count = min(9, max(buy, sell))
    if buy > 0:
        direction = "buy"
        label = f"买入{count}"
        sub_label = "买入九转" if count >= 9 else "买入计数"
        desc = "连续收盘低于4日前，接近9时关注下跌衰竭"
    elif sell > 0:
        direction = "sell"
        label = f"卖出{count}"
        sub_label = "卖出九转" if count >= 9 else "卖出计数"
        desc = "连续收盘高于4日前，接近9时关注上涨衰竭"
    else:
        direction = "none"
        label = "—"
        sub_label = ""
        desc = "当前无连续九转 setup"
    return {
        "label": label,
        "direction": direction,
        "sub_label": sub_label,
        "desc": desc,
        "countdown": count,
        "setup_length": 9,
    }


class KlineStabilizationService:
    """只读 K 线企稳分析数据，兼容 API 不再拥有独立 current action。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()
        self.config = self._load_config()

    @staticmethod
    def _load_config() -> dict[str, Any]:
        path = PROJECT_ROOT / "config" / "etf_1430_workbench.json"
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _pool(self) -> tuple[str, ...]:
        raw = self.config.get("instrument_pool") or []
        return tuple(str(item).upper() for item in raw if isinstance(item, str))

    def _instruments(self, db: Session) -> list[Instrument]:
        pool = self._pool()
        statement = select(Instrument).where(Instrument.enabled.is_(True))
        if pool:
            statement = statement.where(Instrument.ts_code.in_(pool))
        rows = db.scalars(statement.order_by(Instrument.ts_code)).all()
        if not rows and pool:
            rows = db.scalars(
                select(Instrument)
                .where(Instrument.enabled.is_(True))
                .order_by(Instrument.ts_code)
            ).all()
        return list(rows)

    @staticmethod
    def _bars_frame(db: Session, instrument_id: int, limit: int = 320) -> pd.DataFrame:
        rows = db.scalars(
            select(DailyBar)
            .where(DailyBar.instrument_id == instrument_id)
            .order_by(DailyBar.trade_date.desc())
            .limit(limit)
        ).all()
        rows = list(reversed(rows))
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {
                    "trade_date": row.trade_date,
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume or 0,
                    "amount": row.amount or 0,
                }
                for row in rows
            ]
        )

    @staticmethod
    def _latest_quote(db: Session, instrument_id: int) -> QuoteSnapshot | None:
        return db.scalar(
            select(QuoteSnapshot)
            .where(QuoteSnapshot.instrument_id == instrument_id)
            .order_by(QuoteSnapshot.quote_time.desc())
            .limit(1)
        )

    @staticmethod
    def _latest_forecast(db: Session, instrument_id: int, horizon: int = 1) -> ForecastSnapshot | None:
        return db.scalar(
            select(ForecastSnapshot)
            .where(ForecastSnapshot.instrument_id == instrument_id, ForecastSnapshot.horizon == horizon)
            .order_by(ForecastSnapshot.as_of_date.desc(), ForecastSnapshot.generated_at.desc())
            .limit(1)
        )

    def _sector_alias(self) -> dict[str, str]:
        raw = self.config.get("sector_alias") or {}
        return {
            str(key): str(value)
            for key, value in raw.items()
            if isinstance(key, str) and isinstance(value, str) and not key.startswith("_")
        }

    def _concept_alias(self) -> dict[str, str]:
        raw = self.config.get("concept_alias") or {}
        return {
            str(key): str(value)
            for key, value in raw.items()
            if isinstance(key, str) and isinstance(value, str) and not key.startswith("_")
        }

    def _broad_market_themes(self) -> list[str]:
        raw = self.config.get("broad_market_themes") or []
        return [str(value) for value in raw if isinstance(value, str)]

    @staticmethod
    def _sector_state(
        db: Session,
        instrument: Instrument,
        alias: dict[str, str],
        *,
        board_type: str,
    ) -> dict[str, Any]:
        candidates = [
            value
            for value in (
                instrument.theme_l2,
                instrument.theme_l1,
                alias.get(instrument.theme_l2 or ""),
                alias.get(instrument.theme_l1 or ""),
            )
            if value
        ]
        for candidate in candidates:
            row = db.scalar(
                select(SectorSnapshot)
                .where(
                    SectorSnapshot.board_type == board_type,
                    SectorSnapshot.sector_name == candidate,
                )
                .order_by(SectorSnapshot.trade_date.desc(), SectorSnapshot.id.desc())
                .limit(1)
            )
            if row is not None:
                return {
                    "sector_name": row.sector_name,
                    "trade_date": row.trade_date.isoformat(),
                    "up": row.up_count,
                    "down": row.down_count,
                    "flat": row.flat_count,
                    "change_pct": row.change_pct,
                    "source": row.source,
                    "board_type": board_type,
                }
        return {
            "sector_name": None,
            "trade_date": None,
            "up": None,
            "down": None,
            "flat": None,
            "change_pct": None,
            "source": None,
            "board_type": board_type,
        }

    @staticmethod
    def _market_breadth(db: Session) -> dict[str, Any] | None:
        row = db.scalar(
            select(SectorSnapshot)
            .where(SectorSnapshot.board_type == "market")
            .order_by(SectorSnapshot.trade_date.desc(), SectorSnapshot.id.desc())
            .limit(1)
        )
        if row is None:
            return None
        return {
            "sector_name": row.sector_name,
            "trade_date": row.trade_date.isoformat(),
            "up": row.up_count,
            "down": row.down_count,
            "flat": row.flat_count,
            "change_pct": row.change_pct,
            "source": row.source,
            "board_type": "market",
        }

    def _chanlun_state(self, frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty or ChanKline is None or build_process_center is None or objects_to_query is None:
            return {
                "status": "unavailable",
                "label": "缠论近似不可用",
                "detail": "chanlun optional dependency unavailable or no bars",
            }
        try:
            records = []
            for _, row in frame.tail(220).iterrows():
                records.append(
                    {
                        "date": pd.Timestamp(row["trade_date"]).to_pydatetime(),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row["volume"]),
                    }
                )
            klines = [ChanKline(**item) for item in records]
            center = build_process_center(klines)
            objects = objects_to_query(center)
            if not objects:
                return {"status": "empty", "label": "缠论近似无结构", "detail": "no processed objects"}
            latest = objects[-1]
            return {
                "status": "ok",
                "label": str(getattr(latest, "type", None) or getattr(latest, "kind", None) or "结构已识别"),
                "detail": str(latest),
            }
        except Exception as exc:  # optional research display must not block the board
            return {
                "status": "degraded",
                "label": "缠论近似失败",
                "detail": type(exc).__name__,
            }

    @staticmethod
    def _volume_state(frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty or len(frame) < 6:
            return {"ratio": None, "label": "量能不足", "kind": "unknown"}
        current = float(frame["volume"].iloc[-1])
        previous = frame["volume"].iloc[-6:-1].astype(float)
        average = float(previous.mean()) if len(previous) else 0.0
        ratio = current / average if average > 0 else None
        if ratio is None:
            return {"ratio": None, "label": "量能不足", "kind": "unknown"}
        if ratio >= 1.35:
            kind, label = "expand", "放量"
        elif ratio <= 0.85:
            kind, label = "contract", "缩量"
        else:
            kind, label = "flat", "平量"
        return {"ratio": round(ratio, 3), "label": label, "kind": kind}

    @staticmethod
    def _ma_state(frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty:
            return {"label": "均线不足", "kind": "unknown", "values": {}}
        close = frame["close"].astype(float)
        values: dict[str, float] = {}
        for window in (5, 10, 20, 30):
            if len(close) >= window:
                values[f"ma{window}"] = float(close.tail(window).mean())
        required = [values.get(f"ma{window}") for window in (5, 10, 20, 30)]
        if any(value is None for value in required):
            return {"label": "均线不足", "kind": "unknown", "values": values}
        m5, m10, m20, m30 = required
        if m5 > m10 > m20 > m30:
            kind, label = "bull", "多头排列"
        elif m5 < m10 < m20 < m30:
            kind, label = "bear", "空头排列"
        else:
            kind, label = "mixed", "多空交织"
        return {"label": label, "kind": kind, "values": values}

    @staticmethod
    def _ema(series: pd.Series, span: int) -> pd.Series:
        return series.ewm(span=span, adjust=False).mean()

    def _macd_state(self, frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty or len(frame) < 35:
            return {"label": "MACD不足", "kind": "unknown", "dif": None, "dea": None, "hist": None}
        close = frame["close"].astype(float)
        dif_series = self._ema(close, 12) - self._ema(close, 26)
        dea_series = self._ema(dif_series, 9)
        hist_series = (dif_series - dea_series) * 2
        dif = float(dif_series.iloc[-1])
        dea = float(dea_series.iloc[-1])
        hist = float(hist_series.iloc[-1])
        previous_hist = float(hist_series.iloc[-2])
        previous_dif = float(dif_series.iloc[-2])
        previous_dea = float(dea_series.iloc[-2])
        if previous_dif >= previous_dea and dif < dea:
            kind, label = "death", "死叉"
        elif previous_dif <= previous_dea and dif > dea:
            kind, label = "gold", "金叉"
        elif hist > 0 and hist < previous_hist:
            kind, label = "approach_death", "将死叉"
        elif hist < 0 and hist > previous_hist:
            kind, label = "approach_gold", "将金叉"
        elif hist > 0:
            kind, label = "bull_cont", "多头延续"
        else:
            kind, label = "bear_cont", "空头延续"
        return {"label": label, "kind": kind, "dif": dif, "dea": dea, "hist": hist}

    @staticmethod
    def _kdj_state(frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty or len(frame) < 12:
            return {"label": "KDJ不足", "kind": "unknown", "j": None, "k": None, "d": None}
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        close = frame["close"].astype(float)
        lowest = low.rolling(9).min()
        highest = high.rolling(9).max()
        span = (highest - lowest).replace(0, np.nan)
        rsv = ((close - lowest) / span * 100).fillna(50.0)
        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        j = 3 * k - 2 * d
        jv = float(j.iloc[-1])
        kv = float(k.iloc[-1])
        dv = float(d.iloc[-1])
        prev_k = float(k.iloc[-2])
        prev_d = float(d.iloc[-2])
        death = prev_k >= prev_d and kv < dv
        if death:
            kind, label = "death", "死叉"
        elif jv >= 100:
            kind, label = "overbought", "超买"
        elif jv >= 90:
            kind, label = "high", "偏高"
        elif jv <= 20:
            kind, label = "low", "低位"
        else:
            kind, label = "healthy", "健康"
        return {"label": label, "kind": kind, "j": jv, "k": kv, "d": dv, "death": death}

    @staticmethod
    def _rsi_state(frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty or len(frame) < 16:
            return {"value": None, "label": "RSI不足"}
        close = frame["close"].astype(float)
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = -delta.clip(upper=0).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        value = float((100 - 100 / (1 + rs)).iloc[-1])
        if not np.isfinite(value):
            value = 100.0 if float(gain.iloc[-1]) > 0 else 50.0
        if value >= 70:
            label = "超买 · 回调风险高"
        elif value >= 60:
            label = "正常偏强 · 趋势中段"
        elif value <= 40:
            label = "偏弱 · 动能不足"
        else:
            label = "正常整理 · 趋势中段"
        return {"value": round(value, 2), "label": label}

    # ---------- 行构建 ----------

    def _row(self, db: Session, instrument: Instrument, *, current_decision: dict[str, Any] | None = None, decision_snapshot_id: str | None = None) -> dict[str, Any]:
        frame = self._bars_frame(db, instrument.id)
        quote = self._latest_quote(db, instrument.id)

        today_pct = _pct(_finite(quote.pct_change)) if quote else None
        current_price = _finite(quote.price) if quote else None
        if current_price is None and not frame.empty:
            current_price = _finite(frame["close"].iloc[-1])
        vs_yesterday = "→"
        if len(frame) >= 2:
            prev_close = _finite(frame["close"].iloc[-2])
            if current_price and prev_close and prev_close > 0:
                change = (current_price - prev_close) / prev_close
                vs_yesterday = "↑" if change > 0.001 else ("↓" if change < -0.001 else "→")

        td = td_setup_snapshot(frame) if not frame.empty else {"label": "—", "direction": "none", "sub_label": "", "desc": "", "countdown": 0, "setup_length": 9}
        stored_forecast = self._latest_forecast(db, instrument.id, 1)
        if stored_forecast is None:
            pattern = {
                "expected_return": None,
                "p_up": None,
                "confidence": 0,
                "sample_count": 0,
                "calibration_status": "not_calibrated",
                "note": "persisted forecast unavailable",
                "source": "unavailable",
                "p_up_semantics": "unavailable",
            }
        else:
            status = str(stored_forecast.calibration_status or "not_calibrated")
            pattern = {
                "expected_return": stored_forecast.expected_return,
                "p_up": stored_forecast.p_up,
                "confidence": stored_forecast.confidence,
                "sample_count": stored_forecast.sample_count,
                "calibration_status": status,
                "note": _forecast_note(stored_forecast.diagnostics_json),
                "source": "persisted_forecast_snapshot",
                "p_up_semantics": (
                    "calibrated_up_probability"
                    if status == "calibrated"
                    else "weighted_historical_neighbor_up_frequency"
                ),
            }
        chan = self._chanlun_state(frame)
        if current_decision is None:
            decision_snapshot_id, decisions = CurrentDecisionService(self.settings).resolve_many(db, [instrument])
            current_decision = decisions.get(str(instrument.ts_code).strip().upper())

        sector = self._sector_state(db, instrument, self._sector_alias(), board_type="industry")
        sector_concept = self._sector_state(db, instrument, self._concept_alias(), board_type="concept")
        market_breadth: dict[str, Any] | None = None
        broad_themes = set(self._broad_market_themes())
        if instrument.theme_l1 in broad_themes or instrument.theme_l2 in broad_themes:
            market_breadth = self._market_breadth(db)

        volume = self._volume_state(frame)
        ma = self._ma_state(frame)
        macd = self._macd_state(frame)
        kdj = self._kdj_state(frame)
        rsi = self._rsi_state(frame)
        action = str((current_decision or {}).get("state") or "数据异常")

        return {
            "ts_code": instrument.ts_code,
            "name": instrument.name,
            "theme_l1": instrument.theme_l1,
            "theme_l2": instrument.theme_l2,
            "price": current_price,
            "today_pct": today_pct,
            "vs_yesterday": vs_yesterday,
            "td": td,
            "forecast": {
                "expected_return": pattern.get("expected_return"),
                "confidence": pattern.get("confidence"),
                "sample_count": pattern.get("sample_count"),
                "calibration_status": pattern.get("calibration_status"),
                "note": pattern.get("note"),
                "source": pattern.get("source"),
                "p_up": pattern.get("p_up"),
                "p_up_semantics": pattern.get("p_up_semantics"),
            },
            "chanlun": chan,
            "action": action,
            "action_source": (current_decision or {}).get("source", "unavailable"),
            "action_canonical": bool((current_decision or {}).get("canonical", False)),
            "decision_snapshot_id": decision_snapshot_id,
            "volume": volume,
            "ma": ma,
            "macd": macd,
            "kdj": kdj,
            "rsi": rsi,
            "sector": sector,
            "sector_concept": sector_concept,
            "market_breadth": market_breadth,
        }

    def summary(self, db: Session) -> dict[str, Any]:
        instruments = self._instruments(db)
        decision_snapshot_id, decisions = CurrentDecisionService(self.settings).resolve_many(db, instruments)
        rows = [
            self._row(
                db,
                instrument,
                current_decision=decisions.get(str(instrument.ts_code).strip().upper()),
                decision_snapshot_id=decision_snapshot_id,
            )
            for instrument in instruments
        ]
        counts = {
            "可加仓": sum(1 for row in rows if row["action"] == "可加仓"),
            "可入场": sum(1 for row in rows if row["action"] == "可入场"),
            "可试探": sum(1 for row in rows if row["action"] == "可试探"),
            "观望": sum(1 for row in rows if row["action"] == "观望"),
            "减仓": sum(1 for row in rows if row["action"] == "减仓"),
            "数据异常": sum(1 for row in rows if row["action"] == "数据异常"),
        }
        return {
            "generated_at": pd.Timestamp.now(tz=self.settings.timezone).isoformat(),
            "research_only": True,
            "automatic_orders": False,
            "current_decision_contract": (
                "decision_board_snapshot_then_signal_grade_then_signal_snapshot_last_resort"
            ),
            "decision_snapshot_id": decision_snapshot_id,
            "counts": counts,
            "rows": rows,
            "disclaimers": [
                "研究视图，仅供分析，不构成投资建议。",
                "action 与主页共用唯一 current decision；TD/MA/MACD/KDJ/RSI/缠论只作解释，不生成第二套动作。",
                "明日预测读取与主页相同的持久化 ForecastSnapshot；未校准 p_up 仅表示历史相似样本上涨占比。",
                "不会自动下单，不会写入持仓。",
            ],
        }

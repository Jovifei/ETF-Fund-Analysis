"""K 线企稳分析看板服务（kline stabilization workbench）。

整合 TD 九转、形态匹配明日预测、缠论指标（chanlun）、技术指标快照，
输出目标看板「K线企稳分析看板」风格的结构化数据。

合规约束：
  - 只读已有持久化数据，不触发行情抓取、不创建订单。
  - 预测一律 calibration_status="not_calibrated"（未完成 walk-forward 校准）。
  - 缠论指标仅作为研究视图，不生成操作级信号。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.models import DailyBar, Instrument, QuoteSnapshot, SectorSnapshot
from app.utils.pattern_forecast import pattern_forecast_snapshot
from app.utils.td_sequential import td_setup_snapshot

logger = logging.getLogger(__name__)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # NaN guard


def _pct(value: float | None) -> float | None:
    """规范化涨跌幅数值。

    重要：QuoteSnapshot.pct_change 的单位约定是「百分比」（与 dashboard_service
    等既有消费方一致，东财「涨跌幅」列也是百分比）。这里只做精度收敛，
    不做 ×100 换算——历史版本曾在此误乘 100，导致看板出现 -136% / +367% 之类的
    不可能数值。单位口径一旦存疑应停止信号，而不是猜测性换算。
    """
    return round(value, 2) if value is not None else None


class KlineStabilizationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        path = PROJECT_ROOT / "config" / "etf_1430_workbench.json"
        self.config: dict[str, Any] = {}
        if path.is_file():
            import json

            self.config = json.loads(path.read_text(encoding="utf-8"))
        self.timezone = ZoneInfo(str(self.config.get("decision_timezone", "Asia/Shanghai")))

    # ---------- 数据获取 ----------

    def _instruments(self, db: Session) -> list[Instrument]:
        return list(db.scalars(select(Instrument).where(Instrument.enabled.is_(True))).all())

    def _bars_frame(self, db: Session, instrument_id: int) -> pd.DataFrame:
        rows = db.scalars(
            select(DailyBar)
            .where(DailyBar.instrument_id == instrument_id)
            .order_by(DailyBar.trade_date.desc())
            .limit(420)  # 足够覆盖 10 日窗口 + 历史匹配
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
                    "volume": row.volume or 0.0,
                    "amount": row.amount or 0.0,
                }
                for row in rows
            ]
        )

    def _latest_quote(self, db: Session, instrument_id: int) -> QuoteSnapshot | None:
        return db.scalar(
            select(QuoteSnapshot)
            .where(QuoteSnapshot.instrument_id == instrument_id)
            .order_by(QuoteSnapshot.quote_time.desc())
            .limit(1)
        )

    def _sector_alias(self) -> dict[str, str]:
        """读取 config 中的主题→行业板块显式映射表（去掉下划线开头的注释键）。"""
        raw = self.config.get("sector_alias") or {}
        if not isinstance(raw, dict):
            return {}
        return {k: str(v) for k, v in raw.items() if not k.startswith("_") and isinstance(v, str)}

    def _concept_alias(self) -> dict[str, str]:
        """读取 config 中的主题→概念板块显式映射表（去掉下划线开头的注释键）。"""
        raw = self.config.get("concept_alias") or {}
        if not isinstance(raw, dict):
            return {}
        return {k: str(v) for k, v in raw.items() if not k.startswith("_") and isinstance(v, str)}

    def _broad_market_themes(self) -> list[str]:
        """读取 config 中需要展示全市场宽度的宽基/指数主题（theme_l1）。"""
        raw = self.config.get("broad_market_themes") or []
        if not isinstance(raw, list):
            return []
        return [str(t) for t in raw if isinstance(t, str)]

    @staticmethod
    def _sector_state(
        db: Session,
        instrument: Instrument,
        alias: dict[str, str] | None = None,
        board_type: str | None = None,
    ) -> dict[str, Any]:
        """读取板块涨跌家数（SectorSnapshot 表）。

        匹配策略（严格，不做模糊猜测）：
        1. theme_l1/theme_l2 原样精确命中板块名；
        2. 经 config 显式映射表（sector_alias / concept_alias）映射后的板块名精确命中。

        匹配不到一律返回 null（前端显示 "—"）——刻意**不**用"最近一条任意板块"兜底，
        因为把无关板块的涨跌家数显示在某标的旁边会误导判断。

        Args:
            db: 数据库会话。
            instrument: 标的实例。
            alias: 主题 → 板块名 的显式映射表，缺省为空。
            board_type: 限定板块类别，"industry" 行业 / "concept" 概念；为 None 时不过滤。

        Returns:
            含 up/down/ratio 的字典；无匹配时三个值均为 None。
        """
        alias = {k: v for k, v in (alias or {}).items() if not k.startswith("_")}
        candidates: list[str] = []
        for theme in (instrument.theme_l1, instrument.theme_l2):
            if not theme:
                continue
            if theme not in candidates:
                candidates.append(theme)
            mapped = alias.get(theme)
            if mapped and mapped not in candidates:
                candidates.append(mapped)
        if not candidates:
            return {"up": None, "down": None, "ratio": None}

        stmt = select(SectorSnapshot).where(SectorSnapshot.sector_name.in_(candidates))
        if board_type is not None:
            stmt = stmt.where(SectorSnapshot.board_type == board_type)
        rows = db.scalars(
            stmt.order_by(SectorSnapshot.trade_date.desc(), SectorSnapshot.fetched_at.desc())
        ).all()
        if not rows:
            return {"up": None, "down": None, "ratio": None}
        # 多个候选板块同时命中时，按 candidates 的优先级（原始 theme 优先于别名）
        # 选，而不是单纯取日期最新——避免别名盖掉更贴切的直接匹配。
        latest = min(rows, key=lambda row: (candidates.index(row.sector_name), -row.trade_date.toordinal()))
        total = latest.total_count or (latest.up_count + latest.down_count + latest.flat_count)
        ratio = round(latest.down_count / total * 100, 1) if total > 0 else None
        return {
            "up": latest.up_count,
            "down": latest.down_count,
            "ratio": ratio,
            "sector_name": latest.sector_name,
            "board_type": latest.board_type,
            "trade_date": latest.trade_date.isoformat(),
        }

    @staticmethod
    def _market_breadth(db: Session) -> dict[str, Any] | None:
        """读取全市场宽度快照（SectorSnapshot.board_type == "market"，单条 "全市场"）。

        用作指数 ETF 的广度参考：全市场涨/跌/平家数与跌比。无数据返回 None。
        """
        row = db.scalar(
            select(SectorSnapshot)
            .where(SectorSnapshot.board_type == "market")
            .order_by(SectorSnapshot.trade_date.desc(), SectorSnapshot.fetched_at.desc())
            .limit(1)
        )
        if not row:
            return None
        total = row.total_count or (row.up_count + row.down_count + row.flat_count)
        ratio = round(row.down_count / total * 100, 1) if total > 0 else None
        return {
            "up": row.up_count,
            "down": row.down_count,
            "flat": row.flat_count,
            "total": total,
            "ratio": ratio,
            "sector_name": row.sector_name,
            "trade_date": row.trade_date.isoformat(),
        }

    # ---------- 指标快照 ----------

    @staticmethod
    def _ma_state(frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty or "close" not in frame.columns:
            return {"label": "—", "color": "neutral", "dirs": [], "vals": "", "bullish": False}
        close = frame["close"]
        latest = float(close.iloc[-1])
        ma_values: dict[str, float | None] = {}
        for window in (5, 10, 20, 30):
            ma = close.rolling(window, min_periods=window).mean()
            ma_values[f"M{window}"] = _finite(ma.iloc[-1]) if len(ma) else None
        dirs: list[list[str]] = []
        labels: list[str] = []
        for key, value in ma_values.items():
            if value is None:
                continue
            labels.append(key)
            direction = "↑" if latest >= float(value) else "↓"
            dirs.append([key, direction])
        vals = " ".join(f"{key}={value:.4g}" for key, value in ma_values.items() if value is not None)
        # 多头排列: M5>M10>M20>M30
        ordered = [ma_values[k] for k in ("M5", "M10", "M20", "M30")]
        bullish = all(v is not None for v in ordered) and all(
            ordered[i] > ordered[i + 1] for i in range(len(ordered) - 1)
        )
        label = "多头排列" if bullish else ("空头排列" if all(v is not None and ordered[i] < ordered[i + 1] for i, v in enumerate(ordered[:-1])) else "多空交织")
        color = "#2ecc71" if bullish else ("#e74c3c" if label == "空头排列" else "#f39c12")
        return {"label": label, "color": color, "dirs": dirs, "vals": vals, "bullish": bullish}

    @staticmethod
    def _macd_state(frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty or "close" not in frame.columns:
            return {"label": "—", "cls": "dk-vf", "vals": ""}
        close = frame["close"]
        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=9, adjust=False).mean()
        hist = 2 * (dif - dea)
        latest_dif = _finite(dif.iloc[-1])
        latest_dea = _finite(dea.iloc[-1])
        prev_dif = _finite(dif.iloc[-2]) if len(dif) > 1 else None
        prev_dea = _finite(dea.iloc[-2]) if len(dea) > 1 else None
        vals = f"DIF={latest_dif:.4g} DEA={latest_dea:.4g}" if latest_dif is not None and latest_dea is not None else ""

        if latest_dif is None or latest_dea is None:
            return {"label": "—", "cls": "dk-vf", "vals": vals}

        # 近3日是否金叉/死叉
        recent_cross = None
        for i in range(min(3, len(dif) - 1)):
            idx = len(dif) - 1 - i
            if idx <= 0:
                break
            if dif.iloc[idx] > dea.iloc[idx] and dif.iloc[idx - 1] <= dea.iloc[idx - 1]:
                recent_cross = "golden"
                break
            if dif.iloc[idx] < dea.iloc[idx] and dif.iloc[idx - 1] >= dea.iloc[idx - 1]:
                recent_cross = "death"
                break

        if dif.iloc[-1] > dea.iloc[-1]:
            if recent_cross == "golden" and latest_dif > 0:
                return {"label": "强势金叉", "cls": "dk-tb", "vals": vals}
            if recent_cross == "golden" and latest_dif < 0:
                return {"label": "弱势金叉", "cls": "dk-tw", "vals": vals}
            if latest_dif > 0:
                return {"label": "多头延续", "cls": "dk-tm", "vals": vals}
            return {"label": "修复延续", "cls": "dk-tx", "vals": vals}
        # DIF < DEA（死叉状态）
        if recent_cross == "death":
            return {"label": "死叉", "cls": "dk-tr", "vals": vals}
        if prev_dif is not None and prev_dea is not None and prev_dif > prev_dea and latest_dif < latest_dea:
            return {"label": "将死叉", "cls": "dk-td", "vals": vals}
        return {"label": "空头延续", "cls": "dk-vf", "vals": vals}

    @staticmethod
    def _kdj_state(frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty:
            return {"label": "—", "cls": "dk-vf", "sub": "", "desc": "", "vals": ""}
        high, low, close = frame["high"], frame["low"], frame["close"]
        lowest = low.rolling(9, min_periods=1).min()
        highest = high.rolling(9, min_periods=1).max()
        denominator = (highest - lowest).replace(0, float("nan"))
        rsv = ((close - lowest) / denominator * 100).fillna(50).clip(0, 100)
        k, d = 50.0, 50.0
        for value in rsv.tolist():
            k = (2.0 / 3.0) * k + (1.0 / 3.0) * float(value)
            d = (2.0 / 3.0) * d + (1.0 / 3.0) * k
        j = 3 * k - 2 * d
        vals = f"K={k:.1f} D={d:.1f}"

        if j > 100:
            return {"label": f"J={j:.1f}", "cls": "dk-tr", "sub": "超买", "desc": "短期过热 · 回调风险高", "vals": vals}
        if j >= 90:
            return {"label": f"J={j:.1f}", "cls": "dk-tx", "sub": "偏高", "desc": "动能偏强 · 谨慎追高", "vals": vals}
        if k < d:
            return {"label": f"J={j:.1f}", "cls": "dk-tr", "sub": "死叉", "desc": "空头信号 · 短线看跌", "vals": vals}
        if j < 20:
            return {"label": f"J={j:.1f}", "cls": "dk-tb", "sub": "低位", "desc": "超卖 · 反弹概率升高", "vals": vals}
        return {"label": f"J={j:.1f}", "cls": "dk-tm", "sub": "健康", "desc": "趋势健康 · 可持有", "vals": vals}

    @staticmethod
    def _rsi_state(frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty or "close" not in frame.columns:
            return {"val": "—", "desc": ""}
        close = frame["close"]
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, float("nan"))
        rsi = float((100 - (100 / (1 + rs))).iloc[-1]) if len(avg_gain) else 50.0
        if not rsi == rsi:
            rsi = 50.0
        if rsi >= 70:
            desc = "超买 · 短期回调风险高"
        elif rsi >= 50:
            desc = "正常偏强 · 趋势中段"
        elif rsi >= 30:
            desc = "偏弱 · 动能不足"
        else:
            desc = "超卖 · 反弹概率升高"
        return {"val": round(rsi, 1), "desc": desc}

    @staticmethod
    def _volume_state(frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty or "volume" not in frame.columns:
            return {"text": "—", "cls": "dk-vf"}
        volume = frame["volume"]
        latest = float(volume.iloc[-1]) or 0.0
        avg20 = float(volume.rolling(20, min_periods=10).mean().iloc[-1]) or 1.0
        ratio = latest / avg20 if avg20 > 0 else 1.0
        if ratio >= 1.15:
            return {"text": f"放量 {ratio:.2f}", "cls": "dk-vu"}
        if ratio <= 0.9:
            return {"text": f"缩量 {ratio:.2f}", "cls": "dk-vd"}
        return {"text": f"平量 {ratio:.2f}", "cls": "dk-vf"}

    # ---------- 缠论（chanlun，可选） ----------

    @staticmethod
    def _chanlun_state(frame: pd.DataFrame) -> dict[str, Any]:
        """基于 chanlun 框架计算缠论摘要；框架不可用时返回 unavailable。"""
        try:
            import chanlun
        except ImportError:
            return {"available": False, "note": "chanlun 未安装"}
        try:
            if frame.empty or "close" not in frame.columns:
                return {"available": False, "note": "数据不足"}
            import datetime as dt

            klines = []
            for i, row in frame.iterrows():
                ts = row.get("trade_date")
                if hasattr(ts, "timestamp"):  # datetime
                    ts_int = int(ts.timestamp())
                elif hasattr(ts, "toordinal"):  # datetime.date
                    ts_int = int(dt.datetime.combine(ts, dt.time()).timestamp())
                else:
                    ts_int = int(ts)
                klines.append(
                    chanlun.K线.创建普K(
                        "CHAN",
                        ts_int,
                        float(row["open"]),
                        float(row["high"]),
                        float(row["low"]),
                        float(row["close"]),
                        float(row.get("volume") or 0.0),
                        i,
                        86400,
                    )
                )
            config = chanlun.缠论配置()
            obs = chanlun.观察者("CHAN", 86400, config)
            for kline in klines:
                obs.增加原始K线(kline)
            return {
                "available": True,
                "fenxing": len(getattr(obs, "分型序列", []) or []),
                "bi": len(getattr(obs, "笔序列", []) or []),
                "segments": len(getattr(obs, "线段序列", []) or []),
                "zs": len(getattr(obs, "中枢序列", []) or []),
                "note": "缠论(分型/笔/线段/中枢) 研究视图",
            }
        except Exception as exc:  # 框架异常不阻断看板
            logger.warning("chanlun analysis failed: %s", exc)
            return {"available": False, "note": f"缠论计算失败: {type(exc).__name__}"}

    # ---------- 行构建 ----------

    def _row(self, db: Session, instrument: Instrument) -> dict[str, Any]:
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
        pattern = pattern_forecast_snapshot(frame) if not frame.empty else {"expected_return": None, "p_up": None, "confidence": 0, "sample_count": 0, "calibration_status": "not_calibrated", "note": "数据不足"}
        chan = self._chanlun_state(frame)

        # 板块涨跌家数：行业板块（theme 直接命中 → 再试 config.sector_alias 显式映射）；
        # 概念板块（config.concept_alias）；都没命中就是没数据，占位 null（前端显示 "—"），
        # 不用无关板块兜底。
        sector = self._sector_state(db, instrument, self._sector_alias(), board_type="industry")
        sector_concept = self._sector_state(db, instrument, self._concept_alias(), board_type="concept")

        # 全市场宽度：仅宽基 / 指数主题 ETF 作为广度参考（config.broad_market_themes）。
        market_breadth: dict[str, Any] | None = None
        if instrument.theme_l1 in self._broad_market_themes():
            market_breadth = self._market_breadth(db)

        forecast_expected = pattern.get("expected_return")
        forecast_label = f"{forecast_expected:+.2%}" if forecast_expected is not None else "—"
        conf_text = f"conf {int(pattern.get('confidence') or 0)}" if pattern.get("confidence") else ""

        # 近1周（5日收益，若无 quote 用 close 序列）
        week_label = "—"
        if len(frame) >= 6:
            close = frame["close"]
            ret5 = (float(close.iloc[-1]) / float(close.iloc[-6]) - 1) if float(close.iloc[-6]) > 0 else None
            if ret5 is not None:
                week_label = f"{ret5 * 100:+.1f}%"

        # 量能
        volume = self._volume_state(frame)

        # 操作建议（研究态启发式，不构成交易指令）
        action = self._research_action(td, pattern, volume, current_price)

        return {
            "name": instrument.name,
            "ts_code": instrument.ts_code,
            "theme_l1": instrument.theme_l1,
            "current_price": current_price,
            "today_pct_change": today_pct,
            "vs_yesterday": vs_yesterday,
            "volume": volume,
            "ma": self._ma_state(frame),
            "macd": self._macd_state(frame),
            "kdj": self._kdj_state(frame),
            "td": td,
            "rsi": self._rsi_state(frame),
            "sector": sector,
            "sector_concept": sector_concept,
            "market_breadth": market_breadth,
            "week_label": week_label,
            "forecast": {
                "label": forecast_label,
                "conf": conf_text,
                "expected_return": forecast_expected,
                "confidence": pattern.get("confidence"),
                "sample_count": pattern.get("sample_count"),
                "calibration_status": pattern.get("calibration_status"),
                "note": pattern.get("note"),
            },
            "chanlun": chan,
            "action": action,
            "actionable": False,  # 研究态：永不 actionable
            "as_of": datetime.now(self.timezone).isoformat(timespec="seconds"),
        }

    @staticmethod
    def _research_action(td: dict[str, Any], pattern: dict[str, Any], volume: dict[str, Any], price: float | None) -> str:
        """研究态操作建议（启发式，非交易指令）。

        目标看板分档：可加仓 / 可入场 / 可试探 / 观望 / 减仓
        """
        direction = td.get("direction")
        td_label = td.get("label", "—")
        # TD9 顶 -> 减仓
        if direction == "top" and td_label.startswith("TD"):
            return "减仓"
        # TD9 底 + 超卖 -> 可加仓（保守起见给可试探）
        if direction == "bottom" and td_label.startswith("TD"):
            return "可试探"
        # 超买（KDJ 由 _kdj_state 给出，这里用 RSI 兜底）
        confidence = float(pattern.get("confidence") or 0)
        if confidence >= 60:
            return "可入场"
        if confidence >= 40:
            return "可试探"
        return "观望"

    # ---------- 汇总 ----------

    def summary(self, db: Session) -> dict[str, Any]:
        instruments = self._instruments(db)
        rows = [self._row(db, instrument) for instrument in instruments]
        counts = {
            "可加仓": sum(1 for row in rows if row["action"] == "可加仓"),
            "可入场": sum(1 for row in rows if row["action"] == "可入场"),
            "可试探": sum(1 for row in rows if row["action"] == "可试探"),
            "观望": sum(1 for row in rows if row["action"] == "观望"),
            "减仓": sum(1 for row in rows if row["action"] == "减仓"),
        }
        return {
            "generated_at": datetime.now(self.timezone).isoformat(timespec="seconds"),
            "automatic_orders": False,
            "counts": counts,
            "rows": rows,
            "disclaimers": [
                "本看板为研究视图，不构成投资建议，不生成自动订单。",
                "TD 九转为确定性指标；明日预测为形态匹配（horizon=1）且未完成 walk-forward 校准，仅供研究参考。",
                "缠论指标基于 chanlun 框架计算，仅作研究视图。",
            ],
        }

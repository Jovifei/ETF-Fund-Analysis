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
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.models import (
    DailyBar,
    ForecastSnapshot,
    IndicatorSnapshot,
    Instrument,
    QuoteSnapshot,
    SectorSnapshot,
)
from app.services.current_decision_service import CurrentDecisionService
from app.services.snapshot_contract import SNAPSHOT_CONTRACT_VERSION, snapshot_issues
from app.utils.indicator_state import (
    kdj_state_view,
    ma_state_view,
    macd_state_view,
    rsi_state_view,
    td_state_view,
    thresholds_from_strategy,
    volume_state_view,
)

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


def _forecast_note(diagnostics: Any) -> str:
    """Read an optional note without assuming legacy diagnostics JSON shape."""
    if isinstance(diagnostics, dict):
        note = diagnostics.get("note")
        if isinstance(note, str) and note.strip():
            return note.strip()
    return "persisted ForecastSnapshot"


class KlineStabilizationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        path = PROJECT_ROOT / "config" / "etf_1430_workbench.json"
        self.config: dict[str, Any] = {}
        if path.is_file():
            import json

            self.config = json.loads(path.read_text(encoding="utf-8"))
        self.timezone = ZoneInfo(str(self.config.get("decision_timezone", "Asia/Shanghai")))
        # 指标状态阈值与 signal_grade 同一来源（strategy.signal_grade），单一口径。
        self.thresholds = thresholds_from_strategy(self.settings.load_strategy())

    # ---------- 数据获取 ----------

    def _instruments(self, db: Session) -> list[Instrument]:
        return list(db.scalars(select(Instrument).where(Instrument.enabled.is_(True))).all())

    def _latest_indicator_values(
        self, db: Session, instrument_id: int
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        """Current-compatible latest indicator plus previous same-identity values."""
        current = db.scalar(
            select(IndicatorSnapshot)
            .where(IndicatorSnapshot.instrument_id == instrument_id)
            .order_by(
                IndicatorSnapshot.as_of_date.desc(),
                IndicatorSnapshot.generated_at.desc(),
                IndicatorSnapshot.id.desc(),
            )
            .limit(1)
        )
        issues = snapshot_issues(current, self.settings, None, kind="indicator")
        if current is None or issues:
            return {}, {}, issues
        from app.utils.indicator_history import previous_values as previous_indicator_values
        previous = previous_indicator_values(db, current) or {}
        return dict(current.values_json or {}), previous, []

    def _recent_daily_closes(self, db: Session, instrument_id: int) -> list[float | None]:
        values = db.scalars(
            select(DailyBar.close)
            .where(DailyBar.instrument_id == instrument_id)
            .order_by(DailyBar.trade_date.desc())
            .limit(6)
        ).all()
        return [_finite(value) for value in reversed(values)]

    def _latest_quote(self, db: Session, instrument_id: int) -> QuoteSnapshot | None:
        return db.scalar(
            select(QuoteSnapshot)
            .where(QuoteSnapshot.instrument_id == instrument_id)
            .order_by(QuoteSnapshot.quote_time.desc())
            .limit(1)
        )

    def _latest_forecast(
        self, db: Session, instrument_id: int, horizon: int = 1
    ) -> tuple[ForecastSnapshot | None, list[str]]:
        row = db.scalar(
            select(ForecastSnapshot)
            .where(ForecastSnapshot.instrument_id == instrument_id, ForecastSnapshot.horizon == horizon)
            .order_by(
                ForecastSnapshot.as_of_date.desc(),
                ForecastSnapshot.generated_at.desc(),
                ForecastSnapshot.id.desc(),
            )
            .limit(1)
        )
        issues = snapshot_issues(row, self.settings, None, kind="forecast")
        return (row if not issues else None), issues

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

        健壮性：优先取「真实源」（`source != "mock-sector"`），仅当不存在任何真实源时
        才回退到 mock 行。这样可避免 mock provider 的演示假数据（如 3387/2039/126）
        顶掉真实 AKShare 宽度，防止演示数据遮蔽真实研究结论。
        """
        row = db.scalar(
            select(SectorSnapshot)
            .where(SectorSnapshot.board_type == "market")
            .order_by(
                # 真实源排在最前（0），mock 源排最后（1）
                case((SectorSnapshot.source != "mock-sector", 0), else_=1),
                SectorSnapshot.trade_date.desc(),
                SectorSnapshot.fetched_at.desc(),
            )
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
            "source": row.source,
            "is_mock": row.source == "mock-sector",
        }

    # ---------- 指标快照 ----------

    # ---------- Persisted Chan compatibility summary ----------

    @staticmethod
    def _persisted_chan_summary(db: Session, instrument: Instrument) -> dict[str, Any]:
        if instrument.kind not in {"ETF", "LOF"}:
            view: dict[str, Any] = {
                "available": False,
                "reason_code": "unsupported_instrument_type",
                "counts": {},
                "observation_id": None,
                "settlement_status": None,
            }
        else:
            from app.services.chan_read_service import read_latest

            view = read_latest(db, instrument.ts_code, "D")

        available = view.get("available") is True
        counts = view.get("counts") if available else {}
        counts = counts if isinstance(counts, dict) else {}
        reason = view.get("reason_code")
        return {
            "available": available,
            "fenxing": counts.get("fx") if available else None,
            "bi": counts.get("bi") if available else None,
            "zs": counts.get("zs") if available else None,
            "segments": None,
            "source": "persisted_r4c_observed_revision",
            "observation_id": view.get("observation_id"),
            "settlement_status": view.get("settlement_status"),
            "engine_confirmation": "unknown",
            "reason_code": reason,
            "note": reason or "persisted R4C observed revision",
        }

    # ---------- 行构建 ----------

    def _row(
        self,
        db: Session,
        instrument: Instrument,
        *,
        current_decision: dict[str, Any] | None = None,
        decision_snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        # 指标状态唯一数据源：IndicatorSnapshot.values_json（与 signal_grade 同一口径）。
        values, previous_values, indicator_issues = self._latest_indicator_values(db, instrument.id)
        quote = self._latest_quote(db, instrument.id)

        today_pct = _pct(_finite(quote.pct_change)) if quote else None
        current_price = _finite(quote.price) if quote else None
        if current_price is None:
            current_price = _finite(values.get("close"))
        prev_close = _finite(previous_values.get("close"))
        vs_yesterday = "→"
        if current_price and prev_close and prev_close > 0:
            change = (current_price - prev_close) / prev_close
            vs_yesterday = "↑" if change > 0.001 else ("↓" if change < -0.001 else "→")

        td = td_state_view(values)
        stored_forecast, forecast_issues = self._latest_forecast(db, instrument.id, 1)
        if stored_forecast is None:
            pattern = {
                "expected_return": None, "p_up": None, "confidence": 0, "sample_count": 0,
                "calibration_status": "not_calibrated", "note": "persisted forecast unavailable",
                "source": "unavailable", "p_up_semantics": "unavailable",
                "as_of_date": None, "feature_basis": "unavailable", "intraday_provisional_used": False,
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
                "as_of_date": stored_forecast.as_of_date.isoformat(),
                "feature_basis": "settled_daily_bars",
                "intraday_provisional_used": False,
                "p_up_semantics": (
                    "calibrated_up_probability"
                    if status == "calibrated"
                    else "weighted_historical_neighbor_up_frequency"
                ),
            }
        chan = self._persisted_chan_summary(db, instrument)
        if current_decision is None:
            decision_snapshot_id, decisions = CurrentDecisionService(self.settings).resolve_many(db, [instrument])
            current_decision = decisions.get(str(instrument.ts_code).strip().upper())

        # 板块涨跌家数：行业板块（theme 直接命中 → 再试 config.sector_alias 显式映射）；
        # 概念板块（config.concept_alias）；都没命中就是没数据，占位 null（前端显示 "—"），
        # 不用无关板块兜底。
        sector = self._sector_state(db, instrument, self._sector_alias(), board_type="industry")
        sector_concept = self._sector_state(db, instrument, self._concept_alias(), board_type="concept")

        # 全市场宽度：仅宽基 / 指数主题 ETF 作为广度参考（config.broad_market_themes，
        # 同时匹配 theme_l1 与 theme_l2，以覆盖 创业板/科创50 等跨行业指数）。
        market_breadth: dict[str, Any] | None = None
        broad_themes = set(self._broad_market_themes())
        if instrument.theme_l1 in broad_themes or instrument.theme_l2 in broad_themes:
            market_breadth = self._market_breadth(db)

        forecast_expected = pattern.get("expected_return")
        forecast_label = f"{forecast_expected:+.2%}" if forecast_expected is not None else "—"
        conf_text = f"conf {int(pattern.get('confidence') or 0)}" if pattern.get("confidence") else ""

        # 近1周：优先读落库 return_5d（与指标引擎同一口径）
        week_label = "—"
        ret5 = _finite(values.get("return_5d"))
        if ret5 is None:
            recent_closes = self._recent_daily_closes(db, instrument.id)
            first_close = recent_closes[0] if len(recent_closes) == 6 else None
            last_close = recent_closes[-1] if len(recent_closes) == 6 else None
            if first_close is not None and last_close is not None and first_close > 0:
                ret5 = last_close / first_close - 1
        if ret5 is not None:
            week_label = f"{ret5 * 100:+.1f}%"

        # 量能（落库 volume_ratio，单一口径）
        volume = volume_state_view(values, self.thresholds)

        # Current action is projected from the single canonical decision contract.
        action = str((current_decision or {}).get("state") or "数据异常")

        return {
            "name": instrument.name,
            "ts_code": instrument.ts_code,
            "theme_l1": instrument.theme_l1,
            "current_price": current_price,
            "today_pct_change": today_pct,
            "vs_yesterday": vs_yesterday,
            "volume": volume,
            "ma": ma_state_view(values, previous_values),
            "macd": macd_state_view(values, previous_values, self.thresholds),
            "kdj": kdj_state_view(values, previous_values, self.thresholds),
            "td": td,
            "rsi": rsi_state_view(values, self.thresholds),
            "snapshot_compatibility": {
                "contract": SNAPSHOT_CONTRACT_VERSION,
                "indicator": indicator_issues,
                "forecast_1d": forecast_issues,
            },
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
                "source": pattern.get("source"),
                "p_up": pattern.get("p_up"),
                "p_up_semantics": pattern.get("p_up_semantics"),
                "as_of_date": pattern.get("as_of_date"),
                "feature_basis": pattern.get("feature_basis"),
                "intraday_provisional_used": pattern.get("intraday_provisional_used", False),
            },
            "chanlun": chan,
            "action": action,
            "action_source": (current_decision or {}).get("source", "unavailable"),
            "action_canonical": bool((current_decision or {}).get("canonical", False)),
            "decision_snapshot_id": decision_snapshot_id,
            "actionable": False,  # 研究态：永不 actionable
            "as_of": datetime.now(self.timezone).isoformat(timespec="seconds"),
        }

    # ---------- 汇总 ----------

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
            "generated_at": datetime.now(self.timezone).isoformat(timespec="seconds"),
            "automatic_orders": False,
            "current_decision_contract": "decision_board_snapshot_then_signal_grade_then_signal_snapshot_last_resort",
            "decision_snapshot_id": decision_snapshot_id,
            "counts": counts,
            "rows": rows,
            "disclaimers": [
                "本看板为研究视图，不构成投资建议，不生成自动订单。",
                "action 与主页共用唯一 current decision；TD/MA/MACD/KDJ/RSI/缠论只作解释，不生成第二套动作。",
                "明日预测读取与主页相同的持久化 ForecastSnapshot；未校准 p_up 仅表示历史相似样本上涨占比。",
                "缠论兼容摘要读取已持久化的 R4C 观测修订，仅作研究视图。",
            ],
        }

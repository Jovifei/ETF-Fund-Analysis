from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import IndicatorSnapshot, Instrument, NewsItem, SignalSnapshot
from app.services.decision_board_service import DecisionBoardService
from app.services.holding_service import HoldingService
from app.services.signal_grade_service import SignalGradeService
from app.utils.numbers import clamp, finite_or_none, percentile_rank

OPPORTUNITY_STATES = frozenset({"可加仓", "可入场", "可试探"})
RISK_STATES = frozenset({"观望", "减仓", "数据异常"})
LEGACY_OPPORTUNITY_STATES = frozenset({"可入场", "可试探", "加仓", "小幅加仓"})
LEGACY_RISK_STATES = frozenset({"减仓", "风险观察", "数据异常"})


class SignalCenterService:
    """信号中心读取层研究视图。

    当前五档结论直接读取最新 DecisionBoardSnapshot；若尚无决策快照才回退
    SignalGradeService，因此与主决策看板使用同一当前结论。SignalSnapshot 仅
    保留生产分数/置信度审计，系数只影响前排排序和止盈热度，不改变当前五档。
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()
        self.config = self.strategy.get("signal_center", {})
        self.version = self.strategy.get("signal_center_version", "signal-center-v0.1.0")

    # ------------------------------------------------------------------ build

    def build(
        self,
        db: Session,
        coefficient: float | None = None,
        days: int | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        minimum, maximum, default = self._coefficient_bounds()
        if coefficient is None:
            coefficient = default
        coefficient = round(clamp(float(coefficient), minimum, maximum), 2)
        days_limit = int(days) if days else int(self.config.get("curve_days", 60))
        front_size = int(self.config.get("front_size", 10))

        instruments = db.scalars(
            select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)
        ).all()
        latest_signals = self._latest_signals(db)
        latest_indicators = self._latest_indicators(db)
        holdings = {row["ts_code"]: row for row in HoldingService().list(db, user_id=user_id) if row.get("ts_code")}
        decision_payload = DecisionBoardService(self.settings).read_latest(db, horizon=1) or {}
        decision_by_code = {row["ts_code"]: row for row in decision_payload.get("rows", [])}
        grade_payload = SignalGradeService(self.settings).build(db) if not decision_by_code else {}
        fallback_by_code = {row["ts_code"]: row for row in grade_payload.get("rows", [])}
        current_source = "decision_board_snapshot" if decision_by_code else "signal_grade_fallback"

        rows: list[dict[str, Any]] = []
        for instrument in instruments:
            state_row = decision_by_code.get(instrument.ts_code) or fallback_by_code.get(instrument.ts_code)
            if state_row is None:
                continue
            signal = latest_signals.get(instrument.id)
            indicator = latest_indicators.get(instrument.id)
            values = indicator.values_json if indicator else {}
            raw_score = float(signal.score or 0) if signal is not None else 0.0
            effective = round(raw_score * coefficient, 2)
            board_grade = str(state_row.get("grade") or "数据异常")
            rows.append(
                {
                    "instrument": instrument,
                    "signal": signal,
                    "indicator": indicator,
                    "values": values,
                    "effective": effective,
                    "board_grade": board_grade,
                    "board_grade_reason": state_row.get("grade_reason"),
                    "categories": self._categories(board_grade, values, coefficient),
                    "heat": self._heat(values),
                    "holding": holdings.get(instrument.ts_code),
                }
            )

        summary = {
            "total": len(rows),
            "opportunity": sum(1 for row in rows if "opportunity" in row["categories"]),
            "risk": sum(1 for row in rows if "risk" in row["categories"]),
            "take_profit": sum(1 for row in rows if "take_profit" in row["categories"]),
        }
        current_states = {
            row["instrument"].ts_code: {
                "state": row["board_grade"],
                "reason": row.get("board_grade_reason"),
                "production_state": row["signal"].state if row.get("signal") is not None else None,
            }
            for row in rows
        }
        return {
            "generated_at": datetime.now(self.settings.timezone),
            "version": self.version,
            "strategy_version": self.strategy.get("version"),
            "current_state_source": current_source,
            "current_state_snapshot_id": decision_payload.get("snapshot_id") if decision_by_code else None,
            "current_state_version": grade_payload.get("version") if not decision_by_code else "decision-board-snapshot",
            "current_states": current_states,
            "coefficient_semantics": "ranking_and_take_profit_only",
            "coefficient": coefficient,
            "coefficient_bounds": {"min": minimum, "max": maximum},
            "research_only": self.settings.market_provider == "mock",
            "summary": summary,
            "fronts": {
                "opportunity": self._front(rows, "opportunity", front_size, self._opportunity_key),
                "risk": self._front(rows, "risk", front_size, self._risk_key),
                "take_profit": self._front(rows, "take_profit", front_size, self._heat_key),
            },
            "curve": self._curve(db, coefficient, days_limit),
            "curve_source": "production_signal_history_legacy",
            "sectors": self._sectors(db),
        }

    # ----------------------------------------------------------------- fronts

    def _front(
        self,
        rows: list[dict[str, Any]],
        category: str,
        size: int,
        sort_key: Any,
    ) -> list[dict[str, Any]]:
        selected = [row for row in rows if category in row["categories"]]
        selected.sort(key=sort_key)
        return [self._front_item(row, category) for row in selected[: max(0, size)]]

    @staticmethod
    def _opportunity_key(row: dict[str, Any]) -> tuple[float, float]:
        signal_score = float(row["signal"].score or 0) if row.get("signal") is not None else 0.0
        return (-row["effective"], -signal_score)

    @staticmethod
    def _risk_key(row: dict[str, Any]) -> tuple[float, float]:
        indicator = row["indicator"]
        risk_score = float(indicator.risk_score) if indicator else 0.0
        return (-risk_score, row["effective"])

    @staticmethod
    def _heat_key(row: dict[str, Any]) -> tuple[float, float]:
        return (-(row["heat"] or 0.0), -row["effective"])

    def _front_item(self, row: dict[str, Any], category: str) -> dict[str, Any]:
        instrument: Instrument = row["instrument"]
        signal: SignalSnapshot | None = row["signal"]
        indicator: IndicatorSnapshot | None = row["indicator"]
        values = row["values"]
        holding: dict[str, Any] | None = row["holding"]
        return {
            "ts_code": instrument.ts_code,
            "name": instrument.name,
            "theme_l1": instrument.theme_l1,
            "theme_l2": instrument.theme_l2,
            "category": category,
            "state": row["board_grade"],
            "board_grade": row["board_grade"],
            "board_grade_reason": row.get("board_grade_reason"),
            "production_state": signal.state if signal is not None else None,
            "score": round(float(signal.score or 0), 2) if signal is not None else 0.0,
            "effective_score": row["effective"],
            "confidence": round(float(signal.confidence or 0), 2) if signal is not None else 0.0,
            "is_actionable": bool(signal.is_actionable) if signal is not None else False,
            "technical_score": round(float(indicator.technical_score), 2) if indicator else None,
            "risk_score": round(float(indicator.risk_score), 2) if indicator else None,
            "trend_label": indicator.trend_label if indicator else None,
            "return_5d": finite_or_none(values.get("return_5d")),
            "return_20d": finite_or_none(values.get("return_20d")),
            "rsi14": finite_or_none(values.get("rsi14")),
            "heat": row["heat"],
            "signal_time": signal.as_of_time if signal is not None else None,
            "expires_at": signal.expires_at if signal is not None else None,
            "in_account": holding is not None,
            "holding": self._holding_view(holding) if holding else None,
        }

    @staticmethod
    def _holding_view(holding: dict[str, Any]) -> dict[str, Any]:
        return {
            "shares": holding.get("shares"),
            "cost_price": holding.get("cost_price"),
            "latest_price": holding.get("latest_price"),
            "market_value": holding.get("market_value"),
            "pnl": holding.get("pnl"),
            "pnl_pct": holding.get("pnl_pct"),
            "current_weight": holding.get("current_weight"),
        }

    # ------------------------------------------------------- classification

    def _coefficient_bounds(self) -> tuple[float, float, float]:
        config = self.config.get("coefficient", {})
        return (
            float(config.get("min", 0.5)),
            float(config.get("max", 1.5)),
            float(config.get("default", 1.0)),
        )

    def _categories(
        self, board_grade: str, values: dict[str, Any], coefficient: float
    ) -> set[str]:
        categories: set[str] = set()
        if board_grade in OPPORTUNITY_STATES:
            categories.add("opportunity")
        if board_grade in RISK_STATES:
            categories.add("risk")
        if self._is_overheated(values, coefficient):
            categories.add("take_profit")
        return categories

    def _legacy_categories(
        self, state: str, effective: float, values: dict[str, Any], coefficient: float
    ) -> set[str]:
        signal_config = self.strategy.get("signal", {})
        entry = float(signal_config.get("entry_score", 68))
        reduce_line = float(signal_config.get("reduce_score", 38))
        categories: set[str] = set()
        if state in LEGACY_OPPORTUNITY_STATES or effective >= entry:
            categories.add("opportunity")
        if state in LEGACY_RISK_STATES or effective < reduce_line:
            categories.add("risk")
        if self._is_overheated(values, coefficient):
            categories.add("take_profit")
        return categories

    def _is_overheated(self, values: dict[str, Any], coefficient: float) -> bool:
        config = self.config.get("take_profit", {})
        min_return = float(config.get("min_return_20d", 0.10))
        rsi_floor = float(config.get("rsi_floor", 68))
        heat_threshold = float(config.get("heat_threshold", 0.62))
        return_20d = finite_or_none(values.get("return_20d"))
        if return_20d is None or return_20d <= 0 or return_20d < min_return / coefficient:
            return False
        rsi14 = finite_or_none(values.get("rsi14"))
        if rsi14 is not None and rsi14 >= rsi_floor:
            return True
        heat = self._heat(values)
        return heat is not None and heat >= heat_threshold / coefficient

    @staticmethod
    def _heat(values: dict[str, Any]) -> float | None:
        """过热度：0.5×20 日动量 + 0.3×5 日动量（30% 饱和）+ 0.2×RSI14，0-1。"""
        return_20d = finite_or_none(values.get("return_20d"))
        if return_20d is None:
            return None
        saturation = 0.30
        return_5d = finite_or_none(values.get("return_5d")) or 0.0
        rsi14 = finite_or_none(values.get("rsi14"))
        rsi_component = clamp(rsi14 / 100.0, 0.0, 1.0) if rsi14 is not None else 0.5
        heat = (
            0.5 * clamp(return_20d / saturation, 0.0, 1.0)
            + 0.3 * clamp(return_5d / saturation, 0.0, 1.0)
            + 0.2 * rsi_component
        )
        return round(clamp(heat, 0.0, 1.0), 4)

    # ------------------------------------------------------------------ curve

    def _curve(self, db: Session, coefficient: float, days_limit: int) -> list[dict[str, Any]]:
        snapshots = db.scalars(
            select(SignalSnapshot).order_by(SignalSnapshot.as_of_time.asc())
        ).all()
        if not snapshots:
            return []
        by_day: dict[date, dict[int, SignalSnapshot]] = {}
        for snapshot in snapshots:
            day = self._local_date(snapshot.as_of_time)
            inner = by_day.setdefault(day, {})
            existing = inner.get(snapshot.instrument_id)
            if existing is None or snapshot.as_of_time >= existing.as_of_time:
                inner[snapshot.instrument_id] = snapshot
        recent_days = sorted(by_day)[-max(1, days_limit) :]
        values_by_key = self._indicator_values_since(db, recent_days[0])
        curve: list[dict[str, Any]] = []
        for day in recent_days:
            counts = {"total": 0, "opportunity": 0, "risk": 0, "take_profit": 0}
            for instrument_id, snapshot in by_day[day].items():
                counts["total"] += 1
                values = values_by_key.get((instrument_id, day), {})
                effective = float(snapshot.score or 0) * coefficient
                for category in self._legacy_categories(snapshot.state, effective, values, coefficient):
                    counts[category] += 1
            curve.append({"date": day.isoformat(), **counts})
        return curve

    def _indicator_values_since(
        self, db: Session, since: date
    ) -> dict[tuple[int, date], dict[str, Any]]:
        rows = db.scalars(select(IndicatorSnapshot).where(IndicatorSnapshot.as_of_date >= since)).all()
        return {(row.instrument_id, row.as_of_date): row.values_json for row in rows}

    def _local_date(self, value: datetime) -> date:
        if value.tzinfo is None:
            return value.date()
        return value.astimezone(self.settings.timezone).date()

    # ---------------------------------------------------------------- sectors

    def _sectors(self, db: Session) -> list[dict[str, Any]]:
        instruments = db.scalars(
            select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)
        ).all()
        latest_indicators = self._latest_indicators(db)
        themes = {instrument.theme_l1 for instrument in instruments if instrument.theme_l1}
        news_scores = self._sector_news_scores(db, themes)

        grouped: dict[str, list[dict[str, Any]]] = {}
        for instrument in instruments:
            theme = instrument.theme_l1
            indicator = latest_indicators.get(instrument.id)
            if not theme or indicator is None:
                continue
            values = indicator.values_json or {}
            grouped.setdefault(theme, []).append(
                {
                    "ts_code": instrument.ts_code,
                    "name": instrument.name,
                    "technical_score": float(indicator.technical_score or 0),
                    "risk_score": float(indicator.risk_score or 0),
                    "return_5d": finite_or_none(values.get("return_5d")),
                    "return_20d": finite_or_none(values.get("return_20d")),
                    "return_60d": finite_or_none(values.get("return_60d")),
                    "above_ma20": self._above_ma20(values),
                }
            )

        momentum_by_theme = {
            theme: self._mean(
                [
                    self._momentum(member)
                    for member in members
                    if self._momentum(member) is not None
                ]
            )
            for theme, members in grouped.items()
        }
        momentum_values = [value for value in momentum_by_theme.values() if value is not None]
        weights: dict[str, float] = self.config.get("sector_weights", {})

        sectors: list[dict[str, Any]] = []
        for theme, members in grouped.items():
            momentum = momentum_by_theme.get(theme)
            technical = self._mean([member["technical_score"] for member in members])
            risk_mean = self._mean([member["risk_score"] for member in members])
            breadth_flags = [member["above_ma20"] for member in members if member["above_ma20"] is not None]
            breadth = (sum(1 for flag in breadth_flags if flag) / len(breadth_flags)) if breadth_flags else None
            news = news_scores.get(theme)
            components = {
                "momentum": percentile_rank(momentum_values, momentum) if momentum is not None else None,
                "technical": technical,
                "breadth": breadth * 100.0 if breadth is not None else None,
                "news": news,
                "risk_inverse": 100.0 - risk_mean if risk_mean is not None else None,
            }
            available = {key: value for key, value in components.items() if value is not None}
            if not available or "momentum" not in available:
                continue
            total_weight = sum(float(weights.get(key, 0.0)) for key in available)
            if total_weight <= 0:
                continue
            strength = sum(
                float(weights.get(key, 0.0)) / total_weight * value
                for key, value in available.items()
            )
            sectors.append(
                {
                    "theme_l1": theme,
                    "strength": round(clamp(strength, 0.0, 100.0), 2),
                    "momentum_score": round(available["momentum"], 2),
                    "technical_score": round(technical, 2) if technical is not None else None,
                    "breadth": round(breadth, 4) if breadth is not None else None,
                    "news_score": round(news, 2) if news is not None else None,
                    "risk_score": round(risk_mean, 2) if risk_mean is not None else None,
                    "member_count": len(members),
                    "members": sorted(members, key=lambda item: item["ts_code"]),
                }
            )
        sectors.sort(key=lambda item: (-item["strength"], item["theme_l1"]))
        for rank, sector in enumerate(sectors, start=1):
            sector["rank"] = rank
        return sectors

    @staticmethod
    def _momentum(member: dict[str, Any]) -> float | None:
        parts = [member.get("return_20d"), member.get("return_5d"), member.get("return_60d")]
        if parts[0] is None:
            return None
        r20, r5, r60 = parts[0], parts[1] or 0.0, parts[2] or 0.0
        return round(0.5 * r20 + 0.3 * r5 + 0.2 * r60, 6)

    @staticmethod
    def _above_ma20(values: dict[str, Any]) -> bool | None:
        close = finite_or_none(values.get("close"))
        ma20 = finite_or_none(values.get("ma20"))
        if close is None or ma20 is None or ma20 == 0:
            return None
        return close > ma20

    @staticmethod
    def _mean(values: list[float]) -> float | None:
        clean = [value for value in values if value is not None]
        if not clean:
            return None
        return sum(clean) / len(clean)

    def _sector_news_scores(self, db: Session, themes: set[str]) -> dict[str, float]:
        hours = int(self.config.get("news_lookback_hours", 72))
        now = datetime.now(self.settings.timezone)
        cutoff = now - timedelta(hours=hours)
        rows = db.scalars(
            select(NewsItem).where(NewsItem.published_at >= cutoff).order_by(NewsItem.published_at.desc())
        ).all()
        if not rows or not themes:
            return {}
        impacts: dict[str, list[float]] = {}
        for row in rows:
            score = finite_or_none(row.impact_score)
            if score is None:
                continue
            published_at = row.published_at
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=self.settings.timezone)
            age_hours = max(0.0, (now - published_at).total_seconds() / 3600)
            decay = max(0.2, 1 - age_hours / 96)
            for affected in row.affected_themes_json or []:
                if not isinstance(affected, str) or not affected:
                    continue
                for theme in themes:
                    # 与 signal_service 同口径：板块与新闻主题双向子串匹配
                    if theme in affected or affected in theme:
                        impacts.setdefault(theme, []).append(score * decay)
        # 与 signal_service._news_theme_score 同口径：50 + 35 × 均值
        return {theme: 50.0 + 35.0 * (sum(values) / len(values)) for theme, values in impacts.items()}

    # ----------------------------------------------------------------- latest

    @staticmethod
    def _latest_signals(db: Session) -> dict[int, SignalSnapshot]:
        latest: dict[int, SignalSnapshot] = {}
        for snapshot in db.scalars(select(SignalSnapshot).order_by(SignalSnapshot.as_of_time.asc())).all():
            latest[snapshot.instrument_id] = snapshot
        return latest

    @staticmethod
    def _latest_indicators(db: Session) -> dict[int, IndicatorSnapshot]:
        latest: dict[int, IndicatorSnapshot] = {}
        for snapshot in db.scalars(
            select(IndicatorSnapshot).order_by(
                IndicatorSnapshot.as_of_date.asc(), IndicatorSnapshot.generated_at.asc()
            )
        ).all():
            latest[snapshot.instrument_id] = snapshot
        return latest

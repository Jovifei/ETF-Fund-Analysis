"""Read-only ETF signal grading view (company-reference grading).

Derives colourful research labels from stored indicator/quote/forecast snapshots.
Does not mutate production signal thresholds, holdings, or orders.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.models import ForecastSnapshot, IndicatorSnapshot, Instrument, QuoteSnapshot
from app.services.kline_stabilization_service import KlineStabilizationService
from app.utils.numbers import finite_or_none

GRADE_ORDER = ("可加仓", "可入场", "可试探", "观望", "减仓")
GRADE_REASONS = {
    "可加仓": "J < 90 · 上涨放量 · MA多头排列",
    "可入场": "J < 90 · KDJ有余量 · 结构向好",
    "可试探": "J < 90 · 信号偏弱 · 结构尚可",
    "观望": "超买/偏高 · 放量滞涨 · 回调风险",
    "减仓": "KDJ死叉 · MACD将死叉 · 多重看空共振",
    "数据异常": "核心指标缺失，停止分级",
}


def _f(values: dict[str, Any], key: str) -> float | None:
    return finite_or_none(values.get(key))


def quote_percent_points_to_ratio(value: object) -> float | None:
    """Normalize QuoteSnapshot.pct_change percentage points to decimal ratio."""
    number = finite_or_none(value)
    return round(number / 100.0, 12) if number is not None else None


def classify_volume(volume_ratio: float | None, expand: float, contract: float) -> dict[str, Any]:
    if volume_ratio is None:
        return {"label": "量能未知", "kind": "unknown", "ratio": None}
    if volume_ratio >= expand:
        return {"label": "放量", "kind": "expand", "ratio": round(volume_ratio, 2)}
    if volume_ratio < contract:
        return {"label": "缩量", "kind": "contract", "ratio": round(volume_ratio, 2)}
    return {"label": "平量", "kind": "flat", "ratio": round(volume_ratio, 2)}


def classify_ma(values: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    mas = [_f(values, f"ma{w}") for w in (5, 10, 20, 30)]
    if any(item is None for item in mas):
        return {"label": "均线不足", "kind": "unknown", "arrows": [], "values_text": ""}
    m5, m10, m20, m30 = mas
    if m5 > m10 > m20 > m30:
        kind, label = "bull", "多头排列"
    elif m5 < m10 < m20 < m30:
        kind, label = "bear", "空头排列"
    else:
        kind, label = "mixed", "多空交织"
    arrows: list[dict[str, str]] = []
    for window, current in zip((5, 10, 20, 30), mas, strict=True):
        prior = _f(previous or {}, f"ma{window}")
        if prior is None:
            close = _f(values, "close")
            up = close is not None and current is not None and close >= current
        else:
            up = current >= prior
        arrows.append({"window": f"M{window}", "dir": "up" if up else "down"})
    return {
        "label": label,
        "kind": kind,
        "arrows": arrows,
        "values_text": f"MA5={m5:.2f} MA20={m20:.2f}",
    }


def classify_macd(values: dict[str, Any], previous: dict[str, Any] | None, approach: float) -> dict[str, Any]:
    dif = _f(values, "macd_dif")
    dea = _f(values, "macd_dea")
    hist = _f(values, "macd_hist")
    if dif is None or dea is None or hist is None:
        return {"label": "MACD不足", "kind": "unknown", "dif": dif, "dea": dea}
    prev_hist = _f(previous or {}, "macd_hist")
    prev_dif = _f(previous or {}, "macd_dif")
    prev_dea = _f(previous or {}, "macd_dea")
    crossed_down = (
        prev_dif is not None
        and prev_dea is not None
        and prev_dif >= prev_dea
        and dif < dea
    )
    crossed_up = (
        prev_dif is not None
        and prev_dea is not None
        and prev_dif <= prev_dea
        and dif > dea
    )
    shrinking = prev_hist is not None and 0 < hist < prev_hist
    expanding = prev_hist is not None and hist < 0 and hist > prev_hist
    if crossed_down or (hist < 0 and dif < dea and prev_hist is not None and prev_hist >= 0):
        kind, label = "death", "死叉"
    elif crossed_up or (hist > 0 and dif > dea and prev_hist is not None and prev_hist <= 0):
        kind, label = "gold", "强势金叉" if dif > 0 else "弱势金叉"
    elif hist > 0 and (shrinking or (0 < hist <= approach and dif > dea)):
        kind, label = "approach_death", "将死叉"
    elif hist < 0 and (expanding or (abs(hist) <= approach and dif < dea)):
        kind, label = "approach_gold", "将叉"
    elif hist > 0:
        kind, label = "bull_cont", "多头延续" if dif > 0 else "修复延续"
    else:
        kind, label = "bear_cont", "死叉"
    return {"label": label, "kind": kind, "dif": round(dif, 4), "dea": round(dea, 4)}


def classify_kdj(values: dict[str, Any], previous: dict[str, Any] | None, cfg: dict[str, Any]) -> dict[str, Any]:
    j = _f(values, "kdj_j")
    k = _f(values, "kdj_k")
    d = _f(values, "kdj_d")
    if j is None or k is None or d is None:
        return {"label": "KDJ不足", "kind": "unknown", "j": j, "k": k, "d": d, "note": ""}
    prev_k = _f(previous or {}, "kdj_k")
    prev_d = _f(previous or {}, "kdj_d")
    death = k < d and (prev_k is None or prev_d is None or prev_k >= prev_d)
    if death:
        kind, label, note = "death", "死叉", "空头信号 · 短线谨慎"
    elif j > float(cfg["j_overbought"]):
        kind, label, note = "overbought", "超买", "短期过热 · 回调风险"
    elif j >= float(cfg["j_high"]):
        kind, label, note = "high", "偏高", "动能偏弱 · 谨慎追高"
    elif j < float(cfg["j_low"]):
        kind, label, note = "low", "低位", "超卖 · 反弹概率升高"
    else:
        kind, label, note = "healthy", "健康", "趋势可观察 · 非指令"
    return {
        "label": label,
        "kind": kind,
        "j": round(j, 1),
        "k": round(k, 1),
        "d": round(d, 1),
        "note": note,
        "death": death,
    }


def classify_rsi(rsi: float | None, cfg: dict[str, Any]) -> dict[str, Any]:
    if rsi is None:
        return {"value": None, "label": "RSI不足"}
    overbought = float(cfg.get("rsi_overbought", 70))
    strong = float(cfg.get("rsi_strong", 50))
    oversold = float(cfg.get("rsi_oversold", 30))
    if rsi >= overbought:
        label = "超买 · 短期回调风险高"
    elif rsi >= strong:
        label = "正常偏强 · 趋势中段"
    elif rsi >= oversold:
        label = "偏弱 · 动能不足"
    else:
        label = "超卖 · 反弹概率升高"
    return {"value": round(rsi, 1), "label": label}


def classify_td(values: dict[str, Any]) -> dict[str, Any]:
    buy = values.get("td_buy_setup")
    sell = values.get("td_sell_setup")
    if buy and int(buy) > 0:
        return {"label": f"TD{int(buy)}", "kind": "buy"}
    if sell and int(sell) > 0:
        return {"label": f"TD{int(sell)}", "kind": "sell"}
    return {"label": "—", "kind": "none"}


def assign_grade(
    *,
    pct_change: float | None,
    volume: dict[str, Any],
    ma: dict[str, Any],
    macd: dict[str, Any],
    kdj: dict[str, Any],
    cfg: dict[str, Any],
) -> str:
    j = kdj.get("j")
    if j is None or ma["kind"] == "unknown" or macd["kind"] == "unknown" or volume["kind"] == "unknown":
        return "数据异常"
    rising_expand = pct_change is not None and pct_change > 0 and volume["kind"] == "expand"
    stall = volume["kind"] == "expand" and (pct_change is None or pct_change <= float(cfg["stall_return"]))
    bearish_macd = macd["kind"] in {"death", "approach_death", "bear_cont"}
    if kdj.get("death") or bearish_macd:
        return "减仓"
    if kdj["kind"] in {"overbought", "high"} or stall:
        return "观望"
    if j < float(cfg["j_add_cap"]) and rising_expand and ma["kind"] == "bull":
        return "可加仓"
    structure_ok = ma["kind"] == "bull" or macd["kind"] in {"gold", "approach_gold", "bull_cont"}
    if j < float(cfg["j_add_cap"]) and not kdj.get("death") and kdj["kind"] != "overbought" and structure_ok:
        return "可入场"
    if j < float(cfg["j_add_cap"]):
        return "可试探"
    return "观望"


def classify_row(
    values: dict[str, Any],
    *,
    pct_change: float | None,
    previous: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or {}
    volume = classify_volume(_f(values, "volume_ratio"), float(cfg.get("volume_expand", 1.15)), float(cfg.get("volume_contract", 0.90)))
    ma = classify_ma(values, previous)
    macd = classify_macd(values, previous, float(cfg.get("macd_approach_hist", 0.0008)))
    kdj = classify_kdj(values, previous, {
        "j_overbought": cfg.get("j_overbought", 100),
        "j_high": cfg.get("j_high", 90),
        "j_low": cfg.get("j_low", 20),
    })
    rsi = classify_rsi(_f(values, "rsi14"), {
        "rsi_overbought": cfg.get("rsi_overbought", 70),
        "rsi_strong": cfg.get("rsi_strong", 50),
        "rsi_oversold": cfg.get("rsi_oversold", 30),
    })
    td = classify_td(values)
    vs_yesterday = None
    if pct_change is not None:
        prev_ret = _f(previous or {}, "return_1d")
        if prev_ret is None:
            vs_yesterday = "up" if pct_change > 0 else "down" if pct_change < 0 else "flat"
        else:
            vs_yesterday = "up" if pct_change > prev_ret else "down" if pct_change < prev_ret else "flat"
    grade = assign_grade(pct_change=pct_change, volume=volume, ma=ma, macd=macd, kdj=kdj, cfg={
        "j_add_cap": cfg.get("j_add_cap", 90),
        "stall_return": cfg.get("stall_return", 0.002),
    })
    return {
        "volume": volume,
        "ma": ma,
        "macd": macd,
        "kdj": kdj,
        "rsi": rsi,
        "td": td,
        "grade": grade,
        "grade_reason": GRADE_REASONS[grade],
        "vs_yesterday": vs_yesterday,
        "return_5d": _f(values, "return_5d"),
        "return_1d": _f(values, "return_1d") if pct_change is None else pct_change,
    }


class SignalGradeService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()
        self.config = dict(self.strategy.get("signal_grade", {}))
        self.version = str(self.strategy.get("signal_grade_version", "signal-grade-v0.1.0"))
        # 行业/概念/全市场板块口径与「K线企稳分析看板」共用同一份配置，
        # 保证两个只读研究视图的板块数据完全一致。
        self.workbench_config = self._load_workbench_config()

    # ---------- 板块配置与查询 ----------

    @staticmethod
    def _load_workbench_config() -> dict[str, Any]:
        """加载 config/etf_1430_workbench.json（与 K线企稳分析看板同一份）。

        文件缺失或非法时返回空字典，调用方按"无板块数据"处理，不抛异常。
        """
        import json

        path = PROJECT_ROOT / "config" / "etf_1430_workbench.json"
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _alias(self, key: str) -> dict[str, str]:
        """读取主题→板块名 的显式映射表（去掉下划线开头的注释键）。"""
        raw = self.workbench_config.get(key) or {}
        if not isinstance(raw, dict):
            return {}
        return {k: str(v) for k, v in raw.items() if not k.startswith("_") and isinstance(v, str)}

    def _broad_market_themes(self) -> set[str]:
        """需要展示全市场宽度的宽基/指数主题（同时匹配 theme_l1 与 theme_l2）。"""
        raw = self.workbench_config.get("broad_market_themes") or []
        if not isinstance(raw, list):
            return set()
        return {str(t) for t in raw if isinstance(t, str)}

    def _sector_for(self, db: Session, instrument: Instrument) -> dict[str, Any]:
        """按标的主题解析板块涨跌家数，口径与 K线企稳分析看板一致。

        优先级：
        1. 宽基/指数主题（config.broad_market_themes）→ 全市场涨跌家数（board_type='market'）；
        2. 行业板块（board_type='industry'，theme 经 sector_alias 映射后精确命中）；
        3. 概念板块（board_type='concept'，theme 经 concept_alias 映射后精确命中）；
        4. 都没有 → up/down 为 None，note 明确说明缺少哪类数据。

        匹配一律精确，不用无关板块兜底（避免误导判断）。
        """
        broad_themes = self._broad_market_themes()
        if instrument.theme_l1 in broad_themes or instrument.theme_l2 in broad_themes:
            breadth = KlineStabilizationService._market_breadth(db)
            if breadth is not None:
                return {
                    "label": f"全市场 {breadth['up']}涨 {breadth['down']}跌",
                    "up": breadth["up"],
                    "down": breadth["down"],
                    "note": f"全市场涨跌家数 · {breadth['trade_date']} · 源 {breadth.get('source')}",
                    "sector_name": breadth.get("sector_name"),
                    "board_type": "market",
                }
            return {
                "label": "未验证 / 不可用",
                "up": None,
                "down": None,
                "note": "无全市场涨跌家数",
                "sector_name": None,
                "board_type": "market",
            }

        industry = KlineStabilizationService._sector_state(
            db, instrument, self._alias("sector_alias"), board_type="industry"
        )
        if industry.get("up") is not None:
            return {
                "label": f"{industry['sector_name']} {industry['up']}涨 {industry['down']}跌",
                "up": industry["up"],
                "down": industry["down"],
                "note": f"行业板块 · {industry['trade_date']}",
                "sector_name": industry.get("sector_name"),
                "board_type": "industry",
            }

        concept = KlineStabilizationService._sector_state(
            db, instrument, self._alias("concept_alias"), board_type="concept"
        )
        if concept.get("up") is not None:
            return {
                "label": f"{concept['sector_name']} {concept['up']}涨 {concept['down']}跌",
                "up": concept["up"],
                "down": concept["down"],
                "note": f"概念板块 · {concept['trade_date']}",
                "sector_name": concept.get("sector_name"),
                "board_type": "concept",
            }

        return {
            "label": "未验证 / 不可用",
            "up": None,
            "down": None,
            "note": "无对应行业/概念板块数据",
            "sector_name": None,
            "board_type": None,
        }

    def build(self, db: Session) -> dict[str, Any]:
        instruments = db.scalars(
            select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)
        ).all()
        latest_indicators = self._latest_indicators(db)
        previous_indicators = self._previous_indicators(db, latest_indicators)
        latest_quotes = self._latest_quotes(db)
        latest_forecasts = self._latest_horizon_forecasts(db, 1)

        classified: list[dict[str, Any]] = []
        for instrument in instruments:
            indicator = latest_indicators.get(instrument.id)
            values = dict(indicator.values_json) if indicator and indicator.values_json else {}
            quote = latest_quotes.get(instrument.id)
            pct = quote_percent_points_to_ratio(quote.pct_change) if quote else _f(values, "return_1d")
            previous = previous_indicators.get(instrument.id)
            row = classify_row(values, pct_change=pct, previous=previous, cfg=self.config)
            forecast = latest_forecasts.get(instrument.id)
            classified.append({
                "ts_code": instrument.ts_code,
                "name": instrument.name,
                "theme_l1": instrument.theme_l1,
                "theme_l2": instrument.theme_l2,
                "pct_change": pct,
                **row,
                "forecast": {
                    "expected_return": forecast.expected_return if forecast else None,
                    "confidence": forecast.confidence if forecast else None,
                    "calibration_status": forecast.calibration_status if forecast else "not_calibrated",
                    "disclaimer": "FORECAST · 非实际结果",
                },
                "quote_is_mock": self.settings.market_provider == "mock",
                "research_only": True,
                "actionable": False,
                # 板块涨跌家数：复用 K线企稳分析看板的真实板块口径
                # （全市场宽度 / 行业板块 / 概念板块）。
                # 旧实现是"池内同主题 ETF 互比"，因每主题仅 1 只 ETF 而恒为不可用。
                "sector": self._sector_for(db, instrument),
            })

        groups = {key: [row for row in classified if row["grade"] == key] for key in GRADE_ORDER}
        anomaly = [row for row in classified if row["grade"] == "数据异常"]
        counts = {key: len(items) for key, items in groups.items()}
        counts["数据异常"] = len(anomaly)
        up_count = sum(1 for row in classified if (row["pct_change"] or 0) > 0)
        down_count = sum(1 for row in classified if (row["pct_change"] or 0) < 0)
        narrative = (
            f"研究分级 {len(classified)} 只 · 涨 {up_count} / 跌 {down_count}。"
            f"可加仓 {counts['可加仓']} · 可入场 {counts['可入场']} · 可试探 {counts['可试探']} · "
            f"观望 {counts['观望']} · 减仓 {counts['减仓']} · 数据异常 {counts['数据异常']}。"
            "标签为研究提示，非操作指令，不构成下单。"
        )
        return {
            "version": self.version,
            "disclaimer": self.config.get("disclaimer", "研究提示，非操作指令"),
            "research_only": True,
            "writes_holdings": False,
            "narrative": narrative,
            "counts": counts,
            "groups": groups,
            "anomaly": anomaly,
            "rows": classified,
        }

    @staticmethod
    def _latest_indicators(db: Session) -> dict[int, IndicatorSnapshot]:
        rows = db.scalars(
            select(IndicatorSnapshot).order_by(
                IndicatorSnapshot.instrument_id,
                IndicatorSnapshot.as_of_date.desc(),
                IndicatorSnapshot.generated_at.desc(),
            )
        ).all()
        latest: dict[int, IndicatorSnapshot] = {}
        for row in rows:
            latest.setdefault(row.instrument_id, row)
        return latest

    @staticmethod
    def _previous_indicators(
        db: Session, latest: dict[int, IndicatorSnapshot]
    ) -> dict[int, dict[str, Any]]:
        previous: dict[int, dict[str, Any]] = {}
        for instrument_id, current in latest.items():
            row = db.scalar(
                select(IndicatorSnapshot)
                .where(
                    IndicatorSnapshot.instrument_id == instrument_id,
                    IndicatorSnapshot.as_of_date < current.as_of_date,
                )
                .order_by(IndicatorSnapshot.as_of_date.desc(), IndicatorSnapshot.generated_at.desc())
                .limit(1)
            )
            if row and row.values_json:
                previous[instrument_id] = dict(row.values_json)
        return previous

    @staticmethod
    def _latest_quotes(db: Session) -> dict[int, QuoteSnapshot]:
        rows = db.scalars(
            select(QuoteSnapshot).order_by(QuoteSnapshot.instrument_id, QuoteSnapshot.quote_time.desc())
        ).all()
        latest: dict[int, QuoteSnapshot] = {}
        for row in rows:
            latest.setdefault(row.instrument_id, row)
        return latest

    @staticmethod
    def _latest_horizon_forecasts(db: Session, horizon: int) -> dict[int, ForecastSnapshot]:
        rows = db.scalars(
            select(ForecastSnapshot)
            .where(ForecastSnapshot.horizon == horizon)
            .order_by(
                ForecastSnapshot.instrument_id,
                ForecastSnapshot.as_of_date.desc(),
                ForecastSnapshot.generated_at.desc(),
            )
        ).all()
        latest: dict[int, ForecastSnapshot] = {}
        for row in rows:
            latest.setdefault(row.instrument_id, row)
        return latest

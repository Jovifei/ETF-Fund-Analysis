from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.utils.numbers import clamp


@dataclass(slots=True)
class StrategyEvaluation:
    composite_score: float
    family_scores: dict[str, float]
    signals: list[dict[str, Any]]
    reasons: list[str]
    risks: list[str]


def _f(values: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = values.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _b(values: dict[str, Any], key: str) -> bool:
    return bool(values.get(key))


def _score(base: float, *deltas: tuple[bool, float]) -> float:
    value = base
    for condition, delta in deltas:
        if condition:
            value += delta
    return round(clamp(value, 0, 100), 2)


def evaluate_strategy_families(
    values: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> StrategyEvaluation:
    """Evaluate deterministic strategy families from already-computed indicators.

    The engine is deliberately rule based.  No language model is allowed to alter
    these scores.  A strategy hit is an observation label, not an execution order.
    """

    config = config or {}
    ma20 = _f(values, "ma20")
    ma60 = _f(values, "ma60")
    close = _f(values, "close")
    macd_hist = _f(values, "macd_hist")
    adx = _f(values, "adx14")
    plus_di = _f(values, "plus_di14")
    minus_di = _f(values, "minus_di14")
    rsi14 = _f(values, "rsi14", 50)
    kdj_j = _f(values, "kdj_j", 50)
    roc12 = _f(values, "roc12")
    mfi14 = _f(values, "mfi14", 50)
    cmf20 = _f(values, "cmf20")
    obv_slope = _f(values, "obv_slope_5")
    volume_ratio = _f(values, "volume_ratio")
    amount_ratio = _f(values, "amount_ratio", volume_ratio)
    box_pos20 = _f(values, "box_position_20")
    box_range20 = _f(values, "box_range_20")
    rsrs_z = _f(values, "rsrs_zscore")
    chip_distance = _f(values, "chip_distance_to_peak_pct", 999)
    chip_winner = _f(values, "chip_winner_ratio", 0.5)
    chip_concentration = _f(values, "chip_concentration_70", 999)
    rps20 = _f(values, "rps20", 50)
    rps60 = _f(values, "rps60", 50)
    rps120 = _f(values, "rps120", 50)
    wr14 = _f(values, "wr14", -50)
    td_buy = int(_f(values, "td_buy_setup"))
    td_sell = int(_f(values, "td_sell_setup"))

    trend = _score(
        50,
        (close > ma20 > ma60 > 0, 18),
        (close > ma20 > 0 and not (ma20 > ma60 > 0), 6),
        (macd_hist > 0, 8),
        (adx >= 20 and plus_di > minus_di, 12),
        (adx >= 30 and plus_di > minus_di, 5),
        (rsrs_z >= 0.7, 7),
        (close < ma20 and ma20 > 0, -12),
        (adx >= 25 and minus_di > plus_di, -16),
        (rsrs_z <= -0.7, -9),
    )
    momentum = _score(
        50,
        (50 <= rsi14 <= 70, 10),
        (0 < roc12 <= 15, 10),
        (kdj_j > 50 and kdj_j <= 95, 7),
        (55 <= mfi14 <= 80, 8),
        (rsi14 >= 78, -14),
        (kdj_j >= 110, -10),
        (roc12 < -8, -12),
    )
    volume_flow = _score(
        50,
        (volume_ratio >= 1.20, 8),
        (amount_ratio >= 1.20, 6),
        (cmf20 >= 0.05, 12),
        (mfi14 >= 55, 7),
        (obv_slope > 0.08, 10),
        (cmf20 <= -0.08, -15),
        (mfi14 <= 35, -9),
        (obv_slope < -0.08, -10),
    )
    breakout = _score(
        45,
        (_b(values, "turtle_entry_20"), 14),
        (_b(values, "turtle_entry_55"), 18),
        (0.05 <= box_range20 <= 0.25 and box_pos20 >= 0.95, 12),
        (_b(values, "volume_breakout"), 15),
        (volume_ratio >= 1.50, 6),
        (_b(values, "false_breakout_risk"), -18),
    )
    pullback = _score(
        45,
        (_b(values, "pullback_ready"), 22),
        (_b(values, "second_launch"), 20),
        (0 < _f(values, "pullback_volume_ratio", 99) <= 0.90, 10),
        (close >= ma20 > 0, 6),
        (_b(values, "pullback_support_broken"), -25),
    )
    structure = _score(
        50,
        (abs(chip_distance) <= 3.0, 10),
        (chip_winner >= 0.55, 7),
        (0 < chip_concentration <= 0.18, 8),
        (0.20 <= box_pos20 <= 0.85, 3),
        (box_pos20 >= 0.95 and volume_ratio >= 1.2, 7),
        (chip_winner >= 0.88 and rsi14 >= 75, -10),
        (chip_distance > 12, -8),
    )
    relative_strength = round(clamp((rps20 * 0.45 + rps60 * 0.35 + rps120 * 0.20), 0, 100), 2)
    reversal = _score(
        45,
        (rsi14 <= 35, 10),
        (wr14 <= -80, 8),
        (kdj_j <= 15, 8),
        (td_buy >= 7, 12),
        (cmf20 > 0, 6),
        (td_sell >= 9, -14),
        (rsi14 >= 78, -12),
    )

    family_scores = {
        "trend": trend,
        "momentum": momentum,
        "volume_flow": volume_flow,
        "breakout": breakout,
        "pullback": pullback,
        "structure": structure,
        "relative_strength": relative_strength,
        "reversal": reversal,
    }
    default_weights = {
        "trend": 0.18,
        "momentum": 0.12,
        "volume_flow": 0.16,
        "breakout": 0.16,
        "pullback": 0.10,
        "structure": 0.10,
        "relative_strength": 0.12,
        "reversal": 0.06,
    }
    weights = dict(default_weights)
    weights.update({k: float(v) for k, v in (config.get("family_weights") or {}).items() if k in weights})
    total_weight = sum(max(0.0, weight) for weight in weights.values()) or 1.0
    composite = sum(family_scores[key] * max(0.0, weights[key]) for key in weights) / total_weight

    signals: list[dict[str, Any]] = []
    reasons: list[str] = []
    risks: list[str] = []

    def hit(key: str, name: str, family: str, score: float, reason: str, direction: str = "positive") -> None:
        signals.append(
            {
                "key": key,
                "name": name,
                "family": family,
                "score": round(clamp(score, 0, 100), 2),
                "direction": direction,
                "reason": reason,
            }
        )
        (reasons if direction == "positive" else risks).append(reason)

    if close > ma20 > ma60 > 0 and adx >= 20 and plus_di > minus_di:
        hit("trend_following", "趋势跟随", "trend", trend, "均线趋势、ADX 与 DMI 同向")
    if 0.05 <= box_range20 <= 0.25 and box_pos20 >= 0.95 and volume_ratio >= 0.9:
        hit("box_breakout", "箱体突破", "breakout", breakout, "20日箱体收敛且价格逼近上沿")
    if _b(values, "turtle_entry_55") and volume_ratio >= 1.1:
        hit("turtle_breakout", "海龟55日突破", "breakout", breakout, "价格突破前55日高点并有量能确认")
    elif _b(values, "turtle_entry_20") and volume_ratio >= 1.2:
        hit("turtle_breakout_20", "海龟20日突破", "breakout", breakout, "价格突破前20日高点并放量")
    if _b(values, "volume_breakout"):
        hit("volume_breakout", "放量突破", "breakout", breakout, "价格接近/突破平台且成交量明显放大")
    if _b(values, "second_launch"):
        hit("second_launch", "缩量回踩后二次启动", "pullback", pullback, "放量点火后缩量承接并重新转强")
    elif _b(values, "pullback_ready"):
        hit("volume_pullback", "放量突破缩量承接", "pullback", pullback, "点火后回调量能收缩且关键支撑未破")
    if rps20 >= 80 and rps60 >= 75:
        hit("rps_leader", "RPS 相对强势", "relative_strength", relative_strength, "20/60日相对强度位于基金池前列")
    if rsrs_z >= 0.7:
        hit("rsrs_risk_on", "RSRS 风险偏好增强", "trend", trend, "RSRS 标准分进入偏多区间")
    elif rsrs_z <= -0.7:
        hit("rsrs_risk_off", "RSRS 风险收缩", "trend", 100 - trend, "RSRS 标准分进入偏空区间", "negative")
    if abs(chip_distance) <= 3 and chip_winner >= 0.45:
        hit("chip_support", "成交密集峰附近支撑", "structure", structure, "价格位于近120日成交密集峰近似区域")
    if chip_winner >= 0.88 and rsi14 >= 75:
        hit("chip_crowded", "获利盘近似拥挤", "structure", 100 - structure, "成交分布推算的获利盘比例偏高且动量过热，注意兑现压力", "negative")
    if cmf20 >= 0.05 and mfi14 >= 55 and obv_slope > 0:
        hit("money_flow_confirmation", "资金流确认", "volume_flow", volume_flow, "CMF、MFI 与 OBV 同向改善")
    if rsi14 <= 35 and wr14 <= -80 and td_buy >= 7:
        hit("oversold_reversal", "超跌反转观察", "reversal", reversal, "RSI/WR 超卖并伴随 TD 低位计数")
    if _b(values, "false_breakout_risk"):
        hit("false_breakout", "假突破风险", "breakout", 100 - breakout, "冲击箱体/通道上沿但量能不足或收盘回落", "negative")
    if _b(values, "pullback_support_broken"):
        hit("support_break", "回踩支撑失守", "pullback", 100 - pullback, "突破后回踩跌破点火低点/平台支撑", "negative")

    signals.sort(key=lambda item: item["score"], reverse=True)
    return StrategyEvaluation(
        composite_score=round(clamp(composite, 0, 100), 2),
        family_scores=family_scores,
        signals=signals,
        reasons=list(dict.fromkeys(reasons))[:12],
        risks=list(dict.fromkeys(risks))[:12],
    )

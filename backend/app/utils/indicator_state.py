"""单一指标状态口径（indicator-state-v1）。

这里是全系统唯一的「已落库存储值 → 展示状态」推导层：

* ``classify_*``  —— 信号分级（signal_grade_service）与各看板共用的判定原语；
* ``*_view``     —— K线看板等前端的展示形状适配器。

规则（AGENTS.md / 修复方案 §5.2）：
* 输入只允许已落库的 ``IndicatorSnapshot.values_json`` 与其上一条快照
  （``previous``），禁止任何调用方从原始日线重算 MA/MACD/KDJ/RSI；
* 振荡指标数值永远不直接换算成价格；
* 字段缺失时返回 ``kind == "unknown"`` 的不足状态，由调用方按数据不足处理。
"""
from __future__ import annotations

from typing import Any

from app.utils.numbers import finite_or_none

DEFAULT_THRESHOLDS: dict[str, Any] = {
    "j_add_cap": 90,
    "j_overbought": 100,
    "j_high": 90,
    "j_low": 20,
    "volume_expand": 1.15,
    "volume_contract": 0.9,
    "stall_return": 0.002,
    "rsi_overbought": 70,
    "rsi_strong": 50,
    "rsi_weak": 30,
    "rsi_oversold": 30,
    "macd_approach_hist": 0.0008,
}

MACD_KIND_TO_CLS = {
    "gold": "macd-gold",
    "bull_cont": "macd-bull",
    "approach_gold": "macd-repair",
    "bear_cont": "macd-bear",
    "approach_death": "macd-warn",
    "death": "macd-death",
}

KDJ_KIND_TO_CLS = {
    "overbought": "kdj-hot",
    "high": "kdj-warn",
    "death": "kdj-hot",
    "low": "kdj-low",
    "healthy": "kdj-ok",
}

VOLUME_KIND_TO_CLS = {"expand": "vol-expand", "contract": "vol-contract", "flat": "vol-flat"}


def thresholds_from_strategy(strategy: dict[str, Any] | None) -> dict[str, Any]:
    """从 strategy["signal_grade"] 读阈值；缺省回落到模块默认，口径全系统一致。"""
    merged = dict(DEFAULT_THRESHOLDS)
    block = (strategy or {}).get("signal_grade")
    if isinstance(block, dict):
        for key, value in block.items():
            if key in merged:
                merged[key] = value
    return merged


def _f(values: dict[str, Any], key: str) -> float | None:
    return finite_or_none(values.get(key))


# ---------------------------------------------------------------------------
# 判定原语（存储值 → 语义状态）。signal_grade_service 同样消费本模块。
# ---------------------------------------------------------------------------


def classify_volume(volume_ratio: float | None, expand: float, contract: float) -> dict[str, Any]:
    if volume_ratio is None:
        return {"label": "量能未知", "kind": "unknown", "ratio": None}
    if volume_ratio >= expand:
        return {"label": "放量", "kind": "expand", "ratio": round(volume_ratio, 2)}
    if volume_ratio <= contract:
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
        kind, label = "bear_cont", "空头延续"
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
    elif j >= float(cfg["j_overbought"]):
        kind, label, note = "overbought", "超买", "短期过热 · 回调风险"
    elif j >= float(cfg["j_high"]):
        kind, label, note = "high", "偏高", "动能偏弱 · 谨慎追高"
    elif j <= float(cfg["j_low"]):
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
    if rsi >= float(cfg.get("rsi_overbought", 70)):
        label = "超买 · 短期回调风险高"
    elif rsi >= float(cfg.get("rsi_strong", 50)):
        label = "正常偏强 · 趋势中段"
    elif rsi <= float(cfg.get("rsi_oversold", cfg.get("rsi_weak", 30))):
        label = "超卖 · 反弹概率升高"
    else:
        label = "偏弱 · 动能不足"
    return {"value": round(rsi, 1), "label": label}


def classify_td(values: dict[str, Any]) -> dict[str, Any]:
    buy = values.get("td_buy_setup")
    sell = values.get("td_sell_setup")
    if buy and int(buy) > 0:
        return {"label": f"TD{int(buy)}", "kind": "buy"}
    if sell and int(sell) > 0:
        return {"label": f"TD{int(sell)}", "kind": "sell"}
    return {"label": "—", "kind": "none"}


# ---------------------------------------------------------------------------
# 展示形状适配器（K线看板等前端消费的形状）。语义状态一律来自上方 classify_*。
# ---------------------------------------------------------------------------


def ma_state_view(values: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    state = classify_ma(values, previous)
    if state["kind"] == "unknown":
        return {"label": state["label"], "color": "#f39c12", "dirs": [], "vals": "", "bullish": False}
    color = {"bull": "#2ecc71", "bear": "#e74c3c"}.get(state["kind"], "#f39c12")
    dirs = [[arrow["window"], arrow["dir"]] for arrow in state["arrows"]]
    return {
        "label": state["label"],
        "color": color,
        "dirs": dirs,
        "vals": state["values_text"],
        "bullish": state["kind"] == "bull",
    }


def macd_state_view(values: dict[str, Any], previous: dict[str, Any] | None, cfg: dict[str, Any]) -> dict[str, Any]:
    state = classify_macd(values, previous, float(cfg.get("macd_approach_hist", 0.0008)))
    vals = ""
    if state.get("dif") is not None and state.get("dea") is not None:
        vals = f"DIF={state['dif']:.4g} DEA={state['dea']:.4g}"
    return {
        "label": state["label"],
        "cls": MACD_KIND_TO_CLS.get(state["kind"], "dk-vf"),
        "vals": vals,
    }


def kdj_state_view(values: dict[str, Any], previous: dict[str, Any] | None, cfg: dict[str, Any]) -> dict[str, Any]:
    state = classify_kdj(values, previous, cfg)
    if state["kind"] == "unknown":
        return {"label": state["label"], "cls": "dk-vf", "sub": "", "desc": "", "vals": ""}
    return {
        "label": f"J={state['j']:.1f}",
        "cls": KDJ_KIND_TO_CLS.get(state["kind"], "dk-tm"),
        "sub": state["label"],
        "desc": state["note"],
        "vals": f"K={state['k']:.1f} D={state['d']:.1f}",
    }


def rsi_state_view(values: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    state = classify_rsi(_f(values, "rsi14"), cfg)
    return {"val": state["value"] if state["value"] is not None else None, "desc": state["label"]}


def volume_state_view(values: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    state = classify_volume(
        _f(values, "volume_ratio"),
        float(cfg.get("volume_expand", 1.15)),
        float(cfg.get("volume_contract", 0.9)),
    )
    text = "—"
    if state["kind"] != "unknown":
        text = f"{state['label']} {state['ratio']:.2f}"
    return {"text": text, "cls": VOLUME_KIND_TO_CLS.get(state["kind"], "dk-vf")}


def td_state_view(values: dict[str, Any]) -> dict[str, Any]:
    """K线看板 TD 单元格形状；与 signal_grade.classify_td 同一判定。"""
    state = classify_td(values)
    if state["kind"] == "none":
        return {
            "label": "—",
            "direction": "none",
            "sub_label": "",
            "desc": "",
            "countdown": 0,
            "setup_length": 9,
        }
    digits = "".join(ch for ch in state["label"] if ch.isdigit())
    countdown = int(digits) if digits else 0
    direction = "sell" if state["kind"] == "sell" else "buy"
    if state["kind"] == "sell":
        sub = "上涨衰竭" if countdown >= 9 else ""
        desc = "下跌变盘节奏参考" if countdown >= 9 else "卖出 setup 计数"
    else:
        sub = "下跌衰竭" if countdown >= 9 else ""
        desc = "上涨变盘节奏参考" if countdown >= 9 else "买入 setup 计数"
    return {
        "label": state["label"],
        "direction": direction,
        "sub_label": sub,
        "desc": desc,
        "countdown": countdown,
        "setup_length": 9,
    }

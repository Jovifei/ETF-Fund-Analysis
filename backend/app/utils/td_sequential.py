from __future__ import annotations

"""TD 九转 (TD Sequential / Demark 9) 工具。

扩展 indicators._td_setup 的计数逻辑，输出目标看板风格的九转标签：
  - 顶部序列: 连续 9 根收盘价 > 4 根前收盘价 -> TD9 下跌变盘（上涨衰竭）
  - 底部序列: 连续 9 根收盘价 < 4 根前收盘价 -> TD9 上涨变盘（下跌衰竭）

与 indicators.py 的 _td_setup 共用同一比较规则（current vs 4-bars-ago），
但这里输出结构化标签而非原始计数，供 K线企稳分析看板直接渲染。
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(slots=True)
class TDSetupResult:
    """TD Setup 计算结果。

    Attributes:
        buy_count: 买入 setup 计数序列（连续收盘 < 4 根前收盘）
        sell_count: 卖出 setup 计数序列（连续收盘 > 4 根前收盘）
        countdown: 当前最新一根 K 线的计数（0-9+，9 表示变盘窗口）
        direction: "top" | "bottom" | "none" —— 最近形成的计数方向
        label: 目标看板风格标签，如 "TD9"、"8"、"3" 或 "—"
        sub_label: 变盘说明，如 "下跌变盘" / "上涨变盘" / ""
        desc: 衰竭描述，如 "上涨衰竭" / "下跌衰竭" / ""
    """

    buy_count: pd.Series
    sell_count: pd.Series
    countdown: int = 0
    direction: str = "none"
    label: str = "—"
    sub_label: str = ""
    desc: str = ""


def compute_td_setup(close: pd.Series, setup_length: int = 9) -> TDSetupResult:
    """计算 TD Sequential setup（九转计数 + 标签）。

    Args:
        close: 收盘价序列（须按时间升序）。
        setup_length: 变盘计数阈值，默认 9（Demark 标准）。

    Returns:
        TDSetupResult 结构化结果。
    """
    values = close.tolist()
    buy_counts: list[int] = []
    sell_counts: list[int] = []
    for idx, current in enumerate(values):
        if idx < 4 or pd.isna(current) or not float(current) == float(current):  # NaN 防护
            buy_counts.append(0)
            sell_counts.append(0)
            continue
        reference = values[idx - 4]
        if pd.isna(reference):
            buy_counts.append(0)
            sell_counts.append(0)
            continue
        if float(current) < float(reference):
            buy_counts.append((buy_counts[-1] if buy_counts else 0) + 1)
            sell_counts.append(0)
        elif float(current) > float(reference):
            sell_counts.append((sell_counts[-1] if sell_counts else 0) + 1)
            buy_counts.append(0)
        else:
            buy_counts.append(0)
            sell_counts.append(0)

    buy_series = pd.Series(buy_counts, index=close.index)
    sell_series = pd.Series(sell_counts, index=close.index)

    # 最新一根 K 线的计数
    latest_buy = int(buy_series.iloc[-1]) if len(buy_series) else 0
    latest_sell = int(sell_series.iloc[-1]) if len(sell_series) else 0

    # ---- 最近变盘信号（Demark setup 完成事件）----
    # 语义：TD9 是"序列中最近一次达到 >= setup_length 的位置"事件标记，
    # 与目标看板一致（如有色 TD9 下跌变盘：即使最新一根已回落，仍标记近期出现过变盘信号）。
    # 遍历全序列找 buy/sell 各自最后一次达到阈值的索引，取更近者作为当前变盘信号。
    buy_trigger_idx = -1
    sell_trigger_idx = -1
    for idx in range(len(buy_counts)):
        if buy_counts[idx] >= setup_length:
            buy_trigger_idx = idx
    for idx in range(len(sell_counts)):
        if sell_counts[idx] >= setup_length:
            sell_trigger_idx = idx

    # 比较两个触发点的新近程度，取更近的
    if sell_trigger_idx >= buy_trigger_idx and sell_trigger_idx >= 0:
        direction = "top"
        label = "TD9"
        sub_label = "下跌变盘"
        desc = "上涨衰竭"
        trigger_idx = sell_trigger_idx
    elif buy_trigger_idx >= 0:
        direction = "bottom"
        label = "TD9"
        sub_label = "上涨变盘"
        desc = "下跌衰竭"
        trigger_idx = buy_trigger_idx
    elif latest_sell > 0:
        direction = "top"
        label = str(latest_sell)
        sub_label = ""
        desc = ""
        trigger_idx = len(sell_counts) - 1
    elif latest_buy > 0:
        direction = "bottom"
        label = str(latest_buy)
        sub_label = ""
        desc = ""
        trigger_idx = len(buy_counts) - 1
    else:
        direction = "none"
        label = "—"
        sub_label = ""
        desc = ""
        trigger_idx = -1

    # 回落标记：最新一根计数比前一根下降（序列中断）时加 ↓；TD9 信号不加
    if direction in {"top", "bottom"} and trigger_idx == len(buy_counts) - 1:
        if direction == "top" and len(sell_counts) > 1 and latest_sell < sell_counts[-2]:
            label = f"{label}↓"
        elif direction == "bottom" and len(buy_counts) > 1 and latest_buy < buy_counts[-2]:
            label = f"{label}↓"

    return TDSetupResult(
        buy_count=buy_series,
        sell_count=sell_series,
        countdown=max(latest_buy, latest_sell),
        direction=direction,
        label=label,
        sub_label=sub_label,
        desc=desc,
    )


def td_setup_snapshot(frame: pd.DataFrame, setup_length: int = 9) -> dict[str, Any]:
    """从 K 线 DataFrame 计算 TD 九转快照（供看板 API 使用）。

    Args:
        frame: 含 close/trade_date 列的 DataFrame。
        setup_length: 变盘阈值。

    Returns:
        {
            "label": "TD9" | "8" | "—",
            "direction": "top" | "bottom" | "none",
            "sub_label": "下跌变盘" | "上涨变盘" | "",
            "desc": "上涨衰竭" | "下跌衰竭" | "",
            "countdown": 9,
            "setup_length": 9,
        }
    """
    if frame is None or frame.empty or "close" not in frame.columns:
        return {"label": "—", "direction": "none", "sub_label": "", "desc": "", "countdown": 0, "setup_length": setup_length}
    df = frame.copy().sort_values("trade_date") if "trade_date" in frame.columns else frame.copy()
    close = pd.to_numeric(df["close"], errors="coerce")
    result = compute_td_setup(close, setup_length)
    return {
        "label": result.label,
        "direction": result.direction,
        "sub_label": result.sub_label,
        "desc": result.desc,
        "countdown": result.countdown,
        "setup_length": setup_length,
    }

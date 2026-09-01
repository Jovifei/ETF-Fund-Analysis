from __future__ import annotations

from __future__ import annotations

"""K 线形态匹配明日预测（pattern-match next-day forecast）。

思路（与目标看板一致）：
  1. 取标的最近 N 根 K 线作为"查询窗口"（默认 10 根）。
  2. 在自身历史 K 线上滑动相同长度的窗口，用归一化价格序列（相对窗口内均值）
     计算欧氏距离，选出最相似的 K 个历史窗口。
  3. 统计这些窗口的"次日真实涨跌"，得到次日预期收益与上涨概率。
  4. 置信度 conf(0-100) = 相似窗口数量 * 方向一致性 / 距离离散度 的启发式度量。

合规约束（AGENTS.md）：
  - 输出一律标记 calibration_status="not_calibrated"，除非完成 walk-forward 校准。
  - 预测仅用于研究视图，不生成操作级信号。
"""

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(slots=True)
class PatternForecast:
    """形态匹配预测结果。"""

    horizon: int = 1
    expected_return: float | None = None
    p_up: float | None = None
    terminal_price_q50: float | None = None
    path_low_price_q50: float | None = None
    path_high_price_q50: float | None = None
    sample_count: int = 0
    confidence: float = 0.0
    calibration_status: str = "not_calibrated"
    best_distance: float | None = None
    note: str = ""


def _normalize(window: np.ndarray) -> np.ndarray:
    """窗口内价格相对均值归一化，消除绝对价格差异。"""
    mean = float(np.mean(window))
    if not np.isfinite(mean) or mean == 0:
        return window
    return (window - mean) / mean


def _distance(a: np.ndarray, b: np.ndarray) -> float:
    """归一化后欧氏距离。"""
    norm_a, norm_b = _normalize(a), _normalize(b)
    return float(np.sqrt(np.sum((norm_a - norm_b) ** 2)))


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=float), q))


def pattern_forecast(
    frame: pd.DataFrame,
    *,
    window: int = 10,
    top_k: int = 20,
    min_samples: int = 3,
    last_price: float | None = None,
    last_date: Any = None,
) -> PatternForecast:
    """对给定 K 线 DataFrame 计算 1 日形态匹配预测。

    Args:
        frame: 含 close（及可选 high/low）列的 DataFrame，按时间升序。
        window: 查询窗口长度。
        top_k: 相似窗口数量上限。
        min_samples: 最少样本数，低于则不输出预测。
        last_price: 当前最新价（用于换算目标价位），缺省取最后一根 close。
        last_date: 最新交易日（仅透传），缺省取最后一根 trade_date。

    Returns:
        PatternForecast 对象。
    """
    result = PatternForecast(calibration_status="not_calibrated")
    if frame is None or frame.empty or "close" not in frame.columns:
        result.note = "数据不足"
        return result

    df = frame.copy()
    if "trade_date" in df.columns:
        df = df.sort_values("trade_date")
    closes = pd.to_numeric(df["close"], errors="coerce").dropna().to_numpy(dtype=float)
    if len(closes) < window + min_samples + 1:
        result.note = f"历史不足 ({len(closes)} < {window + min_samples + 1})"
        return result

    # 查询窗口：最后 window 根
    query = closes[-window:]
    # 候选窗口：从第 0 根到 len-window-1（每个窗口后还有至少 1 根次日）
    candidates: list[tuple[float, float]] = []  # (distance, next_return)
    for start in range(0, len(closes) - window):
        candidate = closes[start : start + window]
        distance = _distance(query, candidate)
        next_return = float(closes[start + window] / closes[start + window - 1] - 1)
        candidates.append((distance, next_return))

    candidates.sort(key=lambda item: item[0])
    selected = candidates[:top_k]
    if len(selected) < min_samples:
        result.note = f"相似样本不足 ({len(selected)} < {min_samples})"
        return result

    next_returns = [item[1] for item in selected]
    distances = [item[0] for item in selected]

    # 距离加权：更近的窗口权重更高
    max_distance = max(distances) or 1.0
    weights = np.asarray([max(0.0, 1.0 - d / max_distance) + 0.1 for d in distances], dtype=float)
    weights = weights / weights.sum()

    expected = float(np.average(next_returns, weights=weights))
    p_up = float(np.sum((np.asarray(next_returns) > 0) * weights))

    current_price = float(last_price if last_price is not None else closes[-1])
    q50 = _percentile(next_returns, 50)
    low_q50 = _percentile(next_returns, 25)
    high_q50 = _percentile(next_returns, 75)

    # 置信度启发式：0~100
    spread = float(np.std(next_returns, ddof=1)) if len(next_returns) > 1 else 0.0
    direction_strength = abs(p_up - 0.5) * 2.0  # 0~1
    sample_factor = min(1.0, len(selected) / 20.0)
    distance_quality = max(0.0, 1.0 - float(np.mean(distances)) / (0.35 + float(np.mean(distances))))
    confidence = round(100.0 * (0.35 * sample_factor + 0.35 * direction_strength + 0.30 * distance_quality), 1)

    result.expected_return = round(expected, 6)
    result.p_up = round(p_up, 4)
    result.terminal_price_q50 = round(current_price * (1 + (q50 or 0)), 4)
    result.path_low_price_q50 = round(current_price * (1 + (low_q50 or 0)), 4)
    result.path_high_price_q50 = round(current_price * (1 + (high_q50 or 0)), 4)
    result.sample_count = len(selected)
    result.confidence = confidence
    result.best_distance = round(float(distances[0]), 6)
    result.note = "形态匹配(horizon=1), 未校准"
    return result


def pattern_forecast_snapshot(frame: pd.DataFrame, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """生成看板可用的明日预测快照。"""
    config = config or {}
    forecast = pattern_forecast(
        frame,
        window=int(config.get("window", 10)),
        top_k=int(config.get("top_k", 20)),
        min_samples=int(config.get("min_samples", 3)),
    )
    return {
        "horizon": forecast.horizon,
        "expected_return": forecast.expected_return,
        "p_up": forecast.p_up,
        "terminal_price_q50": forecast.terminal_price_q50,
        "path_low_price_q50": forecast.path_low_price_q50,
        "path_high_price_q50": forecast.path_high_price_q50,
        "sample_count": forecast.sample_count,
        "confidence": forecast.confidence,
        "calibration_status": forecast.calibration_status,
        "note": forecast.note,
    }

"""Factor dependency masks computed from RAW inputs before any imputation.

Unknown volume is not a zero-volume session. Windows contaminated by unknown
inputs yield NaN/null and do not count towards factor coverage. Price-only
features remain available. Cumulative OBV requires the entire input prefix.
"""
import numpy as np
import pandas as pd

VOLUME_FEATURES = {
    "volume_ma20": 20, "volume_ratio": 20, "volume_zscore20": 20,
    "obv": 0, "obv_slope_5": 0, "mfi14": 15, "cmf20": 20,
    "volume_breakout": 20, "false_breakout_risk": 20,
    "pullback_volume_ratio": 0, "pullback_ready": 0, "second_launch": 0,
    "pullback_support_broken": 0, "last_ignition_volume": 0,
    "vp_peak_distance": 120, "cost50_distance": 120,
    "profit_ratio_est": 120, "chip_concentration": 120,
}
AMOUNT_FEATURES = {"amount_ma20": 20, "amount_ratio": 20}

def apply_input_validity(frame, raw, config=None):
    cfg = config or {}
    ordered = raw.sort_values("trade_date").reset_index(drop=True) if "trade_date" in raw else raw.reset_index(drop=True)
    validity = {}
    for key in ("volume", "amount"):
        series = pd.to_numeric(ordered.get(key, pd.Series(np.nan, index=ordered.index)), errors="coerce")
        validity[key] = pd.Series(np.isfinite(series.to_numpy(dtype=float)) & series.ge(0).to_numpy(), index=frame.index)
        # Preserve absence at source, including when caller omitted amount.
        frame[key] = pd.Series(series.to_numpy(), index=frame.index)
    def window_mask(valid, window):
        return valid.cummin() if window == 0 else valid.rolling(window, min_periods=window).sum().eq(window)
    masks = {}
    for key, window in VOLUME_FEATURES.items():
        if key in {"mfi14", "cmf20"}:
            window = int(cfg.get("money_flow", {}).get("mfi_window" if key == "mfi14" else "cmf_window", 14 if key == "mfi14" else 20)) + (key == "mfi14")
        if key.startswith(("vp_", "cost50", "profit_ratio", "chip_concentration")):
            window = int(cfg.get("chip", {}).get("window", 120))
        masks[key] = window_mask(validity["volume"], window)
    for key, window in AMOUNT_FEATURES.items():
        masks[key] = window_mask(validity["amount"], window)
    masks["vwap20"] = window_mask(validity["volume"] & validity["amount"], 20)
    for key, mask in masks.items():
        if key in frame:
            frame[key] = frame[key].where(mask, np.nan)
    frame.attrs["input_validity"] = {key: mask.tolist() for key, mask in masks.items() if key in frame}
    return frame

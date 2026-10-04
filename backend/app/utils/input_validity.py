"""Dependency and maturity masks applied after indicator calculation.

Display helpers may use neutral warm-up placeholders (for example ADX=0 or
RSI=50), but research features must not count those placeholders as observed
indicator values. Raw missing inputs also remain missing instead of becoming a
neutral factor value.
"""
import numpy as np
import pandas as pd

INPUT_VALIDITY_POLICY = "raw-dependency-and-maturity-mask-v2"

VOLUME_FEATURES = {
    "volume_ma20": 20, "volume_ratio": 20, "volume_zscore20": 20,
    "obv": 0, "obv_slope_5": 5, "mfi14": 15, "cmf20": 20,
    "volume_breakout": 20, "false_breakout_risk": 20,
    "pullback_volume_ratio": 0, "pullback_ready": 0, "second_launch": 0,
    "pullback_support_broken": 0, "last_ignition_volume": 0,
    "bars_since_ignition": 0, "last_ignition_low": 0, "last_ignition_high": 0,
    "last_ignition_platform": 0, "pullback_support": 0,
    "vp_peak_distance": 120, "cost50_distance": 120,
    "profit_ratio_est": 120, "chip_concentration": 120,
}
AMOUNT_FEATURES = {"amount_ma20": 20, "amount_ratio": 20}


def _finite_positive(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    values = numeric.to_numpy(dtype=float)
    return pd.Series(np.isfinite(values) & (values > 0), index=numeric.index)


def _price_maturity_windows(cfg: dict) -> dict[str, int]:
    windows: dict[str, int] = {}
    for raw_window in cfg.get("rsi_windows", [6, 12, 14]):
        window = int(raw_window)
        # RSI uses close.diff(), so N directional observations require N+1 bars.
        windows[f"rsi{window}"] = window + 1

    trend = cfg.get("trend_strength", {})
    adx_window = int(trend.get("adx_window", 14))
    # DMI requires a prior bar; ADX then requires a full window of mature DX.
    windows.update({
        "plus_di14": adx_window + 1,
        "minus_di14": adx_window + 1,
        "adx14": 2 * adx_window,
        "cci20": int(trend.get("cci_window", 20)),
        "wr14": int(trend.get("wr_window", 14)),
        "wr28": int(trend.get("wr_long_window", 28)),
    })

    rsrs_cfg = cfg.get("rsrs", {})
    regression = int(rsrs_cfg.get("regression_window", 18))
    zscore = int(rsrs_cfg.get("zscore_window", 60))
    z_min = max(20, min(zscore, zscore // 2))
    z_maturity = regression + z_min - 1
    windows.update({
        "rsrs_beta": regression,
        "rsrs_r2": regression,
        "rsrs_raw": regression,
        "rsrs_zscore": z_maturity,
        "rsrs_right_skew": z_maturity,
    })
    return windows


def apply_input_validity(frame, raw, config=None):
    cfg = config or {}
    ordered = raw.sort_values("trade_date").reset_index(drop=True) if "trade_date" in raw else raw.reset_index(drop=True)

    validity: dict[str, pd.Series] = {}
    for key in ("volume", "amount"):
        series = pd.to_numeric(ordered.get(key, pd.Series(np.nan, index=ordered.index)), errors="coerce")
        validity[key] = pd.Series(
            np.isfinite(series.to_numpy(dtype=float)) & series.ge(0).to_numpy(),
            index=frame.index,
        )
        frame[key] = pd.Series(series.to_numpy(), index=frame.index)

    price_valid = pd.Series(True, index=frame.index)
    for key in ("open", "high", "low", "close"):
        source = ordered.get(key, pd.Series(np.nan, index=ordered.index))
        price_valid &= pd.Series(_finite_positive(source).to_numpy(), index=frame.index)
    validity["price"] = price_valid

    def window_mask(valid, window):
        return valid.cummin() if window == 0 else valid.rolling(window, min_periods=window).sum().eq(window)

    masks = {}
    volume_window = int(cfg.get("volume", {}).get("window", 20))
    for key, window in VOLUME_FEATURES.items():
        if key in {"volume_ma20", "volume_ratio", "volume_zscore20", "volume_breakout", "false_breakout_risk"}:
            window = volume_window
        if key in {"mfi14", "cmf20"}:
            window = int(
                cfg.get("money_flow", {}).get(
                    "mfi_window" if key == "mfi14" else "cmf_window",
                    14 if key == "mfi14" else 20,
                )
            ) + (key == "mfi14")
        if key.startswith(("vp_", "cost50", "profit_ratio", "chip_concentration")):
            window = int(cfg.get("chip", {}).get("window", 120))

        if key == "obv":
            masks[key] = window_mask(validity["volume"] & validity["price"], 0)
        elif key == "obv_slope_5":
            # Five directional observations consume six closes but five current-row volumes.
            masks[key] = window_mask(validity["price"], 6) & window_mask(validity["volume"], 5)
        elif key in {"mfi14", "cmf20"}:
            masks[key] = window_mask(validity["volume"] & validity["price"], window)
        else:
            masks[key] = window_mask(validity["volume"], window)

    for key, window in AMOUNT_FEATURES.items():
        masks[key] = window_mask(validity["amount"], volume_window)
    masks["vwap20"] = window_mask(validity["volume"] & validity["amount"] & validity["price"], 20)

    for key, window in _price_maturity_windows(cfg).items():
        masks[key] = window_mask(validity["price"], window)

    for key, mask in masks.items():
        if key in frame:
            frame[key] = frame[key].where(mask, np.nan)

    frame.attrs.pop("input_validity", None)
    frame.attrs["input_validity_policy"] = INPUT_VALIDITY_POLICY
    return frame

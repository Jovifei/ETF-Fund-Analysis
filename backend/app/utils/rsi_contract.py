from __future__ import annotations

import numpy as np
import pandas as pd


def project_rsi(series: pd.Series, window: int) -> pd.Series:
    """Project RSI with the repository's frozen Wilder-style edge semantics.

    Contract:
    - positive-only mature window -> 100
    - negative-only mature window -> 0
    - flat mature window -> 50
    - warm-up, missing, or non-finite current observation -> 50

    TA-Lib uses different warm-up/flat conventions; this helper intentionally
    preserves the project's neutral warm-up while fixing the zero-loss/zero-gain
    propagation bug across every RSI window.
    """
    period = int(window)
    if period <= 0:
        raise ValueError("rsi window must be positive")
    clean = pd.to_numeric(series, errors="coerce").astype(float).replace([np.inf, -np.inf], np.nan)
    delta = clean.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    both_zero = (avg_gain == 0) & (avg_loss == 0)
    out = out.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    out = out.mask((avg_gain == 0) & (avg_loss > 0), 0.0)
    out = out.mask(both_zero, 50.0)
    out = out.mask(clean.isna(), 50.0)
    return out.fillna(50.0)

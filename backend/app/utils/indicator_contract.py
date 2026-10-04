from __future__ import annotations

INDICATOR_DEFINITION_CONTRACT_VERSION = "indicator-definitions-v1"

# These are project definitions, not claims of byte-for-byte TA-Lib/CZSC parity.
# Changing one of these semantics requires an indicator/feature version review.
INDICATOR_DEFINITIONS = {
    "macd": {"ema_adjust": False, "histogram": "2*(dif-dea)", "histogram_scale": 2.0,
             "warmup": "ema_from_first_observation"},
    "atr": {"true_range": "max(high-low,abs(high-prev_close),abs(low-prev_close))",
            "smoothing": "ewm_alpha_1_over_window_adjust_false", "min_periods": "window"},
    "adx_dmi": {"directional_movement": "wilder_project_rule",
                "smoothing": "ewm_alpha_1_over_window_adjust_false",
                "warmup_exposure": "zero_filled_public_series"},
    "obv": {"first_value": 0.0, "rule": "cumsum(sign(close.diff)*volume)",
            "note": "starting offset is project-defined and affects percentage-slope features"},
    "kdj": {"rsv_window_min_periods": 1, "seed_k": 50.0, "seed_d": 50.0,
            "j_formula": "3*k-2*d", "j_clipped": False},
    "cmf": {"flat_bar_multiplier": 0.0, "warmup_fill": 0.0},
    "rsrs": {"regression": "ols_high_on_low", "raw": "beta*r2", "zscore_ddof": 0,
             "zscore_min_periods": "max(20,min(zscore_window,zscore_window//2))"},
    "td_setup": {"scope": "setup_only_not_full_td_sequential",
                 "comparison": "close[t] vs close[t-4]", "threshold": 9, "trading_signal": False},
}

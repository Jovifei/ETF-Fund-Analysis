"""Research-only diagnostics reusing existing deterministic feature builders."""
from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select

from app.services.factor_analysis_service import DEFAULT_FACTORS, FactorAnalysisService, factor_metric
from app.utils.horizons import aligned_research_horizons
from app.workspace.chart import number

MATRIX_FIELDS = ("return_20d", "ma_gap_5_20", "macd_norm", "kdj_j", "rsi14", "atr_pct", "volume_ratio", "amount_ratio", "obv_slope_5", "mfi14", "rsrs_zscore", "benchmark_beta_60")


def correlation_summary(panel, fields):
    sums = np.zeros((len(fields), len(fields)))
    counts = np.zeros_like(sums, dtype=int)
    # Spearman ranks are computed on each complete pair, not before dropping
    # unmatched instruments. No date/regime pooling or constant-column zeros.
    for _, group in panel.groupby("trade_date", observed=True):
        clean = group[fields].replace([np.inf, -np.inf], np.nan)
        matrix = clean.corr(method="spearman", min_periods=4).to_numpy()
        valid = np.isfinite(matrix)
        sums += np.where(valid, matrix, 0)
        counts += valid
    mean = np.divide(sums, counts, out=np.full_like(sums, np.nan), where=counts > 0)
    return [[number(value) for value in row] for row in mean], counts.tolist()


def run(db, settings, *, selected=None):
    from app.models import Instrument
    from app.providers.data_contract import history_issues
    # The shared signal engine still requires complete, current history. This
    # research-only view is narrower: exclude legacy units and invalid OHLC,
    # but allow current-contract price-only rows and expose null volume-factor
    # coverage instead of blocking all diagnostics.
    issues = history_issues(db, settings)
    blocked_reasons = {"legacy_units_unverified", "ambiguous_price_basis", "invalid_ohlc"}
    eligible_ids = {
        row.id for row in db.scalars(select(Instrument).where(Instrument.enabled.is_(True)))
        if issues.get(row.id) not in blocked_reasons
    }
    configured = settings.load_strategy().get("factor_analysis", {}).get("factors", DEFAULT_FACTORS)
    if selected and (len(selected) > 12 or set(selected) - set(configured)):
        raise ValueError("factor_selection_not_in_registry")
    service = FactorAnalysisService(settings)
    panel = service._panel(db, instrument_ids=eligible_ids)
    if panel.empty:
        return {"status": "unavailable", "reason": "insufficient_history", "metrics": [], "actionable": False}
    configured = service.strategy.get("factor_analysis", {}).get("factors", DEFAULT_FACTORS)
    names = [name for name in (selected or configured) if name in panel.columns]
    horizons = aligned_research_horizons(service.strategy)
    metrics = [factor_metric(panel, name, horizon).model_dump() for name in names for horizon in horizons]
    fields = list(names)[:12] if selected else [name for name in MATRIX_FIELDS if name in names]
    correlations, counts = correlation_summary(panel, fields)
    return {
        "diagnostics_version": "workspace-factor-v1.1-pairwise",
        "status": "diagnostic", "generated_at": datetime.now(UTC).isoformat(),
        "source_as_of": str(panel.trade_date.max()), "strategy_version": service.strategy["version"],
        "selection": list(selected or []), "missing_selected": [name for name in (selected or []) if name not in panel.columns],
        "horizons": list(horizons), "name_count": len(names), "validated_count": None,
        "metrics": metrics, "correlation_fields": fields,
        "correlations": correlations, "correlation_dates": counts,
        "correlation_method": "mean_date_local_spearman_min_4_instruments", "instruments": int(panel.ts_code.nunique()),
        "actionable": False, "qualification": "mock" if settings.market_provider == "mock" else "not_qualified",
        "price_only_instruments": sum(reason == "volume_missing_for_shared_signals" for reason in issues.values()),
        "limitations": ["诊断不是样本外验证", "相关性不代表因果或增量收益", "基线日线可见性与可成交性尚未封版", "缺量标的仅参与价格因子，量价因子覆盖率保持为空", "不会修改策略权重或启用因子"],
    }

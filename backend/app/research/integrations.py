from __future__ import annotations

import importlib.metadata
import importlib.util
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResearchIntegration:
    key: str
    import_name: str
    distribution: str
    purpose: str
    production_runtime: bool = False


INTEGRATIONS = (
    ResearchIntegration("alphalens", "alphalens", "alphalens-reloaded", "factor IC/returns/turnover cross-check"),
    ResearchIntegration("mapie", "mapie", "mapie", "conformal prediction interval cross-check"),
    ResearchIntegration("exchange_calendars", "exchange_calendars", "exchange-calendars", "XSHG session authority", True),
    ResearchIntegration("akquant", "akquant", "akquant", "independent event-driven backtest"),
    ResearchIntegration("mlforecast", "mlforecast", "mlforecast", "global multi-series forecasting"),
    ResearchIntegration("lightgbm", "lightgbm", "lightgbm", "quantile/global model candidate"),
    ResearchIntegration("catboost", "catboost", "catboost", "quantile/global model candidate"),
    ResearchIntegration("qlib", "qlib", "pyqlib", "offline experiment/model registry"),
    ResearchIntegration("riskfolio", "riskfolio", "riskfolio-lib", "portfolio risk budgeting/HRP/CVaR"),
    ResearchIntegration("rqalpha", "rqalpha", "rqalpha", "China-market second execution engine"),
)


def capability_matrix() -> list[dict]:
    rows: list[dict] = []
    for item in INTEGRATIONS:
        available = importlib.util.find_spec(item.import_name) is not None
        version = None
        if available:
            try:
                version = importlib.metadata.version(item.distribution)
            except importlib.metadata.PackageNotFoundError:
                version = "source-or-unknown"
        rows.append(
            {
                "key": item.key,
                "distribution": item.distribution,
                "available": available,
                "version": version,
                "purpose": item.purpose,
                "production_runtime": item.production_runtime,
            }
        )
    return rows

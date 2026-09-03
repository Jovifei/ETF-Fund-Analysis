from __future__ import annotations

import inspect
import json

import pytest

from app.core.config import PROJECT_ROOT, get_settings
from app.services.forecast_service import ForecastService
from app.services.validation_service import ForecastValidationService
from app.utils.feature_store import FEATURE_SCHEMA_VERSION, HORIZON_FEATURES, feature_columns_for_horizon
from app.utils.horizons import DEFAULT_RESEARCH_HORIZONS, aligned_research_horizons


def test_research_and_1430_horizons_share_one_contract():
    strategy = get_settings().load_strategy()
    workbench = json.loads(
        (PROJECT_ROOT / "config" / "etf_1430_workbench.json").read_text(encoding="utf-8")
    )

    expected = DEFAULT_RESEARCH_HORIZONS
    assert expected == (1, 3, 5, 10)
    assert aligned_research_horizons(strategy) == expected
    assert tuple(int(value) for value in workbench["forecast_horizons"]) == expected
    assert strategy["feature_schema_version"] == FEATURE_SCHEMA_VERSION
    assert strategy["forecast"]["feature_schema_version"] == FEATURE_SCHEMA_VERSION

    for horizon in expected:
        assert horizon in HORIZON_FEATURES
        assert len(feature_columns_for_horizon(horizon)) >= 12

    # 20-day support remains readable only for reproduction of older v0.7 artifacts.
    assert 20 in HORIZON_FEATURES
    assert 20 not in expected


def test_research_horizon_config_drift_fails_closed():
    strategy = {
        "forecast": {"horizons": [1, 3, 5, 10]},
        "factor_analysis": {"horizons": [1, 5, 20]},
    }
    with pytest.raises(ValueError, match="must match"):
        aligned_research_horizons(strategy)


def test_forecast_generation_and_validation_do_not_keep_legacy_1_5_20_fallbacks():
    generation_source = inspect.getsource(ForecastService.refresh_all)
    validation_source = inspect.getsource(ForecastValidationService._validate_instrument)

    assert "DEFAULT_RESEARCH_HORIZONS" in generation_source
    assert "DEFAULT_RESEARCH_HORIZONS" in validation_source
    assert "[1, 5, 20]" not in generation_source
    assert "[1, 5, 20]" not in validation_source


def test_readme_matches_current_horizon_and_migration_contracts():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "1/3/5/10 交易日" in readme
    assert "1/5/20 日终点收益" not in readme
    assert "alembic upgrade head" in readme
    assert "alembic current" in readme
    assert "alembic check" in readme

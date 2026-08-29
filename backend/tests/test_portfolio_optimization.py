"""Tests for optimize_portfolio (portfolio_optimization_service + task registration).

Covers: task exists, strategies produced, constraints respected, research-only invariant.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.portfolio_optimization_service import PortfolioOptimizationService
from app.services.task_service import TaskService


def test_optimize_portfolio_task_exists():
    assert "optimize_portfolio" in TaskService().task_names


def test_optimize_produces_three_strategies_and_report(bootstrapped, db_session):
    svc = PortfolioOptimizationService()
    result = svc.run(db_session, run_id="test-optimize")
    db_session.commit()
    if "status" in result:
        # empty case: no signal snapshots in mock bootstrap
        assert result["status"] == "empty"
        return
    assert result["instrument_count"] > 0
    assert "path" in result

    payload = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    assert payload["research_status"] == "research_only_not_production_rebalance"
    strategies = payload["strategies"]
    assert "equal_weight" in strategies
    assert "score_tilted" in strategies
    assert "risk_budget" in strategies

    # Constraints respected: no fund exceeds cap
    cap = payload["constraints"]["single_fund_target_cap"]
    for name, items in strategies.items():
        for item in items:
            assert item["weight"] <= cap + 0.001, f"{name}/{item['ts_code']}: {item['weight']} > {cap}"
        total = sum(item["weight"] for item in items)
        assert abs(total - 1.0) < 0.05, f"{name}: total weight {total} deviates from 1.0"


def test_optimize_mock_flagged(bootstrapped, db_session):
    """In mock environment, report must note contains_mock=True."""
    svc = PortfolioOptimizationService()
    result = svc.run(db_session, run_id="test-optimize-mock")
    db_session.commit()
    payload = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    assert payload["data"]["contains_mock"] is True

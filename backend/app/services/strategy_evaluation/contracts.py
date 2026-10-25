from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class StrategySpec:
    """Thin declarative specification for research strategy candidates."""

    strategy_id: str
    version: str
    family: str  # trend | momentum | volatility_management | counterfactual | benchmark
    parameters: dict[str, Any]
    required_fields: list[str]
    execution_policy: dict[str, Any]
    research_only: bool = True
    actionable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StrategyResult:
    """Thin output contract separating continuous score, trend state, and actual target weight.

    Abstain semantics: When input data is missing or lookback is insufficient,
    qualification must be set to 'abstain' and missing_reason must specify why.
    Never disguise missing data as neutral 0.0 or 50.0.
    """

    strategy_id: str
    version: str
    trade_date: str
    ts_code: str
    signal_score: float | None
    rank_percentile: float | None
    trend_state: int | None  # 1: long, 0: flat/cash, -1: short
    target_weight: float
    qualification: str  # research_candidate | abstain | disqualified
    as_of: str
    available_at: str
    missing_reason: str | None = None
    research_only: bool = True
    actionable: bool = False

    def is_abstain(self) -> bool:
        return self.qualification == "abstain"

    @classmethod
    def abstain(
        cls,
        strategy_id: str,
        version: str,
        trade_date: str,
        ts_code: str,
        reason: str,
        as_of: str,
        available_at: str,
    ) -> StrategyResult:
        return cls(
            strategy_id=strategy_id,
            version=version,
            trade_date=trade_date,
            ts_code=ts_code,
            signal_score=None,
            rank_percentile=None,
            trend_state=0,
            target_weight=0.0,
            qualification="abstain",
            missing_reason=reason,
            as_of=as_of,
            available_at=available_at,
            research_only=True,
            actionable=False,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EvaluationMetrics:
    """Two-tier evaluation metrics cleanly separating directional prediction from execution ledger."""

    strategy_id: str
    version: str
    sample_name: str
    horizon: int
    date_range: tuple[str, str]

    # Directional prediction layer (IC, hit rate)
    rank_ic: float | None
    ic_days: int
    direction_hit_rate: float | None
    hit_rate_wilson_ci: tuple[float, float] | None
    n_signals: int
    mean_fwd_long: float | None
    mean_fwd_short: float | None

    # Transaction ledger layer (T+1 execution, costs, closed trades)
    closed_trades: int
    net_win_rate: float | None
    win_rate_wilson_ci: tuple[float, float] | None
    profit_factor: float | None
    net_expectancy_bps: float | None
    annualized_net_return: float | None
    annualized_net_sharpe: float | None
    max_drawdown: float | None
    turnover_annual: float | None
    cost_bps_roundtrip: float = 20.0

    research_only: bool = True
    actionable: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

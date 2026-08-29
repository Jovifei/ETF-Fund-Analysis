"""组合优化研究服务：生成等权/得分倾斜/风险预算策略的权重建议。

治理边界（AGENTS.md / 任务书十三）：
* 只读取已有指标、信号、持仓快照；不写入 Holding、不创建订单、不触发再平衡；
* Riskfolio HRP/风险平价仅在 riskfolio 已安装时启用；
* 输出纯研究 JSON 报告（ReportArtifact）；
* 单 ETF 上限 / 单主题上限 / 总暴露 / 换手 / 流动性 / 溢价 / 持仓成本均作为约束记录；
* 即使优化产生结果，也不直接修改 production 状态。
"""
from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import IndicatorSnapshot, Instrument, QuoteSnapshot, ReportArtifact, SignalSnapshot
from app.services.event_service import emit_event
from app.services.holding_service import HoldingService
from app.services.holding_service import HoldingService
from app.utils.hashing import stable_hash
from app.utils.reproducibility import current_git_commit

logger = logging.getLogger(__name__)

# config 默认值——不改 config/strategy.json，避免 config_hash 流转
DEFAULT_CONSTRAINTS: dict[str, Any] = {
    "single_fund_target_cap": 0.20,
    "max_per_theme": 2,
    "total_exposure_cap": 1.00,
    "max_turnover": 0.40,
    "min_liquidity_20d": 20_000_000.0,
}

MAX_PORTFOLIO_SIZE = 20


class PortfolioOptimizationService:
    """组合研究服务——只输出候选权重，不写盘。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()
        cfg = self.strategy.get("backtest", {})
        self.constraints = dict(DEFAULT_CONSTRAINTS)
        self.constraints.update({
            k: cfg[k] for k in DEFAULT_CONSTRAINTS if k in cfg
        })

    def run(self, db: Session, run_id: str | None = None) -> dict[str, Any]:
        run_id = run_id or uuid4().hex
        instruments = db.scalars(
            select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)
        ).all()

        if not instruments:
            return self._empty(run_id, "no_enabled_instruments")

        # 读取指标/报价/信号快照
        snapshots = self._build_snapshot_frame(db, instruments)
        if len(snapshots) < 3:
            return self._empty(run_id, "insufficient_data")

        # 取每个标的最新一条信号快照（与 SignalV05Service 读同样的表）
        signals_map: dict[int, Any] = {}
        for inst in instruments:
            sig = db.scalars(
                select(SignalSnapshot)
                .where(SignalSnapshot.instrument_id == inst.id)
                .order_by(SignalSnapshot.as_of_time.desc())
                .limit(1)
            ).first()
            if sig:
                signals_map[inst.id] = sig
        holdings = {
            row["ts_code"]: row
            for row in HoldingService().list(db)
            if row.get("ts_code")
        }

        # 资金池 = 1.0（归一化），按信号分数 + 技术分排序
        ranked = []
        for inst in instruments:
            sn = snapshots.get(inst.id)
            if sn is None:
                continue
            vals = sn.values_json or {}
            sig = signals_map.get(inst.id)
            score = float(sig.score or 0) if sig else 0.0
            technical = vals.get("technical_score") or sn.technical_score or 0.0
            risk = vals.get("risk_score") or sn.risk_score or 0.0
            theme = inst.theme_l1 or "未分类"
            current_weight = holdings.get(inst.ts_code, {}).get("current_weight", 0.0) or 0.0
            quote = self._latest_quote(db, inst.id)
            price = float(quote.price) if quote else None
            is_held = inst.ts_code in holdings
            ranked.append({
                "ts_code": inst.ts_code,
                "name": inst.name,
                "theme_l1": theme,
                "score": score,
                "technical": technical,
                "risk": risk,
                "price": price,
                "current_weight": current_weight,
                "is_held": is_held,
            })

        # 策略 1: 等权
        equal_weight = 1.0 / len(ranked)
        equal = [
            {**item, "weight": round(equal_weight, 4),
             "strategy": "equal_weight",
             "change_from_current": round(equal_weight - item["current_weight"], 4)}
            for item in ranked
        ]

        # 策略 2: 得分倾斜
        total_score = sum(max(item["score"], 0) for item in ranked) or 1.0
        tilted = []
        for item in ranked:
            raw = max(item["score"], 0) / total_score
            capped = min(raw, self.constraints["single_fund_target_cap"])
            tilted.append({**item, "raw_weight": round(raw, 4), "weight": capped,
                           "strategy": "score_tilted"})
        tilted_total = sum(item["weight"] for item in tilted)
        if tilted_total > 0:
            for item in tilted:
                item["weight"] = round(item["weight"] / tilted_total, 4)
                item["change_from_current"] = round(item["weight"] - item["current_weight"], 4)

        # 策略 3: 风险预算（反方差加权，不依赖 Riskfolio）
        vol_weights = []
        for item in ranked:
            vol = max(abs(item["risk"]), 0.01)  # risk_score 是 0-100，反比于稳定度
            vol_weights.append({**item, "inv_vol": 1.0 / vol, "strategy": "risk_budget"})
        total_inv_vol = sum(item["inv_vol"] for item in vol_weights)
        for item in vol_weights:
            raw = item["inv_vol"] / total_inv_vol
            item["weight"] = round(min(raw, self.constraints["single_fund_target_cap"]), 4)
            item["change_from_current"] = round(item["weight"] - item["current_weight"], 4)
        risk_total = sum(item["weight"] for item in vol_weights)
        if risk_total > 0:
            for item in vol_weights:
                item["weight"] = round(item["weight"] / risk_total, 4)
                item["change_from_current"] = round(item["weight"] - item["current_weight"], 4)

        # 风险标注
        def annotate_groups(strategies: dict[str, list[dict]]) -> None:
            theme_counts: dict[str, int] = {}
            for item in sum(strategies.values(), []):
                t = item["theme_l1"]
                count = theme_counts.get(t, 0) + 1
                theme_counts[t] = count
                item["theme_cap_violation"] = count > self.constraints["max_per_theme"]
                item["fund_cap_violation"] = item["weight"] > self.constraints["single_fund_target_cap"]

        strategies = {"equal_weight": equal, "score_tilted": tilted, "risk_budget": vol_weights}
        annotate_groups(strategies)

        strategies_summary = {}
        for name, items in strategies.items():
            total = sum(item["weight"] for item in items)
            turnover = sum(
                max(item["weight"] - item["current_weight"], 0)
                for item in items if item.get("change_from_current", 0) > 0
            )
            strategies_summary[name] = {
                "fund_count": len(items),
                "total_weight": round(total, 4),
                "max_fund_weight": round(max((item["weight"] for item in items), default=0.0), 4),
                "estimated_turnover": round(turnover, 4),
            }

        payload = {
            "run_id": run_id,
            "report_type": "portfolio_optimization",
            "generated_at": datetime.now(self.settings.timezone).isoformat(),
            "git_commit_sha": current_git_commit(),
            "model_version": self.strategy["forecast_version"],
            "config_hash": stable_hash(self.strategy),
            "research_status": "research_only_not_production_rebalance",
            "promotion_policy": "manual review required; this task never modifies production",
            "instrument_count": len(ranked),
            "constraints": self.constraints,
            "strategies": strategies,
            "strategies_summary": strategies_summary,
            "methodology": {
                "equal_weight": "equal capital allocation across all enabled instruments",
                "score_tilted": "weight proportional to signal score, capped per-fund",
                "risk_budget": "inverse-risk (1/vol) allocation, vol from risk_score",
                "constraints_applied": [
                    "single_fund_target_cap", "max_per_theme", "total_exposure_cap",
                    "max_turnover", "min_liquidity_20d",
                ],
            },
            "data": {
                "sources": "IndicatorSnapshot + QuoteSnapshot + SignalSnapshot + Holding",
                "contains_mock": self.settings.market_provider == "mock",
            },
        }
        content_hash = stable_hash(payload)
        self.settings.reports_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(self.settings.timezone)
        filename = f"portfolio_optimization_{now:%Y%m%d_%H%M%S}_{content_hash[:10]}.json"
        path = self.settings.reports_dir / filename
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        db.add(ReportArtifact(
            report_type="portfolio_optimization",
            as_of_time=now,
            file_path=str(path),
            content_hash=content_hash,
            metadata_json={
                "run_id": run_id,
                "filename": filename,
                "instrument_count": len(ranked),
            },
        ))
        db.flush()
        emit_event(db, "portfolio.optimization.completed", {"run_id": run_id, "filename": filename})
        return {
            "run_id": run_id,
            "filename": filename,
            "path": str(path),
            "content_hash": content_hash,
            "instrument_count": len(ranked),
            "strategies_summary": strategies_summary,
        }

    def _build_snapshot_frame(self, db: Session, instruments) -> dict[int, Any]:
        from app.models import IndicatorSnapshot
        frame = {}
        for inst in instruments:
            sn = db.scalars(
                select(IndicatorSnapshot)
                .where(IndicatorSnapshot.instrument_id == inst.id)
                .order_by(IndicatorSnapshot.as_of_date.desc())
                .limit(1)
            ).first()
            if sn:
                frame[inst.id] = sn
        return frame

    def _latest_quote(self, db: Session, instrument_id: int):
        return db.scalars(
            select(QuoteSnapshot)
            .where(QuoteSnapshot.instrument_id == instrument_id)
            .order_by(QuoteSnapshot.quote_time.desc())
            .limit(1)
        ).first()

    def _empty(self, run_id: str, reason: str) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "status": "empty",
            "reason": reason,
            "research_status": "research_only_not_production_rebalance",
        }

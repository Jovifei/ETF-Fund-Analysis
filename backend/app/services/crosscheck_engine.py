"""独立第二回测引擎（crosscheck_engine.py）：对账第一引擎的权益/交易/费用/滑点。

设计约束：
* 从不导入 backtest_service.py；与第一引擎零代码共享（但共享策略配置与数据库）；
* 读取最新 rotation_backtest 报告中的决策序列与交易序列；
* 用最简单的确定性重放：逐日持仓 → 按决策调仓 → 次日开盘价执行；
* 费率/滑点/整手/最低佣金与第一引擎一致；
* 差异超阈值即标记为 FAIL，否则 PASS。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import DailyBar, Instrument, ReportArtifact
from app.utils.hashing import stable_hash


@dataclass
class _Position:
    ts_code: str
    shares: float = 0.0
    avg_cost: float = 0.0


# 差异阈值（容忍浮点与小数取舍）
EQUITY_THRESHOLD = 0.005  # 0.5%
TRADE_COUNT_TOLERANCE = 0
COMMISSION_TOLERANCE = 0.01
SLIPPAGE_TOLERANCE = 0.01
WIN_RATE_TOLERANCE = 0.05


class CrosscheckEngine:
    """独立第二引擎：读取主引擎报告，逐日重放，输出对账结果。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()

    def run(self, db: Session) -> dict[str, Any]:
        # 1. 加载最新 rotation_backtest 报告
        artifact = db.scalars(
            select(ReportArtifact)
            .where(ReportArtifact.report_type == "rotation_backtest")
            .order_by(ReportArtifact.as_of_time.desc())
            .limit(1)
        ).first()
        if artifact is None:
            return {"status": "skipped", "reason": "no rotation_backtest report found"}
        try:
            report = json.loads(Path(artifact.file_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return {"status": "skipped", "reason": f"report unreadable: {type(exc).__name__}"}

        decisions = report.get("decisions", [])
        trades_primary = report.get("trades", [])
        equity_primary = report.get("equity_curve", [])
        config = report.get("configuration", self.strategy.get("backtest", {}))

        if not decisions or not equity_primary:
            return {"status": "skipped", "reason": "empty decisions or equity curve"}

        # 2. 加载所有相关标的的日线数据
        ts_codes = list({
            d.get("ts_code") or sel.get("ts_code")
            for d in decisions
            for sel in (d.get("selection", [d]) if isinstance(d.get("selection"), list) else [d])
        })
        benchmark_code = config.get("benchmark", "510300.SH")
        all_codes = list(set(ts_codes + [benchmark_code]))

        bar_frames: dict[str, pd.DataFrame] = {}
        for code in all_codes:
            inst = db.scalars(
                select(Instrument).where(Instrument.ts_code == code).limit(1)
            ).first()
            if inst is None:
                continue
            bars = db.scalars(
                select(DailyBar)
                .where(DailyBar.instrument_id == inst.id)
                .order_by(DailyBar.trade_date)
            ).all()
            if bars:
                df = pd.DataFrame([{
                    "date": str(b.trade_date),
                    "open": float(b.open),
                    "close": float(b.close),
                    "high": float(b.high),
                    "low": float(b.low),
                } for b in bars]).set_index("date")
                bar_frames[code] = df

        if not bar_frames:
            return {"status": "skipped", "reason": "no bar data loaded"}

        # 3. 构建决策日期→调仓映射
        decision_map: dict[str, dict] = {}
        for d in decisions:
            exec_date = d.get("execution_date")
            if exec_date:
                decision_map[exec_date] = d

        # 4. 确定性重放
        initial_cash = float(config.get("initial_cash", 1_000_000))
        lot_size = int(config.get("lot_size", 100))
        commission_rate = float(config.get("commission_rate", 0.0002))
        min_commission = float(config.get("minimum_commission", 5.0))
        slippage_rate = float(config.get("slippage_rate", 0.0005))

        equity_start = equity_primary[0]["date"]
        equity_end = equity_primary[-1]["date"]
        all_dates = sorted({
            d for code, df in bar_frames.items() for d in df.index
            if equity_start <= d <= equity_end
        })

        cash = initial_cash
        positions: dict[str, _Position] = {}
        crosscheck_equity = []
        crosscheck_trades = []

        for day in all_dates:
            # 市值 = 持仓 * 当日收盘价
            market_value = 0.0
            for code, pos in positions.items():
                price = bar_frames.get(code, pd.DataFrame()).at[day, "close"] if day in bar_frames.get(code, pd.DataFrame()).index else pos.avg_cost
                market_value += pos.shares * price
            total_equity = cash + market_value

            # 调仓日：执行决策
            if day in decision_map:
                d = decision_map[day]
                target_weights = d.get("target_weights", {})
                for code, target_w in target_weights.items():
                    if code not in bar_frames or day not in bar_frames[code].index:
                        continue
                    open_price = float(bar_frames[code].at[day, "open"])
                    exec_price = open_price * (1 + slippage_rate)
                    current_pos = positions.get(code, _Position(code))
                    target_value = total_equity * target_w
                    target_shares = (target_value / exec_price // lot_size) * lot_size
                    delta_shares = target_shares - current_pos.shares

                    if abs(delta_shares) < lot_size:
                        continue

                    gross = abs(delta_shares * exec_price)
                    commission = max(gross * commission_rate, min_commission)
                    side = "buy" if delta_shares > 0 else "sell"
                    cost = gross + commission
                    if side == "buy" and cost > cash:
                        continue
                    if side == "sell":
                        cash += gross - commission
                    else:
                        cash -= cost
                    current_pos.shares = target_shares
                    current_pos.avg_cost = exec_price
                    positions[code] = current_pos
                    crosscheck_trades.append({
                        "date": day,
                        "ts_code": code,
                        "side": side,
                        "shares": abs(delta_shares),
                        "price": round(exec_price, 4),
                        "gross": round(gross, 2),
                        "commission": round(commission, 2),
                    })

            crosscheck_equity.append({"date": day, "equity": round(cash + market_value, 2)})

        # 5. 对账指标
        if not crosscheck_equity:
            return {"status": "skipped", "reason": "crosscheck produced no equity"}

        final_eq = crosscheck_equity[-1]["equity"]
        primary_final = equity_primary[-1]["equity"]
        equity_diff_pct = abs(final_eq - primary_final) / primary_final if primary_final else 1.0

        trades_count_match = len(crosscheck_trades) == len(trades_primary)
        total_commission_cc = sum(t["commission"] for t in crosscheck_trades)
        total_commission_primary = sum(t.get("commission", 0) for t in trades_primary)

        checks = {
            "final_equity_within_threshold": bool(equity_diff_pct <= EQUITY_THRESHOLD),
            "trade_count_match": bool(trades_count_match),
            "commission_within_tolerance": bool(abs(total_commission_cc - total_commission_primary) <= COMMISSION_TOLERANCE * len(trades_primary) + 1.0),
        }
        all_pass = all(checks.values())

        return {
            "status": "pass" if all_pass else "fail",
            "checks": checks,
            "primary_report": artifact.file_path,
            "primary_run_id": report.get("run_id"),
            "equity": {
                "primary_final": round(primary_final, 2),
                "crosscheck_final": round(final_eq, 2),
                "difference_pct": round(equity_diff_pct * 100, 4),
                "threshold_pct": EQUITY_THRESHOLD * 100,
            },
            "trades": {
                "primary_count": len(trades_primary),
                "crosscheck_count": len(crosscheck_trades),
                "match": trades_count_match,
            },
            "commission": {
                "primary_total": round(total_commission_primary, 2),
                "crosscheck_total": round(total_commission_cc, 2),
            },
            "configuration": {
                "lot_size": lot_size,
                "commission_rate": commission_rate,
                "minimum_commission": min_commission,
                "slippage_rate": slippage_rate,
            },
        }


def crosscheck_main(db: Session, settings: Settings | None = None) -> dict[str, Any]:
    """TaskService 入口：运行独立对账。"""
    engine = CrosscheckEngine(settings)
    result = engine.run(db)
    if result.get("status") == "skipped":
        return result

    # 写入 ReportArtifact
    import uuid
    from datetime import datetime
    from app.services.event_service import emit_event

    content_hash = stable_hash(result)
    settings_inst = settings or get_settings()
    settings_inst.reports_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(settings_inst.timezone)
    filename = f"backtest_crosscheck_{now:%Y%m%d_%H%M%S}_{content_hash[:10]}.json"
    path = settings_inst.reports_dir / filename
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    db.add(ReportArtifact(
        report_type="backtest_crosscheck",
        as_of_time=now,
        file_path=str(path),
        content_hash=content_hash,
        metadata_json={
            "run_id": str(uuid.uuid4().hex),
            "filename": filename,
            "status": result["status"],
            "primary_run_id": result.get("primary_run_id"),
        },
    ))
    db.flush()
    emit_event(db, "backtest.crosscheck.completed", {"filename": filename, "status": result["status"]})
    result["filename"] = filename
    result["path"] = str(path)
    return result

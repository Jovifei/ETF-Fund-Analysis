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
            .order_by(ReportArtifact.id.desc())
            .limit(1)
        ).first()
        if artifact is None:
            return {"status": "skipped", "reason": "no rotation_backtest report found"}
        try:
            report = json.loads(Path(artifact.file_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return {"status": "skipped", "reason": f"report unreadable: {type(exc).__name__}"}

        if stable_hash(report) != artifact.content_hash:
            return {"status": "skipped", "reason": "primary_report_content_hash_mismatch"}

        decisions = report.get("decisions", [])
        trades_primary = report.get("trades", [])
        equity_primary = report.get("equity_curve", [])
        config = report.get("configuration")
        if not isinstance(config, dict):
            return {"status": "skipped", "reason": "primary_configuration_missing"}

        if not decisions or not equity_primary:
            return {"status": "skipped", "reason": "empty decisions or equity curve"}

        # 2. 加载所有相关标的的日线数据。Decision.selection 是审计详情字典，
        # 不是持仓列表；真实交易标的来自 target_weights 和已执行 trades。
        ts_codes = sorted({
            str(code)
            for d in decisions
            for code in (d.get("target_weights") or {}).keys()
            if code
        } | {
            str(item.get("ts_code"))
            for item in trades_primary
            if item.get("ts_code")
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

        # 4. 确定性重放。执行口径独立实现，但必须与主引擎的
        # close_t decision -> open_t+1 execution / close_t+1 valuation 一致。
        initial_cash = float(config.get("initial_cash", 1_000_000))
        lot_size = max(1, int(config.get("lot_size", 100)))
        commission_rate = float(config.get("commission_rate", 0.0002))
        min_commission = float(config.get("minimum_commission", 5.0))
        slippage_rate = float(config.get("slippage_rate", 0.0005))

        all_dates = [str(item["date"]) for item in equity_primary]
        cash = initial_cash
        positions: dict[str, _Position] = {}
        crosscheck_equity: list[dict[str, Any]] = []
        crosscheck_trades: list[dict[str, Any]] = []

        def latest_close(code: str, day: str, *, before: bool = False) -> float | None:
            frame = bar_frames.get(code)
            if frame is None or frame.empty:
                return None
            history = frame.loc[frame.index < day if before else frame.index <= day, "close"]
            if history.empty:
                return None
            value = float(history.iloc[-1])
            return value if math.isfinite(value) and value > 0 else None

        for day in all_dates:
            open_prices: dict[str, float] = {}
            for code, frame in bar_frames.items():
                if day not in frame.index:
                    continue
                value = float(frame.at[day, "open"])
                if math.isfinite(value) and value > 0:
                    open_prices[code] = value

            open_value = 0.0
            for code, pos in positions.items():
                raw_open = open_prices.get(code)
                value = raw_open if raw_open is not None else latest_close(code, day, before=True)
                if value is not None:
                    open_value += pos.shares * value
            equity_at_open = cash + open_value

            if day in decision_map:
                target_weights = {
                    str(code): float(weight)
                    for code, weight in (decision_map[day].get("target_weights") or {}).items()
                }

                # Sell first, including positions removed from the target portfolio.
                for code in sorted(list(positions)):
                    pos = positions[code]
                    raw_open = open_prices.get(code)
                    if raw_open is None or pos.shares <= 0:
                        continue
                    target_value = equity_at_open * target_weights.get(code, 0.0)
                    current_value = pos.shares * raw_open
                    excess = max(0.0, current_value - target_value)
                    sell_shares = int(excess // (raw_open * lot_size)) * lot_size
                    if code not in target_weights:
                        sell_shares = int(pos.shares)
                    sell_shares = min(int(pos.shares), sell_shares)
                    if sell_shares <= 0:
                        continue
                    exec_price = raw_open * (1.0 - slippage_rate)
                    gross = exec_price * sell_shares
                    commission = max(gross * commission_rate, min_commission)
                    slippage_cost = (raw_open - exec_price) * sell_shares
                    cash += gross - commission
                    pos.shares -= sell_shares
                    if pos.shares <= 0:
                        del positions[code]
                    crosscheck_trades.append({
                        "date": day, "ts_code": code, "side": "sell",
                        "shares": sell_shares, "price": round(exec_price, 6),
                        "gross": round(gross, 2), "commission": round(commission, 2),
                        "slippage_cost": round(slippage_cost, 6),
                    })

                # Then buy toward the same open-equity target weights.
                for code, target_w in sorted(target_weights.items(), key=lambda item: item[1], reverse=True):
                    raw_open = open_prices.get(code)
                    if raw_open is None:
                        continue
                    pos = positions.get(code, _Position(code))
                    target_value = equity_at_open * target_w
                    current_value = pos.shares * raw_open
                    missing = max(0.0, target_value - current_value)
                    exec_price = raw_open * (1.0 + slippage_rate)
                    buy_shares = int(missing // (exec_price * lot_size)) * lot_size
                    while buy_shares > 0:
                        gross = exec_price * buy_shares
                        commission = max(gross * commission_rate, min_commission)
                        if gross + commission <= cash:
                            break
                        buy_shares -= lot_size
                    if buy_shares <= 0:
                        continue
                    gross = exec_price * buy_shares
                    commission = max(gross * commission_rate, min_commission)
                    slippage_cost = (exec_price - raw_open) * buy_shares
                    old_cost = pos.avg_cost * pos.shares
                    cash -= gross + commission
                    pos.avg_cost = (old_cost + gross + commission) / (pos.shares + buy_shares)
                    pos.shares += buy_shares
                    positions[code] = pos
                    crosscheck_trades.append({
                        "date": day, "ts_code": code, "side": "buy",
                        "shares": buy_shares, "price": round(exec_price, 6),
                        "gross": round(gross, 2), "commission": round(commission, 2),
                        "slippage_cost": round(slippage_cost, 6),
                    })

            # Revalue the POST-trade portfolio at the execution day's close.
            market_value = 0.0
            for code, pos in positions.items():
                price = latest_close(code, day)
                if price is None:
                    price = pos.avg_cost
                market_value += pos.shares * price
            crosscheck_equity.append({"date": day, "equity": round(cash + market_value, 2)})

        # 5. 对账指标
        if not crosscheck_equity:
            return {"status": "skipped", "reason": "crosscheck produced no equity"}

        primary_by_date = {str(item["date"]): float(item["equity"]) for item in equity_primary}
        curve_diffs = []
        for item in crosscheck_equity:
            primary_value = primary_by_date.get(item["date"])
            if primary_value is None or primary_value <= 0:
                continue
            curve_diffs.append(abs(float(item["equity"]) - primary_value) / primary_value)

        final_eq = float(crosscheck_equity[-1]["equity"])
        primary_final = float(equity_primary[-1]["equity"])
        equity_diff_pct = abs(final_eq - primary_final) / primary_final if primary_final else 1.0
        max_curve_diff_pct = max(curve_diffs, default=1.0)

        trades_count_match = len(crosscheck_trades) == len(trades_primary)
        total_commission_cc = sum(float(t["commission"]) for t in crosscheck_trades)
        total_commission_primary = sum(float(t.get("commission", 0)) for t in trades_primary)
        total_slippage_cc = sum(float(t.get("slippage_cost", 0)) for t in crosscheck_trades)

        total_slippage_primary = 0.0
        for trade in trades_primary:
            price = float(trade.get("price") or 0.0)
            shares = float(trade.get("shares") or 0.0)
            if price <= 0 or shares <= 0 or slippage_rate <= 0:
                continue
            if trade.get("side") == "buy":
                raw_open = price / (1.0 + slippage_rate)
                total_slippage_primary += (price - raw_open) * shares
            elif trade.get("side") == "sell":
                raw_open = price / (1.0 - slippage_rate)
                total_slippage_primary += (raw_open - price) * shares

        checks = {
            "final_equity_within_threshold": bool(equity_diff_pct <= EQUITY_THRESHOLD),
            "equity_curve_within_threshold": bool(max_curve_diff_pct <= EQUITY_THRESHOLD),
            "trade_count_match": bool(trades_count_match),
            "commission_within_tolerance": bool(
                abs(total_commission_cc - total_commission_primary)
                <= COMMISSION_TOLERANCE * len(trades_primary) + 1.0
            ),
            "slippage_within_tolerance": bool(
                abs(total_slippage_cc - total_slippage_primary)
                <= SLIPPAGE_TOLERANCE * len(trades_primary) + 1.0
            ),
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
                "max_curve_difference_pct": round(max_curve_diff_pct * 100, 4),
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
            "slippage": {
                "primary_total": round(total_slippage_primary, 2),
                "crosscheck_total": round(total_slippage_cc, 2),
            },
            "qualification": "mock_or_synthetic" if bool((report.get("data") or {}).get("contains_mock")) else "not_qualified",
            "actionable": False,
            "primary_content_hash": artifact.content_hash,
            "primary_backtest_version": report.get("backtest_version"),
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

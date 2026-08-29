"""影子运行审计：每日对比已发布预测 vs 实际走势，不修改预测，不补写历史。

治理边界：
* 只读取 ForecastSnapshot（已发布的预测）和 DailyBar（当日实际）；
* 不删除失败记录、不补写历史预测、不自动调参；
* 输出 ReportArtifact（影子审计报告）+ TaskRun result_json；
* 覆盖区间、支撑/压力触及、信号状态、模型版本、配置哈希等全部核对字段。
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import (
    DailyBar, ForecastSnapshot, IndicatorSnapshot, Instrument,
    ReportArtifact, SignalSnapshot,
)
from app.services.event_service import emit_event
from app.services.trading_calendar_service import TradingCalendarService
from app.utils.hashing import stable_hash
from app.utils.reproducibility import current_git_commit


class ShadowRunAuditService:
    """影子运行审计——只写审计报告，不改预测或信号。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()

    def run(self, db: Session, run_id: str | None = None, target_date: date | None = None) -> dict[str, Any]:
        run_id = run_id or uuid4().hex
        calendar = TradingCalendarService(self.settings)
        today = target_date or date.today()
        today_decision = calendar.decision(today)

        instruments = db.scalars(
            select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code)
        ).all()

        audits: list[dict[str, Any]] = []
        summary = {
            "total_instruments": len(instruments),
            "audited": 0,
            "forecast_available": 0,
            "actual_available": 0,
            "interval_covers_actual": 0,
            "direction_correct": 0,
            "support_touched": 0,
            "resistance_touched": 0,
        }

        for inst in instruments:
            # 取最近一条预测
            forecast = db.scalars(
                select(ForecastSnapshot)
                .where(ForecastSnapshot.instrument_id == inst.id)
                .order_by(ForecastSnapshot.as_of_date.desc(), ForecastSnapshot.horizon)
                .limit(1)
            ).first()
            if forecast is None:
                continue
            summary["forecast_available"] += 1

            # 取预测之后最近一条收盘价（实际）
            actual_bar = db.scalars(
                select(DailyBar)
                .where(DailyBar.instrument_id == inst.id, DailyBar.trade_date > forecast.as_of_date)
                .order_by(DailyBar.trade_date)
                .limit(1)
            ).first()
            if actual_bar is None:
                continue
            summary["actual_available"] += 1

            # 取信号快照（最新）
            signal = db.scalars(
                select(SignalSnapshot)
                .where(SignalSnapshot.instrument_id == inst.id)
                .order_by(SignalSnapshot.as_of_time.desc())
                .limit(1)
            ).first()

            # 计算实际收益率
            prev_close = actual_bar.pre_close or actual_bar.open
            actual_return = (actual_bar.close / prev_close - 1) if prev_close and prev_close > 0 else None

            # 区间覆盖检查（终点 q10/q90）
            terminal_q10 = forecast.q10
            terminal_q90 = forecast.q90
            interval_covers = None
            if actual_return is not None and terminal_q10 is not None and terminal_q90 is not None:
                interval_covers = bool(terminal_q10 <= actual_return <= terminal_q90)
                if interval_covers:
                    summary["interval_covers_actual"] += 1

            # 方向正确
            direction_correct = None
            if actual_return is not None and forecast.p_up is not None:
                predicted_up = forecast.p_up >= 0.5
                actual_up = actual_return > 0
                direction_correct = predicted_up == actual_up
                if direction_correct:
                    summary["direction_correct"] += 1

            # 路径触及（低点触及支撑、高点触及压力）
            support_touched = None
            resistance_touched = None
            support_level = None
            resistance_level = None
            values = {}
            indicator = db.scalars(
                select(IndicatorSnapshot)
                .where(IndicatorSnapshot.instrument_id == inst.id)
                .order_by(IndicatorSnapshot.as_of_date.desc())
                .limit(1)
            ).first()
            if indicator:
                values = indicator.values_json or {}
                support_level = values.get("boll_lower") or values.get("ma20")
                resistance_level = values.get("boll_upper")

            path_low_price = forecast.path_low_price_q50
            path_high_price = forecast.path_high_price_q50
            if actual_bar is not None and support_level and support_level > 0:
                support_touched = bool(actual_bar.low <= support_level)
                if support_touched:
                    summary["support_touched"] += 1
            if actual_bar is not None and resistance_level and resistance_level > 0:
                resistance_touched = bool(actual_bar.high >= resistance_level)
                if resistance_touched:
                    summary["resistance_touched"] += 1

            summary["audited"] += 1

            audits.append({
                "ts_code": inst.ts_code,
                "name": inst.name,
                "theme_l1": inst.theme_l1,
                "forecast_as_of_date": str(forecast.as_of_date),
                "forecast_horizon": forecast.horizon,
                "forecast_model_version": forecast.model_version,
                "forecast_config_hash": forecast.config_hash,
                "forecast_calibration_status": forecast.calibration_status,
                "forecast_p_up": round(forecast.p_up, 4) if forecast.p_up is not None else None,
                "forecast_terminal_q10": round(terminal_q10, 6) if terminal_q10 is not None else None,
                "forecast_terminal_q90": round(terminal_q90, 6) if terminal_q90 is not None else None,
                "forecast_terminal_price_q10": round(forecast.terminal_price_q10, 4) if forecast.terminal_price_q10 else None,
                "forecast_terminal_price_q90": round(forecast.terminal_price_q90, 4) if forecast.terminal_price_q90 else None,
                "forecast_path_low_q50_price": round(path_low_price, 4) if path_low_price else None,
                "forecast_path_high_q50_price": round(path_high_price, 4) if path_high_price else None,
                "forecast_corridor_position": round(forecast.corridor_position, 1) if forecast.corridor_position is not None else None,
                "forecast_support_touch_prob": round(forecast.support_touch_probability, 4) if forecast.support_touch_probability is not None else None,
                "forecast_resistance_touch_prob": round(forecast.resistance_touch_probability, 4) if forecast.resistance_touch_probability is not None else None,
                "actual_trade_date": str(actual_bar.trade_date),
                "actual_close": round(float(actual_bar.close), 4),
                "actual_return": round(actual_return, 6) if actual_return is not None else None,
                "actual_low": round(float(actual_bar.low), 4),
                "actual_high": round(float(actual_bar.high), 4),
                "interval_covers_actual": interval_covers,
                "direction_correct": direction_correct,
                "support_level": round(support_level, 4) if support_level else None,
                "resistance_level": round(resistance_level, 4) if resistance_level else None,
                "support_touched": support_touched,
                "resistance_touched": resistance_touched,
                "signal_state": signal.state if signal else None,
                "signal_score": round(float(signal.score), 2) if signal and signal.score is not None else None,
            })

        now = datetime.now(self.settings.timezone)
        payload = {
            "run_id": run_id,
            "report_type": "shadow_run_audit",
            "generated_at": now.isoformat(),
            "git_commit_sha": current_git_commit(),
            "model_version": self.strategy["forecast_version"],
            "feature_schema_version": self.strategy.get("feature_schema_version"),
            "config_hash": stable_hash(self.strategy),
            "target_date": str(today),
            "is_trade_day": today_decision.is_trade_day,
            "trade_day_source": today_decision.source,
            "research_status": "shadow_only_no_production_changes",
            "promotion_policy": ">=20 trading days shadow; never auto-modify predictions",
            "summary": summary,
            "audits": audits,
            "methodology": {
                "interval_coverage": "q10 <= actual_return <= q90",
                "direction_correct": "p_up>=0.5 matches actual>0",
                "support_touch": "actual_low <= boll_lower or ma20",
                "resistance_touch": "actual_high >= boll_upper",
            },
        }
        content_hash = stable_hash(payload)
        self.settings.reports_dir.mkdir(parents=True, exist_ok=True)
        filename = f"shadow_run_audit_{now:%Y%m%d_%H%M%S}_{content_hash[:10]}.json"
        path = self.settings.reports_dir / filename
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        db.add(ReportArtifact(
            report_type="shadow_run_audit",
            as_of_time=now,
            file_path=str(path),
            content_hash=content_hash,
            metadata_json={
                "run_id": run_id,
                "filename": filename,
                "target_date": str(today),
                "instrument_count": summary["audited"],
            },
        ))
        db.flush()
        emit_event(db, "shadow.run.audit.completed", {"run_id": run_id, "filename": filename})
        return {
            "run_id": run_id,
            "filename": filename,
            "path": str(path),
            "content_hash": content_hash,
            "target_date": str(today),
            "is_trade_day": today_decision.is_trade_day,
            "summary": summary,
        }

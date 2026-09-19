"""Persisted, provider-free ETF decision-board read model.

This service only reads confirmed domain snapshots.  It intentionally does not
fetch market data, write DailyBar, change signal grades, or claim a quote is
actionable.  Intraday observations are stored separately so a later qualified
derived-data implementation can consume them without corrupting daily history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import isfinite
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import (
    DailyBar,
    DecisionBoardProvisionalInput,
    DecisionBoardSnapshot,
    ForecastSnapshot,
    IndicatorSnapshot,
    Instrument,
    QuoteSnapshot,
    TaskRun,
)
from app.services.signal_grade_service import GRADE_ORDER, SignalGradeService, classify_row
from app.services.support_resistance_service import SupportResistanceService
from app.services.trading_calendar_service import TradingCalendarService
from app.utils.indicators_v05 import calculate_indicators
from app.utils.numbers import finite_or_none
from app.utils.support_resistance import build_support_resistance

READ_MODEL_VERSION = "decision-read-v107"
HORIZONS = (1, 3, 5, 10)
# Must match docs/INTRADAY_REFRESH_CADENCE.md and refresh_policy windows.
# Lunch 11:31–12:59 is intentionally absent.  14:50–15:00 is every 2 minutes.
SLOT_TIMES = (
    "09:30", "10:30", "11:30", "13:00", "13:30", "14:00",
    "14:30", "14:40", "14:50", "14:52", "14:54", "14:56", "14:58", "15:00",
)
_SLOT_CLOCKS = tuple(time.fromisoformat(value) for value in SLOT_TIMES)
_GRADE_RANK = {grade: index for index, grade in enumerate(GRADE_ORDER)}
_FRESHNESS_RANK = {"fresh": 0, "stale": 1, "degraded": 2, "missing": 3, "unknown": 4}
SHANGHAI = ZoneInfo("Asia/Shanghai")


class DecisionBoardRefreshBusy(RuntimeError):
    pass


@dataclass(frozen=True)
class SnapshotBuild:
    snapshot: DecisionBoardSnapshot
    payload: dict


def percent_points_to_ratio(value: object) -> float | None:
    """Convert the persisted provider contract (percentage points) deterministically."""

    number = finite_or_none(value)
    return round(number / 100.0, 12) if number is not None else None


def health_sort_key(grade: str | None, freshness: str | None) -> tuple[int, int]:
    """Display ordering only; it never participates in five-grade assignment."""

    return (_GRADE_RANK.get(str(grade), len(GRADE_ORDER)), _FRESHNESS_RANK.get(str(freshness), 4))


def semantic_sort_keys(
    *,
    volume: dict, ma: dict, macd: dict, kdj: dict, td: dict, rsi: dict,
    chan: dict, forecasts: dict[str, dict], horizon: int, today_return: float | None,
) -> dict[str, int | float | None]:
    """Primitive ascending keys; lower is the documented higher-health priority."""

    volume_kind = volume.get("kind")
    volume_bucket = 0 if volume_kind == "expand" and (today_return or 0) > 0 else 1 if volume_kind == "flat" else 2 if volume_kind == "expand" else 3 if volume_kind == "contract" else 4
    volume_direction = 0 if (today_return or 0) > 0 else 1 if (today_return or 0) == 0 else 2
    volume_ratio = finite_or_none(volume.get("ratio"))
    # bucket → direction → higher ratio first, packed as one primitive number.
    volume_key = volume_bucket * 10_000_000_000 + volume_direction * 1_000_000_000 + (1_000_000_000 - min(1_000_000_000, round((volume_ratio or 0) * 1_000_000)))
    ma_bucket = {"bull": 0, "mixed": 1, "bear": 2}.get(ma.get("kind"), 3)
    up_arrows = sum(1 for arrow in (ma.get("arrows") or ()) if isinstance(arrow, dict) and arrow.get("dir") == "up")
    ma_key = ma_bucket * 10 + (4 - min(4, up_arrows))
    macd_key = {"gold": 0, "bull_cont": 1, "approach_gold": 2, "bear_cont": 3, "approach_death": 4, "death": 5}.get(macd.get("kind"), 6)
    kdj_key = {"healthy": 0, "low": 1, "high": 2, "overbought": 3, "death": 4}.get(kdj.get("kind"), 5)
    td_kind = td.get("kind")
    td_bucket = {"none": 0, "buy": 1, "sell": 2}.get(td_kind, 3)
    td_label = str(td.get("label") or "")
    td_count = next((int(character) for character in reversed(td_label) if character.isdigit()), 0)
    # TD9 buy setup outranks lower buy counts; sell count is deterministic risk ordering.
    td_count_key = 0 if td_kind == "none" else 9 - min(9, td_count) if td_kind == "buy" else min(9, td_count)
    td_key = td_bucket * 10 + td_count_key
    rsi_value = finite_or_none(rsi.get("value"))
    rsi_key = 0 if rsi_value is not None and 50 <= rsi_value <= 70 else 1 if rsi_value is not None and rsi_value < 50 else 2 if rsi_value is not None else 3
    chan_key = {"upper_break": 0, "inside": 1, "lower_break": 2}.get(chan.get("status"), 3)
    selected = forecasts.get(str(horizon)) or {}
    expected = finite_or_none(selected.get("expected_return"))
    confidence = finite_or_none(selected.get("confidence"))
    confidence_ratio = (confidence / 100.0) if confidence is not None and confidence > 1 else confidence
    # Quantize expected return first; confidence is a tie-break only and never
    # represented as forecast accuracy.  Missing forecasts remain last.
    forecast_key = None if expected is None else -round(expected * 1_000_000) * 1_000_002 + (1_000_000 - round((confidence_ratio or 0) * 1_000_000))
    return {
        "volume": volume_key, "ma": ma_key, "macd": macd_key, "kdj": kdj_key,
        "td": td_key, "rsi": rsi_key, "chan": chan_key, "forecast": forecast_key,
        "forecast_confidence": confidence,
    }


def decision_board_due_slot(now: datetime, *, is_trade_day: bool) -> str | None:
    local = now.astimezone(SHANGHAI) if now.tzinfo is not None else now.replace(tzinfo=SHANGHAI)
    if not is_trade_day or local.weekday() >= 5:
        return None
    current = local.time().replace(tzinfo=None, second=0, microsecond=0)
    if current not in _SLOT_CLOCKS:
        return None
    return f"{local:%Y%m%d}-{current:%H%M}"


def next_decision_board_refresh(
    now: datetime,
    calendar: TradingCalendarService | None = None,
) -> datetime:
    local = now.astimezone(SHANGHAI) if now.tzinfo is not None else now.replace(tzinfo=SHANGHAI)
    calendar = calendar or TradingCalendarService()
    today = local.date()
    current = local.time().replace(tzinfo=None)
    candidate = today
    while True:
        decision = calendar.decision(candidate)
        if decision.is_trade_day:
            for slot in _SLOT_CLOCKS:
                if candidate != today or current < slot:
                    return datetime.combine(candidate, slot, tzinfo=SHANGHAI)
        candidate += timedelta(days=1)


class DecisionBoardService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.calendar = TradingCalendarService(self.settings)
        self.support_resistance = SupportResistanceService(self.settings)

    def enqueue_refresh(self, db: Session) -> dict:
        active = db.scalar(
            select(TaskRun)
            .where(
                TaskRun.task_name == "refresh_decision_board",
                TaskRun.status.in_(("queued", "running")),
            )
            .order_by(TaskRun.started_at.desc())
            .limit(1)
        )
        if active is not None:
            raise DecisionBoardRefreshBusy("decision board refresh is already active")
        run_id = uuid4().hex
        submitted_at = datetime.now(self.settings.timezone)
        db.add(
            TaskRun(
                run_id=run_id,
                task_name="refresh_decision_board",
                status="queued",
                started_at=submitted_at,
                result_json={"status": "queued", "source": "api"},
            )
        )
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise DecisionBoardRefreshBusy("decision board refresh is already active") from exc
        return {
            "task_id": run_id,
            "task_name": "refresh_decision_board",
            "status": "queued",
            "submitted_at": submitted_at.isoformat(),
            "next_slot": next_decision_board_refresh(submitted_at, self.calendar).isoformat(),
            "provider_fetch_on_queue": False,
        }

    def capture_latest_quotes(self, db: Session) -> int:
        """Copy current OHLCV observations into the isolated provisional table."""

        latest = self._latest_by_instrument(db, QuoteSnapshot, QuoteSnapshot.quote_time, QuoteSnapshot.id)
        inserted = 0
        for instrument_id, quote in latest.items():
            exists = db.scalar(
                select(DecisionBoardProvisionalInput.id).where(
                    DecisionBoardProvisionalInput.instrument_id == instrument_id,
                    DecisionBoardProvisionalInput.observed_at == quote.quote_time,
                    DecisionBoardProvisionalInput.source == quote.source,
                )
            )
            if exists is not None:
                continue
            db.add(
                DecisionBoardProvisionalInput(
                    instrument_id=instrument_id,
                    observed_at=quote.quote_time,
                    source=quote.source,
                    timestamp_verified=bool(quote.timestamp_verified),
                    open_price=quote.open,
                    high_price=quote.high,
                    low_price=quote.low,
                    last_price=quote.price,
                    volume=quote.volume,
                    amount=quote.amount,
                    pct_change_percent_points=quote.pct_change,
                )
            )
            inserted += 1
        db.flush()
        return inserted

    def record_provisional_input(
        self,
        db: Session,
        *,
        ts_code: str,
        observed_at: datetime,
        source: str,
        timestamp_verified: bool,
        open_price: float | None,
        high_price: float | None,
        low_price: float | None,
        last_price: float | None,
        volume: float | None,
        amount: float | None,
        pct_change_percent_points: float | None,
    ) -> DecisionBoardProvisionalInput:
        instrument = db.scalar(select(Instrument).where(Instrument.ts_code == ts_code.strip().upper()))
        if instrument is None:
            raise KeyError("instrument not found")
        row = DecisionBoardProvisionalInput(
            instrument_id=instrument.id,
            observed_at=observed_at,
            source=str(source)[:32],
            timestamp_verified=bool(timestamp_verified),
            open_price=finite_or_none(open_price),
            high_price=finite_or_none(high_price),
            low_price=finite_or_none(low_price),
            last_price=finite_or_none(last_price),
            volume=finite_or_none(volume),
            amount=finite_or_none(amount),
            pct_change_percent_points=finite_or_none(pct_change_percent_points),
        )
        db.add(row)
        db.flush()
        return row

    def refresh(self, db: Session, *, generated_at: datetime | None = None, demo: bool = False) -> SnapshotBuild:
        generated_at = generated_at or datetime.now(self.settings.timezone)
        if not demo:
            # 统一刷新支撑压力快照（250 根 + 真实成交额口径），payload 构建全部读快照。
            instruments = db.scalars(
                select(Instrument).where(Instrument.enabled.is_(True), Instrument.kind.in_(("ETF", "LOF")))
            ).all()
            self.support_resistance.capture_for_instruments(db, list(instruments), computed_by="scheduled")
        payload = self._build_payload(db, generated_at)
        if demo:
            ephemeral = DecisionBoardSnapshot(
                snapshot_id=payload["snapshot_id"],
                generated_at=generated_at,
                next_refresh_at=next_decision_board_refresh(generated_at, self.calendar),
                freshness=payload["freshness"],
                payload_json=payload,
            )
            return SnapshotBuild(ephemeral, payload)
        snapshot = DecisionBoardSnapshot(
            snapshot_id=payload["snapshot_id"],
            generated_at=generated_at,
            next_refresh_at=next_decision_board_refresh(generated_at, self.calendar),
            freshness=payload["freshness"],
            payload_json=payload,
        )
        db.add(snapshot)
        db.flush()
        self._prune_snapshot_dates(db)
        return SnapshotBuild(snapshot, payload)

    def read_latest(self, db: Session, *, horizon: int = 1, snapshot_id: str | None = None) -> dict | None:
        self._validate_horizon(horizon)
        snapshot = (
            db.scalar(select(DecisionBoardSnapshot).where(DecisionBoardSnapshot.snapshot_id == snapshot_id).limit(1))
            if snapshot_id is not None
            else db.scalar(select(DecisionBoardSnapshot).order_by(DecisionBoardSnapshot.generated_at.desc(), DecisionBoardSnapshot.id.desc()).limit(1))
        )
        if snapshot is None:
            return None if snapshot_id is not None else self._empty_payload(horizon)
        payload = self._select_horizon(dict(snapshot.payload_json or {}), horizon)
        from app.utils.hashing import stable_hash
        compatible = (payload.get("read_model_version") == READ_MODEL_VERSION
                      and payload.get("config_hash") == stable_hash(self.settings.load_strategy()))
        payload["read_contract"] = "version_matched" if compatible else "legacy_snapshot_requires_rebuild"
        if not compatible:
            payload["freshness"] = "stale"
            payload["data_status"] = {**payload.get("data_status", {}), "freshness": "stale"}
            payload["source_status"] = {**payload.get("source_status", {}), "freshness": "stale", "actionable": False}
            for row in payload.get("rows", []):
                row["historical_grade"] = row.get("grade")
                row.update(grade="数据异常", freshness="stale", data_status="legacy_snapshot_requires_rebuild",
                           grade_reason="旧快照与当前读取合同不一致，请通过任务重算。", actionable=False,
                           forecasts={}, forecast_scenario=[])
            payload = self._select_horizon(payload, horizon)
        return payload

    def read_instrument(self, db: Session, ts_code: str, *, horizon: int = 1, snapshot_id: str | None = None) -> dict | None:
        payload = self.read_latest(db, horizon=horizon, snapshot_id=snapshot_id)
        if payload is None:
            return None
        normalized = ts_code.strip().upper()
        row = next((row for row in payload["rows"] if row["ts_code"] == normalized), None)
        if row is None:
            return None
        detail = dict(row)
        detail["snapshot_id"] = payload["snapshot_id"]
        detail["generated_at"] = payload["generated_at"]
        detail["selected_horizon"] = horizon
        detail["sort_basis"] = row["sort_keys"]
        return detail

    @staticmethod
    def _validate_horizon(horizon: int) -> None:
        if horizon not in HORIZONS:
            raise ValueError("horizon must be one of 1, 3, 5, 10")

    def _prune_snapshot_dates(self, db: Session) -> None:
        """Retain every snapshot on the latest 20 actual trading dates only."""

        snapshots = db.execute(
            select(DecisionBoardSnapshot.id, DecisionBoardSnapshot.generated_at).order_by(
                DecisionBoardSnapshot.generated_at.desc(), DecisionBoardSnapshot.id.desc()
            ).execution_options(yield_per=256)
        )
        kept_dates: list[date] = []
        stale_ids: list[int] = []
        for snapshot in snapshots:
            generated = snapshot.generated_at
            local_date = (
                generated.astimezone(SHANGHAI) if generated.tzinfo else generated.replace(tzinfo=SHANGHAI)
            ).date()
            trade_date = (
                self.calendar.effective_trade_date(local_date)
                if hasattr(self.calendar, "effective_trade_date")
                else local_date
            )
            if trade_date not in kept_dates and len(kept_dates) < 20:
                kept_dates.append(trade_date)
            elif trade_date not in kept_dates:
                stale_ids.append(snapshot.id)
        if stale_ids:
            for start in range(0, len(stale_ids), 500):
                db.execute(delete(DecisionBoardSnapshot).where(DecisionBoardSnapshot.id.in_(stale_ids[start:start+500])))
            db.flush()

    def _build_payload(self, db: Session, generated_at: datetime) -> dict:
        grade_payload = SignalGradeService(self.settings).build(db)
        grades = {row["ts_code"]: row for row in grade_payload["rows"]}
        instruments = db.scalars(
            select(Instrument)
            .where(Instrument.enabled.is_(True), Instrument.kind.in_(("ETF", "LOF")))
            .order_by(Instrument.ts_code)
        ).all()
        indicators = self._latest_by_instrument(db, IndicatorSnapshot, IndicatorSnapshot.as_of_date, IndicatorSnapshot.generated_at)
        previous_indicators = self._previous_indicator_values(db, indicators)
        quotes = self._latest_by_instrument(db, QuoteSnapshot, QuoteSnapshot.quote_time, QuoteSnapshot.id)
        forecasts = self._latest_forecasts(db)
        provisional = self._latest_provisional(db)
        rows = [
            self._row(db, generated_at, instrument, grades.get(instrument.ts_code), indicators.get(instrument.id), previous_indicators.get(instrument.id), quotes.get(instrument.id), forecasts.get(instrument.id, {}), provisional.get(instrument.id))
            for instrument in instruments
        ]
        from app.utils.decision_reference import entry_exit_reference, theme_relative_ranks
        ranks = theme_relative_ranks(rows)
        for row in rows:
            row["entry_exit_ref"] = entry_exit_reference(row.get("support_resistance"))
            row["theme_relative_strength"] = ranks.get(row["ts_code"]) or {
                "theme_l1": row.get("theme_l1"),
                "peer_count": 0,
                "rank": None,
                "return_5d": row.get("return_5d"),
                "label": "主题相对强弱不足",
                "basis": "confirmed_5d_return_inside_theme_not_a_second_grade",
                "research_only": True,
                "actionable": False,
            }
        rows.sort(key=lambda row: (*health_sort_key(row["grade"], row["freshness"]), row["ts_code"]))
        groups = {grade: [row for row in rows if row["grade"] == grade] for grade in GRADE_ORDER}
        groups["数据异常"] = [row for row in rows if row["grade"] == "数据异常"]
        counts = {grade: len(group) for grade, group in groups.items()}
        if sum(counts.values()) != len(rows):
            raise ValueError("decision_groups_do_not_partition_rows")
        freshness = "fresh" if rows and all(row["freshness"] == "fresh" for row in rows) else "stale" if rows else "missing"
        status_counts = {status: sum(row["data_status"] == status for row in rows) for status in sorted({row["data_status"] for row in rows})}
        from app.services.settlement import settled_session
        from app.utils.hashing import stable_hash
        return {
            "read_model_version": READ_MODEL_VERSION,
            "config_hash": stable_hash(self.settings.load_strategy()),
            "target_trade_date": settled_session(self.settings, generated_at).isoformat(),
            "snapshot_id": uuid4().hex,
            "generated_at": generated_at.isoformat(),
            "next_refresh_at": next_decision_board_refresh(generated_at, self.calendar).isoformat(),
            "selected_forecast_horizon": 1,
            "selected_horizon": 1,
            "forecast_horizons": list(HORIZONS),
            "horizons": list(HORIZONS),
            "freshness": freshness,
            "data_status": {"freshness": freshness, "row_status_counts": status_counts},
            "source_status": {
                "basis": "persisted_confirmed_snapshots",
                "freshness": freshness,
                "actionable": False,
                "research_only": True,
                "source_time_verified": False,
            },
            "indicator_basis": {
                "daily_history": "confirmed_daily_bars_only",
                "td": "TD9 setup only; TD13 not implemented",
                "chan": "overlap-zone approximation only; not full Chan/CZSC",
            },
            "indicator_status": {
                "basis": "confirmed_daily_history_plus_explicit_provisional_state",
                "forecast_basis": "persisted_settled_daily_snapshots",
                "intraday_forecast_policy": "disabled_until_time_matched_intraday_history",
                "td": "TD9 setup only; TD13 not implemented",
                "chan": "overlap-zone approximation only; not full Chan/CZSC",
            },
            "groups": groups,
            "counts": counts,
            "rows": rows,
            "research_only": True,
            "automatic_orders": False,
        }

    def _row(self, db: Session, generated_at: datetime, instrument, grade_row, indicator, previous_values, quote, forecasts, provisional) -> dict:
        grade_row = grade_row or {}
        independent_sector = grade_row.get("sector")
        comparison_basis = "previous_saved_confirmed_date_not_intraday_quote"
        from app.providers.data_contract import history_issues, trailing_unverified_history
        from app.providers.corporate_action_contract import research_history_rows
        blocked = history_issues(db, self.settings, [instrument.id]).get(instrument.id)
        history_rows = db.scalars(
            select(DailyBar).where(DailyBar.instrument_id == instrument.id).order_by(DailyBar.trade_date)
        ).all()
        research_history = research_history_rows(history_rows, instrument.ts_code)
        stale_history = trailing_unverified_history(research_history) if blocked else None
        from app.services.settlement import settled_session
        from app.services.snapshot_contract import snapshot_issues
        expected_date = None if self.settings.market_provider == "mock" else settled_session(self.settings, generated_at)
        indicator_issues = snapshot_issues(indicator, self.settings, expected_date, kind="indicator")
        qualified_through = stale_history["qualified_through"] if stale_history else None
        if stale_history and indicator is not None:
            if indicator.as_of_date <= qualified_through:
                indicator_issues = [issue for issue in indicator_issues if issue != "indicator_date_mismatch"]
            else:
                indicator_issues.append("indicator_date_after_qualified_history")
        forecast_issues = {str(h): snapshot_issues(value, self.settings, expected_date, kind="forecast")
                           for h, value in forecasts.items()}
        if stale_history:
            forecast_issues = {
                horizon: (
                    [issue for issue in issues if issue != "forecast_date_mismatch"]
                    if forecasts.get(int(horizon)) is not None
                    and forecasts[int(horizon)].as_of_date <= qualified_through
                    else [*issues, "forecast_date_after_qualified_history"]
                    if stale_history and forecasts.get(int(horizon)) is not None
                    and forecasts[int(horizon)].as_of_date > qualified_through
                    else issues
                )
                for horizon, issues in forecast_issues.items()
            }
        forecasts = {h: value for h, value in forecasts.items() if not forecast_issues[str(h)]}
        if indicator_issues:
            indicator = None
        display_history = None
        if (blocked and stale_history is None) or indicator is None:
            from app.workspace.read_model import chart_data
            display_history = chart_data(db, self.settings, instrument.ts_code, "1d", 60)
            indicator = None
            if blocked:
                forecasts = {}
            bars = (display_history or {}).get("bars") or []
            price_values = dict(bars[-1]["indicators"]) if bars else {}
            # Current/previous must come from one series and one formula/price basis.
            previous_values = ({**dict(bars[-2]["indicators"]), "_as_of_date": bars[-2]["date"]}
                               if len(bars) >= 2 else None)
            comparison_basis = "adjacent_historical_bars_display_only"
            grade_row = classify_row(price_values, pct_change=None, previous=None,
                                     cfg=SignalGradeService(self.settings).config)
            if independent_sector is not None:
                grade_row["sector"] = independent_sector
            grade_row.update(grade="数据异常", grade_reason="历史价格展示；完整量价/指标资格尚未通过，不生成当前动作")
        elif stale_history:
            qualified_through = stale_history["qualified_through"].isoformat()
            grade_row["grade_reason"] = (
                f"{grade_row.get('grade_reason', '基于历史快照')}；最后合格历史至 {qualified_through}，"
                "当前行情源未通过量额/连续性门禁"
            )
        values = dict(indicator.values_json or {}) if indicator is not None else (price_values if display_history else {})
        freshness, data_status = self._status(indicator, quote, generated_at)
        if stale_history and indicator is not None:
            freshness, data_status = "stale", "historical_price_only_stale"
        source_verified = bool(quote and quote.timestamp_verified and quote.is_realtime and not quote.degraded_reason)
        quote_source = quote.source if quote is not None else None
        quote_is_mock = self.settings.market_provider == "mock" or "mock" in str(quote_source or "").lower()
        # Missing settled indicators do not erase independently timestamped
        # intraday research input. Incompatible history still fails closed.
        provisional_status = ({"status": "blocked_history_contract",
            "used_for_derived_values": False, "reason": blocked}
            if blocked else self._provisional_status(db, instrument.id, provisional, generated_at))
        forecast_map = {str(horizon): self._forecast_payload(forecasts.get(horizon)) for horizon in HORIZONS}
        from app.services.return_observation import observed_returns
        return_context = observed_returns(db, self.settings, instrument.id, quote, generated_at)
        today_return = return_context["value"]
        previous_confirmed_return = return_context["previous_return"]
        if provisional_status["used_for_derived_values"]:
            derived = provisional_status["derived"]
            values = dict(derived["indicator_values"])
            from types import SimpleNamespace
            return_context = observed_returns(db, self.settings, instrument.id,
                SimpleNamespace(quote_time=provisional.observed_at, pct_change=provisional.pct_change_percent_points,
                                degraded_reason=None), generated_at)
            return_context["basis"] = "provisional_research_observation"
            today_return = percent_points_to_ratio(provisional.pct_change_percent_points)
            previous_confirmed_return = return_context["previous_return"]
            grade_row = {
                **grade_row,
                **classify_row(
                    values,
                    pct_change=today_return,
                    previous=previous_values,
                    cfg=SignalGradeService(self.settings).config,
                ),
            }
            freshness, data_status = "stale", "provisional_unverified_research_only" if not provisional.timestamp_verified else "provisional_research_only"
        history, confirmed_levels = self._history_and_levels(db, instrument.id)
        if stale_history:
            confirmed_levels = {}
        if display_history:
            history = [{**bar, "is_forecast": False} for bar in display_history.get("bars", [])]
            confirmed_levels = {}
            if not provisional_status["used_for_derived_values"]:
                freshness, data_status = "stale", "historical_price_only"
        if provisional_status["used_for_derived_values"]:
            history = [
                *history,
                {
                    "date": provisional.observed_at.date().isoformat(),
                    "open": provisional.open_price,
                    "high": provisional.high_price,
                    "low": provisional.low_price,
                    "close": provisional.last_price,
                    "volume": provisional.volume,
                    "is_forecast": False,
                    "is_provisional": True,
                    "timestamp_verified": bool(provisional.timestamp_verified),
                },
            ]
        support_resistance = provisional_status.get("derived", {}).get("support_resistance", confirmed_levels)
        scenario = self._forecast_scenario(history, forecast_map)
        def metric(value, fallback):
            return value if isinstance(value, dict) and value.get("label") else fallback
        volume = metric(grade_row.get("volume"), {"label": "量能不足", "kind": "unknown", "status": "missing"})
        ma = metric(grade_row.get("ma"), {"label": "均线不足", "kind": "unknown", "status": "missing"})
        macd = metric(grade_row.get("macd"), {"label": "MACD不足", "kind": "unknown", "status": "missing"})
        kdj = metric(grade_row.get("kdj"), {"label": "KDJ不足", "kind": "unknown", "status": "missing"})
        td = metric(grade_row.get("td"), {"label": "TD9不足", "kind": "unknown", "status": "missing"})
        rsi = metric(grade_row.get("rsi"), {"label": "RSI不足", "value": None, "status": "missing"})
        current_price = finite_or_none((support_resistance or {}).get("current_price"))
        support = finite_or_none(((support_resistance or {}).get("nearest_support") or {}).get("price"))
        resistance = finite_or_none(((support_resistance or {}).get("nearest_resistance") or {}).get("price"))
        chan_status = "upper_break" if current_price is not None and resistance is not None and current_price >= resistance else "lower_break" if current_price is not None and support is not None and current_price <= support else "inside" if current_price is not None else "missing"
        chan = {
            "label": "缠论近似",
            "status": chan_status,
            "detail": "重叠区近似，不是完整 Chan/CZSC",
            "zone": support_resistance.get("chan_zone_approx") if isinstance(support_resistance, dict) else None,
        }
        return {
            "instrument_id": instrument.id,
            "ts_code": instrument.ts_code,
            "name": instrument.name,
            "kind": instrument.kind,
            "theme_l1": instrument.theme_l1,
            "theme_l2": instrument.theme_l2,
            "grade": grade_row.get("grade", "数据异常"),
            "grade_reason": grade_row.get("grade_reason", "核心指标缺失，停止分级"),
            "display_sort_key": list(health_sort_key(grade_row.get("grade"), freshness)),
            "sort_keys": {
                "grade_health": health_sort_key(grade_row.get("grade"), freshness)[0] * 10 + health_sort_key(grade_row.get("grade"), freshness)[1],
                "display_only": True,
                **semantic_sort_keys(volume=volume, ma=ma, macd=macd, kdj=kdj, td=td, rsi=rsi, chan=chan, forecasts=forecast_map, horizon=1, today_return=today_return),
            },
            "freshness": freshness,
            "data_status": data_status,
            "return_1d": today_return,
            "return_5d": finite_or_none(values.get("return_5d")),
            "returns": {
                "today": today_return,
                "as_of_date": return_context["as_of_date"],
                "basis": return_context["basis"],
                "target_trade_date": return_context["target_trade_date"],
                "previous_as_of_date": return_context["previous_as_of_date"],
                "previous_confirmed_return": previous_confirmed_return,
                "previous_day_delta": (
                    round(today_return - previous_return, 12)
                    if (
                        today_return is not None
                        and (previous_return := previous_confirmed_return) is not None
                    )
                    else None
                ),
                "week_1": finite_or_none(values.get("return_5d")),
                "unit": "decimal_ratio",
                "no_unit_guessing": True,
            },
            "return_semantics": {
                "unit": "decimal_ratio",
                "quote_source_unit": "percentage_points",
                "indicator_source_unit": "decimal_ratio",
                "no_unit_guessing": True,
            },
            "forecast": forecast_map["1"],
            "forecasts": forecast_map,
            "volume": volume,
            "ma": ma,
            "macd": macd,
            "kdj": kdj,
            "td": td,
            "rsi": rsi,
            "chan": chan,
            "sector": metric(grade_row.get("sector"), {"label": "未验证 / 不可用", "status": "missing", "coverage_count": 0}),
            "snapshot_issues": {"indicator": indicator_issues, "forecasts": forecast_issues},
            "indicator_comparison": {
                "as_of_date": indicator.as_of_date.isoformat() if indicator is not None else (display_history or {}).get("source_as_of"),
                "previous_as_of_date": (previous_values or {}).get("_as_of_date"),
                "basis": comparison_basis,
                "values": {key: {"current": finite_or_none(values.get(key)), "previous": finite_or_none((previous_values or {}).get(key))}
                           for key in ("volume_ratio", "ma20", "macd_dif", "kdj_j", "rsi14", "td_buy_setup", "td_sell_setup")},
            },
            "indicator": {
                "version": indicator.version if indicator is not None else None,
                "as_of_date": indicator.as_of_date.isoformat() if indicator is not None else (display_history or {}).get("source_as_of"),
                "display_basis": "historical_price_only" if display_history else "persisted_snapshot",
                "data_quality": indicator.data_quality if indicator is not None else None,
                "td_label": (grade_row.get("td") or {}).get("label", "—"),
                "td_basis": "TD9 setup only; TD13 not implemented",
                "chan_basis": "approximation only; no full Chan/CZSC",
            },
            "quote": {
                "source": quote_source,
                "source_time": quote.quote_time.isoformat() if quote is not None else None,
                "timestamp_verified": bool(quote.timestamp_verified) if quote is not None else False,
                "is_realtime": source_verified,
                "is_mock": quote_is_mock,
                "status": "mock" if quote_is_mock else ("missing" if quote is None else freshness),
                "actionable": False,
            },
            "provisional": provisional_status,
            "history": history,
            "forecast_scenario": scenario,
            "support_resistance": support_resistance,
            "research_only": True,
            "actionable": False,
        }

    @staticmethod
    def _status(indicator, quote, generated_at: datetime) -> tuple[str, str]:
        if indicator is None:
            return "missing", "indicator_missing"
        if quote is None:
            return "stale", "quote_missing_using_confirmed_history"
        quote_time = quote.quote_time
        if quote_time is None or str(quote.degraded_reason or "").startswith("source_timestamp_missing"):
            return "stale", "quote_source_time_missing"
        quote_time = quote_time.astimezone(SHANGHAI) if quote_time.tzinfo else quote_time.replace(tzinfo=SHANGHAI)
        target = generated_at.astimezone(SHANGHAI) if generated_at.tzinfo else generated_at.replace(tzinfo=SHANGHAI)
        if quote_time > target:
            return "stale", "quote_future_at_snapshot_generation"
        if quote_time.date() != target.date() or (target - quote_time).total_seconds() > 8 * 60:
            return "stale", "quote_stale_at_snapshot_generation"
        if not quote.timestamp_verified or not quote.is_realtime or quote.degraded_reason:
            return "stale", "quote_unverified_or_degraded"
        return "fresh", "confirmed_indicator_with_verified_quote"

    def _provisional_status(self, db: Session, instrument_id: int, row, generated_at: datetime) -> dict:
        if row is None:
            return {"status": "missing", "used_for_derived_values": False, "reason": "no_provisional_input"}
        observed = row.observed_at.astimezone(SHANGHAI) if row.observed_at.tzinfo else row.observed_at.replace(tzinfo=SHANGHAI)
        target = generated_at.astimezone(SHANGHAI) if generated_at.tzinfo else generated_at.replace(tzinfo=SHANGHAI)
        if observed > target or observed.date() != target.date() or (target - observed).total_seconds() > 8 * 60:
            return {"status": "stale", "used_for_derived_values": False, "reason": "provisional_outside_snapshot_window", "observed_at": observed.isoformat(), "source": row.source, "timestamp_verified": bool(row.timestamp_verified)}
        complete = all(
            value is not None and isfinite(float(value))
            for value in (row.open_price, row.high_price, row.low_price, row.last_price, row.volume, row.amount)
        )
        if not complete:
            return {
                "status": "stale",
                "used_for_derived_values": False,
                "reason": "incomplete_provisional_input",
                "source_time_verified": bool(row.timestamp_verified),
                "observed_at": observed.isoformat(), "source": row.source, "timestamp_verified": bool(row.timestamp_verified),
            }
        derived = self._derive_provisional(db, instrument_id, row)
        if derived is None:
            return {
                "status": "stale",
                "used_for_derived_values": False,
                "reason": "confirmed_history_insufficient_for_provisional_derivation",
                "source_time_verified": bool(row.timestamp_verified),
            }
        return {
            "status": "computed_research_only" if row.timestamp_verified else "computed_unverified_research_only",
            "used_for_derived_values": True,
            "reason": "temporary_confirmed_history_plus_complete_provisional_ohlcv",
            "forecast_policy": "persisted_settled_daily_only",
            "forecast_policy_reason": "no_time_matched_intraday_neighbor_history",
            "source_time_verified": bool(row.timestamp_verified),
            "observed_at": observed.isoformat(), "source": row.source, "timestamp_verified": bool(row.timestamp_verified),
            "derived": derived,
        }

    def _history_and_levels(self, db: Session, instrument_id: int) -> tuple[list[dict], dict]:
        bars = db.scalars(
            select(DailyBar).where(DailyBar.instrument_id == instrument_id)
            .order_by(DailyBar.trade_date.desc(), DailyBar.id.desc()).limit(160)
        ).all()
        history = [
            {
                "date": item.trade_date.isoformat(),
                "open": item.open,
                "high": item.high,
                "low": item.low,
                "close": item.close,
                "volume": item.volume,
                "is_forecast": False,
            }
            for item in reversed(bars)
        ]
        if not history:
            return history, {"status": "missing", "label": "历史不足"}
        # 支撑压力走统一快照服务（250 根 + 真实成交额口径，与其他页面完全一致）。
        levels = self.support_resistance.latest(db, instrument_id)
        return history, levels or {"status": "missing", "label": "支撑压力快照待生成", "chan_zone_approx": None}

    @staticmethod
    def _latest_confirmed_daily_return(db: Session, instrument_id: int) -> float | None:
        row = db.scalar(
            select(DailyBar)
            .where(DailyBar.instrument_id == instrument_id)
            .order_by(DailyBar.trade_date.desc(), DailyBar.id.desc())
            .limit(1)
        )
        return percent_points_to_ratio(row.pct_change) if row is not None else None

    @staticmethod
    def _forecast_scenario(history: list[dict], forecasts: dict[str, dict]) -> list[dict]:
        if not history:
            return []
        current = finite_or_none(history[-1].get("close"))
        basis_date = history[-1].get("date")
        if current is None or current <= 0 or not basis_date:
            return []
        accepted = {h: {**forecasts[str(h)], "expected_return": value} for h in HORIZONS
                    if (value := finite_or_none(forecasts.get(str(h), {}).get("expected_return"))) is not None}
        if not accepted or any(row.get("as_of_date") != basis_date for row in accepted.values()):
            return []
        if any(not row.get("model_version") for row in accepted.values()) or len({row.get("model_version") for row in accepted.values()}) != 1:
            return []
        if any(row["expected_return"] <= -1 for row in accepted.values()):
            return []
        anchors = {0: current, **{h: current * (1 + row["expected_return"]) for h, row in accepted.items()}}
        if not all(isfinite(value) and value > 0 for value in anchors.values()):
            return []
        candles, previous = [], current
        for day in range(1, max(accepted) + 1):
            upper_key = min(key for key in anchors if key >= day)
            lower_key = max(key for key in anchors if key < day)
            lower = anchors[lower_key]
            close = lower + (anchors[upper_key] - lower) * (day - lower_key) / (upper_key - lower_key)
            candles.append({"day": day, "open": round(previous, 6), "high": round(max(previous, close), 6),
                "low": round(min(previous, close), 6), "close": round(close, 6), "volume": None,
                "is_forecast": True, "not_actual": True, "scenario": "snapshot_conditional_path",
                "as_of_date": basis_date, "base_price": current, "anchor_horizons": sorted(accepted),
                "interpolated": day not in accepted, "ohlc_semantics": "illustration_not_predicted_market_ohlc"})
            previous = close
        return candles

    def _derive_provisional(self, db: Session, instrument_id: int, row) -> dict | None:
        """Compute a temporary research view without mutating DailyBar or snapshots."""

        history = db.scalars(
            select(DailyBar)
            .where(DailyBar.instrument_id == instrument_id, DailyBar.trade_date < row.observed_at.date())
            .order_by(DailyBar.trade_date)
        ).all()
        if len(history) < 30:
            return None
        raw = pd.DataFrame(
            [
                {
                    "trade_date": item.trade_date,
                    "open": item.open,
                    "high": item.high,
                    "low": item.low,
                    "close": item.close,
                    "volume": item.volume,
                    "amount": item.amount,
                }
                for item in history
            ]
            + [
                {
                    "trade_date": row.observed_at.date(),
                    "open": row.open_price,
                    "high": row.high_price,
                    "low": row.low_price,
                    "close": row.last_price,
                    "volume": row.volume,
                    "amount": row.amount,
                }
            ]
        )
        try:
            indicators = calculate_indicators(raw, self.settings.load_strategy()["indicator"])
            support_resistance = build_support_resistance(raw)
        except Exception:
            # Source/history quality failure is represented to the read model,
            # never hidden by overwriting confirmed indicators or forecasts.
            return None
        return {
            "indicator_values": dict(indicators.values),
            "support_resistance": support_resistance,
            "td_basis": "TD9 setup only; TD13 not implemented",
            "chan_basis": "overlap-zone approximation only; not full Chan/CZSC",
        }

    @staticmethod
    def _forecast_payload(row) -> dict:
        return {
            "source": "persisted_forecast_snapshot" if row is not None else "unavailable",
            "model_version": row.model_version if row is not None else None,
            "feature_schema_version": row.feature_schema_version if row is not None else None,
            "config_hash": row.config_hash if row is not None else None,
            "input_hash": row.input_hash if row is not None else None,
            "feature_basis": "settled_daily_bars" if row is not None else "unavailable",
            "intraday_provisional_used": False,
            "expected_return": finite_or_none(row.expected_return) if row is not None else None,
            "q10": finite_or_none(row.q10) if row is not None else None,
            "q50": finite_or_none(row.q50) if row is not None else None,
            "q90": finite_or_none(row.q90) if row is not None else None,
            "p_up": finite_or_none(row.p_up) if row is not None else None,
            "confidence": finite_or_none(row.confidence) if row is not None else None,
            "calibration_status": row.calibration_status if row is not None else "not_calibrated",
            "as_of_date": row.as_of_date.isoformat() if row is not None else None,
            "return_semantics": {"unit": "decimal_ratio", "no_unit_guessing": True},
            "disclaimer": "FORECAST · 非实际结果",
        }

    @staticmethod
    def _latest_by_instrument(db: Session, model, first_order, second_order) -> dict[int, object]:
        from app.utils.snapshot_queries import latest_enabled
        return {row.instrument_id: row for row in latest_enabled(db, model, first_order.desc(), second_order.desc())}

    @staticmethod
    def _latest_forecasts(db: Session) -> dict[int, dict[int, ForecastSnapshot]]:
        from app.utils.snapshot_queries import latest_enabled
        rows = latest_enabled(db, ForecastSnapshot, ForecastSnapshot.as_of_date.desc(), ForecastSnapshot.generated_at.desc(),
                              partitions=[ForecastSnapshot.instrument_id, ForecastSnapshot.horizon],
                              where=[ForecastSnapshot.horizon.in_(HORIZONS)])
        latest: dict[int, dict[int, ForecastSnapshot]] = {}
        for row in rows:
            latest.setdefault(row.instrument_id, {})[row.horizon] = row
        return latest

    @staticmethod
    def _previous_indicator_values(db: Session, latest: dict) -> dict:
        from app.utils.indicator_history import previous_values
        return {ident: values for ident, current in latest.items()
                if (values := previous_values(db, current)) is not None}

    @staticmethod
    def _latest_provisional(db: Session) -> dict[int, DecisionBoardProvisionalInput]:
        from app.utils.snapshot_queries import latest_enabled
        return {row.instrument_id: row for row in latest_enabled(db, DecisionBoardProvisionalInput,
            DecisionBoardProvisionalInput.observed_at.desc(), DecisionBoardProvisionalInput.id.desc())}

    @staticmethod
    def _select_horizon(payload: dict, horizon: int) -> dict:
        selected = dict(payload)
        selected["selected_forecast_horizon"] = horizon
        selected["selected_horizon"] = horizon
        rows = []
        for row in selected.get("rows", []):
            materialized = dict(row)
            materialized["forecast"] = dict((row.get("forecasts") or {}).get(str(horizon), {}))
            materialized["sort_keys"] = {
                **dict(row.get("sort_keys") or {}),
                **semantic_sort_keys(
                    volume=dict(row.get("volume") or {}),
                    ma=dict(row.get("ma") or {}),
                    macd=dict(row.get("macd") or {}),
                    kdj=dict(row.get("kdj") or {}),
                    td=dict(row.get("td") or {}),
                    rsi=dict(row.get("rsi") or {}),
                    chan=dict(row.get("chan") or {}),
                    forecasts=dict(row.get("forecasts") or {}),
                    horizon=horizon,
                    today_return=finite_or_none((row.get("returns") or {}).get("today")),
                ),
            }
            rows.append(materialized)
        selected["rows"] = rows
        selected["groups"] = {
            grade: [row for row in rows if row.get("grade") == grade] for grade in GRADE_ORDER
        }
        selected["groups"]["数据异常"] = [row for row in rows if row.get("grade") == "数据异常"]
        selected["counts"] = {grade: len(group) for grade, group in selected["groups"].items()}
        return selected

    @staticmethod
    def _empty_payload(horizon: int) -> dict:
        return {
            "snapshot_id": None,
            "generated_at": None,
            "next_refresh_at": None,
            "selected_forecast_horizon": horizon,
            "selected_horizon": horizon,
            "forecast_horizons": list(HORIZONS),
            "horizons": list(HORIZONS),
            "freshness": "missing",
            "data_status": {"freshness": "missing", "row_status_counts": {}},
            "source_status": {
                "basis": "persisted_confirmed_snapshots",
                "freshness": "missing",
                "actionable": False,
                "research_only": True,
                "source_time_verified": False,
            },
            "indicator_basis": {
                "daily_history": "confirmed_daily_bars_only",
                "td": "TD9 setup only; TD13 not implemented",
                "chan": "overlap-zone approximation only; not full Chan/CZSC",
            },
            "indicator_status": {
                "basis": "confirmed_daily_history_plus_explicit_provisional_state",
                "forecast_basis": "persisted_settled_daily_snapshots",
                "intraday_forecast_policy": "disabled_until_time_matched_intraday_history",
                "td": "TD9 setup only; TD13 not implemented",
                "chan": "overlap-zone approximation only; not full Chan/CZSC",
            },
            "groups": {grade: [] for grade in (*GRADE_ORDER, "数据异常")},
            "counts": {grade: 0 for grade in (*GRADE_ORDER, "数据异常")},
            "rows": [],
            "research_only": True,
            "automatic_orders": False,
        }

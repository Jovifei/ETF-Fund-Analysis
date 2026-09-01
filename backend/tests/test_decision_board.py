from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from app.main import app
from app.models import (
    DailyBar,
    DecisionBoardProvisionalInput,
    DecisionBoardSnapshot,
    EventLog,
    ForecastSnapshot,
    IndicatorSnapshot,
    QuoteSnapshot,
    TaskRun,
)
from app.scheduler import claim_decision_board_slot, decision_board_due_slot
from app.services.decision_board_service import (
    DecisionBoardRefreshBusy,
    DecisionBoardService,
    health_sort_key,
    percent_points_to_ratio,
    semantic_sort_keys,
)
from app.services.task_service import TaskBusyError, TaskService
from fastapi.testclient import TestClient
from sqlalchemy import func, select

SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_percent_points_are_converted_to_decimal_ratios_including_small_and_zero_values() -> None:
    assert percent_points_to_ratio(0.01) == 0.0001
    assert percent_points_to_ratio(0.0) == 0.0
    assert percent_points_to_ratio(-2.5) == -0.025
    assert percent_points_to_ratio(None) is None


def test_health_sort_key_is_display_only_and_keeps_existing_grade_order() -> None:
    assert health_sort_key("可加仓", "fresh") < health_sort_key("可入场", "fresh")
    assert health_sort_key("可入场", "fresh") < health_sort_key("可入场", "stale")
    assert health_sort_key("减仓", "missing") > health_sort_key("观望", "stale")


def test_refresh_builds_one_unique_row_per_enabled_instrument_and_never_writes_daily_bars(
    db_session, bootstrapped
) -> None:
    service = DecisionBoardService()
    daily_bars_before = db_session.scalar(select(func.count(DailyBar.id)))

    result = service.refresh(db_session, generated_at=datetime(2026, 8, 31, 10, 30, tzinfo=SHANGHAI))

    payload = result.payload
    assert result.snapshot.snapshot_id == payload["snapshot_id"]
    assert len(payload["rows"]) == len({row["ts_code"] for row in payload["rows"]})
    assert all(row["return_semantics"]["unit"] == "decimal_ratio" for row in payload["rows"])
    assert set(payload["groups"]) == {"可加仓", "可入场", "可试探", "观望", "减仓", "数据异常"}
    assert payload["selected_forecast_horizon"] == 1
    assert payload["source_status"]["actionable"] is False
    assert db_session.scalar(select(func.count(DailyBar.id))) == daily_bars_before
    assert db_session.scalar(select(func.count(DecisionBoardSnapshot.id))) == 1


def test_snapshot_read_is_provider_free_and_returns_explicit_stale_missing_state(db_session, bootstrapped, monkeypatch) -> None:
    service = DecisionBoardService()
    service.refresh(db_session, generated_at=datetime(2026, 8, 31, 10, 30, tzinfo=SHANGHAI))
    db_session.commit()

    monkeypatch.setattr("app.providers.factory.create_provider", lambda *_: pytest.fail("provider called"))
    payload = service.read_latest(db_session, horizon=3)

    assert payload["selected_forecast_horizon"] == 3
    assert payload["source_status"]["actionable"] is False
    assert all("freshness" in row and "data_status" in row for row in payload["rows"])
    assert all(row["forecast"]["return_semantics"]["unit"] == "decimal_ratio" for row in payload["rows"])


def test_demo_refresh_is_ephemeral_and_does_not_write_production_snapshot(db_session, bootstrapped) -> None:
    before = db_session.scalar(select(func.count(DecisionBoardSnapshot.id)))

    result = DecisionBoardService().refresh(db_session, demo=True)

    assert result.snapshot.id is None
    assert result.payload["source_status"]["actionable"] is False
    assert db_session.scalar(select(func.count(DecisionBoardSnapshot.id))) == before


def test_provisional_input_is_isolated_from_daily_bars(db_session, bootstrapped) -> None:
    service = DecisionBoardService()
    before = db_session.scalar(select(func.count(DailyBar.id)))

    service.record_provisional_input(
        db_session,
        ts_code="510300.SH",
        observed_at=datetime(2026, 8, 31, 14, 30, tzinfo=SHANGHAI),
        source="fresh_test_provider",
        timestamp_verified=False,
        open_price=3.0,
        high_price=3.1,
        low_price=2.9,
        last_price=3.05,
        volume=100.0,
        amount=300.0,
        pct_change_percent_points=0.01,
    )

    assert db_session.scalar(select(func.count(DailyBar.id))) == before
    assert db_session.scalar(select(func.count(DecisionBoardProvisionalInput.id))) == 1

    payload = service.refresh(
        db_session, generated_at=datetime(2026, 8, 31, 14, 35, tzinfo=SHANGHAI)
    ).payload
    row = next(item for item in payload["rows"] if item["ts_code"] == "510300.SH")
    assert row["provisional"]["used_for_derived_values"] is True
    assert row["provisional"]["status"] == "computed_unverified_research_only"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime(2026, 8, 31, 9, 0, tzinfo=SHANGHAI), "20260831-0900"),
        (datetime(2026, 8, 31, 14, 57, tzinfo=SHANGHAI), "20260831-1457"),
        (datetime(2026, 8, 31, 11, 31, tzinfo=SHANGHAI), None),
        (datetime(2026, 8, 30, 14, 30, tzinfo=SHANGHAI), None),
    ],
)
def test_due_slots_skip_lunch_and_weekends(value: datetime, expected: str | None) -> None:
    assert decision_board_due_slot(value, is_trade_day=value.weekday() < 5) == expected


def test_due_slot_claim_survives_restart_and_deduplicates(db_session) -> None:
    now = datetime(2026, 8, 31, 14, 30, tzinfo=SHANGHAI)
    slot = decision_board_due_slot(now, is_trade_day=True)
    assert slot is not None
    assert claim_decision_board_slot(db_session, slot, now) is True
    db_session.commit()
    assert claim_decision_board_slot(db_session, slot, now) is False


def test_two_refresh_requests_leave_only_one_active_job(db_session) -> None:
    service = DecisionBoardService()
    first = service.enqueue_refresh(db_session)
    db_session.commit()

    with pytest.raises(DecisionBoardRefreshBusy):
        service.enqueue_refresh(db_session)

    active = db_session.scalars(
        select(TaskRun).where(
            TaskRun.task_name == "refresh_decision_board",
            TaskRun.status.in_(("queued", "running")),
        )
    ).all()
    assert len(active) == 1
    assert active[0].run_id == first["task_id"]
    active[0].status = "succeeded"
    active[0].finished_at = datetime.now(SHANGHAI)
    db_session.commit()


def test_active_refresh_index_allows_terminal_history_and_one_new_queue(db_session) -> None:
    finished_at = datetime.now(SHANGHAI)
    db_session.add_all(
        [
            TaskRun(
                run_id="decision-board-succeeded-history",
                task_name="refresh_decision_board",
                status="succeeded",
                started_at=finished_at,
                finished_at=finished_at,
                result_json={},
            ),
            TaskRun(
                run_id="decision-board-failed-history",
                task_name="refresh_decision_board",
                status="failed",
                started_at=finished_at,
                finished_at=finished_at,
                result_json={},
            ),
        ]
    )
    db_session.flush()

    queued = DecisionBoardService().enqueue_refresh(db_session)

    assert queued["status"] == "queued"
    active = db_session.scalar(select(TaskRun).where(TaskRun.run_id == queued["task_id"]))
    assert active.status == "queued"
    active.status = "succeeded"
    active.finished_at = datetime.now(SHANGHAI)
    db_session.flush()


def test_task_run_adopts_the_active_queued_decision_board_refresh(db_session, bootstrapped) -> None:
    queued = DecisionBoardService().enqueue_refresh(db_session)
    db_session.commit()

    result = TaskService().run(db_session, "refresh_decision_board")

    assert result["run_id"] == queued["task_id"]
    rows = db_session.scalars(
        select(TaskRun)
        .where(TaskRun.task_name == "refresh_decision_board")
        .order_by(TaskRun.started_at)
    ).all()
    assert next(row for row in rows if row.run_id == queued["task_id"]).status == "succeeded"
    assert all(row.status not in ("queued", "running") for row in rows)


def test_task_run_returns_controlled_busy_when_decision_board_refresh_is_running(db_session) -> None:
    queued = DecisionBoardService().enqueue_refresh(db_session)
    active = db_session.scalar(select(TaskRun).where(TaskRun.run_id == queued["task_id"]))
    active.status = "running"
    db_session.flush()

    with pytest.raises(TaskBusyError):
        TaskService().run(db_session, "refresh_decision_board")

    assert db_session.scalar(select(TaskRun.status).where(TaskRun.run_id == queued["task_id"])) == "running"
    active.status = "succeeded"
    active.finished_at = datetime.now(SHANGHAI)
    db_session.flush()


def test_private_api_reads_snapshot_and_queues_refresh(db_session, bootstrapped) -> None:
    DecisionBoardService().refresh(db_session, generated_at=datetime(2026, 8, 31, 10, 30, tzinfo=SHANGHAI))
    db_session.commit()

    client = TestClient(app)
    response = client.get("/api/decision-board?horizon=5")
    detail = client.get("/api/decision-board/510300.SH?horizon=5")
    queued = client.post("/api/decision-board/refresh")

    assert response.status_code == 200
    assert response.json()["selected_forecast_horizon"] == 5
    assert response.json()["selected_horizon"] == 5
    assert all(isinstance(group, list) for group in response.json()["groups"].values())
    assert detail.status_code == 200
    assert detail.json()["ts_code"] == "510300.SH"
    assert queued.status_code == 202
    assert queued.json()["task_id"]


def test_snapshot_rows_supply_all_wide_table_metric_objects_and_selected_groups(db_session, bootstrapped) -> None:
    service = DecisionBoardService()
    service.refresh(db_session)

    payload = service.read_latest(db_session, horizon=5)
    row = payload["rows"][0]
    assert set(("volume", "ma", "macd", "kdj", "td", "rsi", "chan", "sector")) <= set(row)
    assert all(isinstance(row[key], dict) and row[key].get("label") for key in ("volume", "ma", "macd", "kdj", "td", "rsi", "chan", "sector"))
    assert row["forecast"] == row["forecasts"]["5"]
    assert payload["groups"][row["grade"]][0]["forecast"] == row["forecasts"]["5"]


def test_detail_is_captured_in_snapshot_and_stays_immutable_after_domain_rows_change(db_session, bootstrapped) -> None:
    service = DecisionBoardService()
    built = service.refresh(db_session)
    detail_before = service.read_instrument(db_session, "510300.SH", horizon=10)
    assert detail_before is not None
    assert detail_before["snapshot_id"] == built.snapshot.snapshot_id
    assert len(detail_before["history"]) > 0
    assert len(detail_before["forecast_scenario"]) == 10
    assert "support_resistance" in detail_before and "chan" in detail_before

    bar = db_session.scalar(select(DailyBar).where(DailyBar.instrument_id == detail_before["instrument_id"]).limit(1))
    bar.close = 999.0
    db_session.flush()
    detail_after = service.read_instrument(db_session, "510300.SH", horizon=10)

    assert detail_after == detail_before


def test_complete_unverified_provisional_is_derived_research_only_and_drives_display(db_session, bootstrapped) -> None:
    service = DecisionBoardService()
    service.record_provisional_input(
        db_session,
        ts_code="510300.SH",
        observed_at=datetime(2026, 8, 31, 14, 30, tzinfo=SHANGHAI),
        source="free_source",
        timestamp_verified=False,
        open_price=3.0,
        high_price=3.2,
        low_price=2.9,
        last_price=3.1,
        volume=1000.0,
        amount=3000.0,
        pct_change_percent_points=0.01,
    )
    payload = service.refresh(
        db_session, generated_at=datetime(2026, 8, 31, 14, 35, tzinfo=SHANGHAI)
    ).payload
    row = next(item for item in payload["rows"] if item["ts_code"] == "510300.SH")

    assert row["provisional"]["status"] == "computed_unverified_research_only"
    assert row["provisional"]["used_for_derived_values"] is True
    assert row["returns"]["today"] == 0.0001
    assert row["quote"]["actionable"] is False


def test_previous_day_delta_is_today_minus_previous_confirmed_return(db_session, bootstrapped) -> None:
    row = DecisionBoardService().refresh(db_session).payload["rows"][0]
    returns = row["returns"]
    assert returns["previous_confirmed_return"] is not None
    assert returns["previous_day_delta"] == pytest.approx(
        returns["today"] - returns["previous_confirmed_return"]
    )


def test_snapshot_id_binds_list_and_detail_to_exact_persisted_snapshot(db_session, bootstrapped) -> None:
    service = DecisionBoardService()
    first = service.refresh(db_session, generated_at=datetime(2026, 8, 27, 14, 30, tzinfo=SHANGHAI))
    second = service.refresh(db_session, generated_at=datetime(2026, 8, 28, 14, 30, tzinfo=SHANGHAI))
    db_session.commit()

    selected = service.read_latest(db_session, horizon=3, snapshot_id=first.snapshot.snapshot_id)
    detail = service.read_instrument(db_session, "510300.SH", horizon=3, snapshot_id=first.snapshot.snapshot_id)

    assert selected["snapshot_id"] == first.snapshot.snapshot_id
    assert selected["snapshot_id"] != second.snapshot.snapshot_id
    assert detail is not None and detail["snapshot_id"] == first.snapshot.snapshot_id
    assert service.read_latest(db_session, snapshot_id="missing-snapshot") is None

    client = TestClient(app)
    bound_list = client.get(f"/api/decision-board?snapshot_id={first.snapshot.snapshot_id}")
    bound_detail = client.get(
        f"/api/decision-board/510300.SH?snapshot_id={first.snapshot.snapshot_id}"
    )
    missing = client.get("/api/decision-board?snapshot_id=missing-snapshot")
    assert bound_list.status_code == 200 and bound_list.json()["snapshot_id"] == first.snapshot.snapshot_id
    assert bound_detail.status_code == 200 and bound_detail.json()["snapshot_id"] == first.snapshot.snapshot_id
    assert missing.status_code == 404


def test_next_refresh_skips_weekend_to_next_trading_day() -> None:
    from app.services.decision_board_service import next_decision_board_refresh

    next_refresh = next_decision_board_refresh(datetime(2026, 9, 5, 16, 0, tzinfo=SHANGHAI))
    assert next_refresh == datetime(2026, 9, 7, 9, 0, tzinfo=SHANGHAI)


def test_snapshot_retention_keeps_last_twenty_trading_dates(db_session, bootstrapped) -> None:
    service = DecisionBoardService()
    day = datetime(2026, 7, 1, 14, 30, tzinfo=SHANGHAI)
    created = 0
    while created < 21:
        if day.weekday() < 5:
            service.refresh(db_session, generated_at=day)
            created += 1
        day += timedelta(days=1)
    db_session.flush()
    dates = db_session.scalars(select(DecisionBoardSnapshot.generated_at).order_by(DecisionBoardSnapshot.generated_at)).all()
    assert len({item.date() for item in dates}) == 20


def test_semantic_health_sort_keys_use_approved_primitive_priority_order() -> None:
    best = semantic_sort_keys(
        volume={"kind": "expand"}, ma={"kind": "bull"}, macd={"kind": "gold"},
        kdj={"kind": "healthy"}, td={"kind": "none"}, rsi={"value": 60},
        chan={"status": "upper_break"}, forecasts={"1": {"expected_return": 0.02, "confidence": 40}}, horizon=1, today_return=0.01,
    )
    weak = semantic_sort_keys(
        volume={"kind": "contract"}, ma={"kind": "bear"}, macd={"kind": "death"},
        kdj={"kind": "death"}, td={"kind": "sell"}, rsi={"value": 80},
        chan={"status": "lower_break"}, forecasts={"1": {"expected_return": -0.02, "confidence": 99}}, horizon=1, today_return=-0.01,
    )
    assert all(isinstance(best[key], (int, float)) for key in ("volume", "ma", "macd", "kdj", "td", "rsi", "chan", "forecast"))
    for key in ("volume", "ma", "macd", "kdj", "td", "rsi", "chan", "forecast"):
        assert best[key] < weak[key]


def test_selected_horizon_changes_forecast_sort_key() -> None:
    metrics = {"kind": "flat"}
    forecasts = {
        "1": {"expected_return": 0.01, "confidence": 0.4},
        "5": {"expected_return": -0.01, "confidence": 0.9},
    }
    one_day = semantic_sort_keys(
        volume=metrics, ma={"kind": "mixed"}, macd={"kind": "bull_cont"},
        kdj={"kind": "healthy"}, td={"kind": "none"}, rsi={"value": 60},
        chan={"status": "inside"}, forecasts=forecasts, horizon=1, today_return=0.0,
    )
    five_day = semantic_sort_keys(
        volume=metrics, ma={"kind": "mixed"}, macd={"kind": "bull_cont"},
        kdj={"kind": "healthy"}, td={"kind": "none"}, rsi={"value": 60},
        chan={"status": "inside"}, forecasts=forecasts, horizon=5, today_return=0.0,
    )
    assert one_day["forecast"] < five_day["forecast"]


def test_semantic_sort_keys_break_same_class_ties_without_object_text() -> None:
    common = {"ma": {"kind": "bull"}, "macd": {"kind": "gold"}, "kdj": {"kind": "healthy"}, "rsi": {"value": 60}, "chan": {"status": "inside"}, "forecasts": {"1": {"expected_return": 0.01, "confidence": 0.5}}, "horizon": 1}
    strong = semantic_sort_keys(volume={"kind": "expand", "ratio": 2.0}, td={"kind": "buy", "label": "TD9"}, today_return=0.01, **common)
    weak = semantic_sort_keys(volume={"kind": "expand", "ratio": 1.4}, td={"kind": "buy", "label": "TD3"}, today_return=0.01, **common)
    more_arrows = semantic_sort_keys(volume={"kind": "flat"}, td={"kind": "none"}, today_return=0.0, **{**common, "ma": {"kind": "bull", "arrows": [{"dir": "up"}] * 4}})
    fewer_arrows = semantic_sort_keys(volume={"kind": "flat"}, td={"kind": "none"}, today_return=0.0, **{**common, "ma": {"kind": "bull", "arrows": [{"dir": "up"}] * 2}})
    assert strong["volume"] < weak["volume"]
    assert strong["td"] < weak["td"]
    assert more_arrows["ma"] < fewer_arrows["ma"]


def test_read_latest_and_api_rematerialize_selected_horizon_forecast_key(db_session, bootstrapped) -> None:
    db_session.query(DecisionBoardProvisionalInput).delete()
    target = db_session.scalar(
        select(ForecastSnapshot)
        .where(ForecastSnapshot.horizon == 1)
        .order_by(ForecastSnapshot.instrument_id, ForecastSnapshot.as_of_date.desc(), ForecastSnapshot.generated_at.desc())
        .limit(1)
    )
    matching = db_session.scalar(
        select(ForecastSnapshot)
        .where(ForecastSnapshot.instrument_id == target.instrument_id, ForecastSnapshot.horizon == 5)
        .order_by(ForecastSnapshot.as_of_date.desc(), ForecastSnapshot.generated_at.desc())
        .limit(1)
    )
    target.expected_return, target.confidence = 0.03, 0.2
    matching.expected_return, matching.confidence = -0.02, 0.9
    snapshot = DecisionBoardService().refresh(db_session)
    db_session.commit()
    code = db_session.scalar(select(DecisionBoardSnapshot).where(DecisionBoardSnapshot.snapshot_id == snapshot.snapshot.snapshot_id)).payload_json["rows"][0]["ts_code"]
    one = DecisionBoardService().read_latest(db_session, horizon=1, snapshot_id=snapshot.snapshot.snapshot_id)
    five = DecisionBoardService().read_latest(db_session, horizon=5, snapshot_id=snapshot.snapshot.snapshot_id)
    one_row = next(row for row in one["rows"] if row["instrument_id"] == target.instrument_id)
    five_row = next(row for row in five["rows"] if row["instrument_id"] == target.instrument_id)
    client = TestClient(app)
    api_one = client.get(f"/api/decision-board?snapshot_id={snapshot.snapshot.snapshot_id}&horizon=1")
    api_five = client.get(f"/api/decision-board?snapshot_id={snapshot.snapshot.snapshot_id}&horizon=5")
    assert one_row["sort_keys"]["forecast"] != five_row["sort_keys"]["forecast"]
    assert api_one.status_code == api_five.status_code == 200
    assert next(row for row in api_one.json()["rows"] if row["instrument_id"] == target.instrument_id)["sort_keys"]["forecast"] == one_row["sort_keys"]["forecast"]
    assert code


def test_snapshot_marks_old_verified_quote_stale_and_keeps_anomaly_visible(db_session, bootstrapped) -> None:
    indicator = db_session.scalar(select(IndicatorSnapshot).limit(1))
    quote = db_session.scalar(select(QuoteSnapshot).where(QuoteSnapshot.instrument_id == indicator.instrument_id).limit(1))
    quote.timestamp_verified, quote.is_realtime = True, True
    generated = (quote.fetched_at or quote.quote_time) + timedelta(minutes=9)
    payload = DecisionBoardService().refresh(db_session, generated_at=generated).payload
    row = next(item for item in payload["rows"] if item["instrument_id"] == indicator.instrument_id)
    assert row["freshness"] == "stale"
    assert row["data_status"] == "quote_stale_at_snapshot_generation"
    db_session.delete(indicator)
    db_session.flush()
    payload = DecisionBoardService().refresh(db_session, generated_at=generated).payload
    assert next(row for row in payload["groups"]["数据异常"] if row["instrument_id"] == indicator.instrument_id)["grade"] == "数据异常"


def test_snapshot_marks_same_day_future_verified_quote_stale_and_non_actionable(db_session, bootstrapped) -> None:
    indicator = db_session.scalar(select(IndicatorSnapshot).limit(1))
    quote = db_session.scalar(select(QuoteSnapshot).where(QuoteSnapshot.instrument_id == indicator.instrument_id).limit(1))
    quote.timestamp_verified, quote.is_realtime, quote.degraded_reason = True, True, None
    generated = (quote.fetched_at or quote.quote_time) - timedelta(minutes=1)

    payload = DecisionBoardService().refresh(db_session, generated_at=generated).payload
    row = next(item for item in payload["rows"] if item["instrument_id"] == indicator.instrument_id)

    assert row["freshness"] == "stale"
    assert row["data_status"] == "quote_future_at_snapshot_generation"
    assert row["actionable"] is False
    assert row["quote"]["actionable"] is False


def test_cross_day_provisional_input_is_stale_and_not_used_for_derived_values(db_session, bootstrapped) -> None:
    service = DecisionBoardService()
    service.record_provisional_input(
        db_session,
        ts_code="510300.SH",
        observed_at=datetime(2026, 8, 31, 14, 30, tzinfo=SHANGHAI),
        source="cross_day_test_provider",
        timestamp_verified=False,
        open_price=3.0,
        high_price=3.1,
        low_price=2.9,
        last_price=3.05,
        volume=100.0,
        amount=300.0,
        pct_change_percent_points=0.01,
    )

    payload = service.refresh(
        db_session, generated_at=datetime(2026, 9, 1, 9, 30, tzinfo=SHANGHAI)
    ).payload
    row = next(item for item in payload["rows"] if item["ts_code"] == "510300.SH")

    assert row["provisional"]["status"] == "stale"
    assert row["provisional"]["used_for_derived_values"] is False
    assert row["provisional"]["reason"] == "provisional_outside_snapshot_window"


def test_decision_board_task_emits_safe_update_event(db_session, bootstrapped) -> None:
    result = TaskService().run(db_session, "refresh_decision_board")
    event = db_session.scalar(select(EventLog).where(EventLog.event_type == "decision_board.updated").order_by(EventLog.id.desc()).limit(1))
    assert event is not None
    assert event.payload_json == {"snapshot_id": result["snapshot_id"], "generated_at": result["generated_at"], "freshness": result["freshness"]}

"""US markets research block: baskets, metrics, provider hygiene, contract, bundle and API."""
from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.us_markets_research import builder, compute, contracts, providers, store
from app.us_markets_research.providers import (
    CLOSE_SOURCE_OFFICIAL,
    CLOSE_SOURCE_PROVISIONAL,
    CsvProvider,
    ProviderResult,
    adjust_frame,
    fill_provisional_close,
)
from app.workspace.api import router
from app.workspace.local_display_contract import CONTRACT_VERSION, compute_parts_hashes, verify_bundle_integrity
from app.workspace.local_display_read import LocalDisplayReader, LocalDisplayStore

APP_ROOT = Path(__file__).resolve().parents[1] / "app" / "us_markets_research"
NOW = datetime(2026, 11, 14, 4, 0, tzinfo=timezone.utc)
DAYS = pd.bdate_range("2025-01-01", "2026-11-13")


def make_frame(closes, *, index=DAYS, spread=0.01, volume=1_000_000.0, provisional_last=False):
    closes = np.asarray(closes, dtype=float)
    frame = pd.DataFrame({
        "open": closes * (1 - spread / 2), "high": closes * (1 + spread), "low": closes * (1 - spread),
        "close": closes, "volume": volume, "close_source": CLOSE_SOURCE_OFFICIAL}, index=index[-len(closes):])
    if provisional_last:
        frame.iloc[-1, frame.columns.get_loc("close_source")] = CLOSE_SOURCE_PROVISIONAL
    frame.index.name = "date"
    return frame


def growth(n, daily):
    return 100.0 * np.cumprod(np.full(n, 1.0 + daily))


class FakeProvider:
    name = "fake"

    def __init__(self, frames, *, failed=(), provisional=()):
        self.frames, self.failed, self.provisional = frames, set(failed), list(provisional)

    def fetch(self, tickers, start, end):
        result = ProviderResult(source_label="fake (test fixture)", source_version="0")
        for ticker in tickers:
            if ticker in self.failed or ticker not in self.frames:
                result.audit.append({"provider": "fake", "operation": "download", "ticker": ticker,
                                     "duration_ms": 0, "rows": 0, "ok": False, "reason": "no_rows_returned"})
            else:
                frame = self.frames[ticker]
                result.frames[ticker] = frame[(frame.index >= pd.Timestamp(start)) & (frame.index < pd.Timestamp(end))]
                result.audit.append({"provider": "fake", "operation": "download", "ticker": ticker,
                                     "duration_ms": 0, "rows": len(frame), "ok": True, "reason": None})
        result.provisional = self.provisional
        return result


@pytest.fixture()
def config():
    return builder.load_config()


@pytest.fixture()
def all_frames(config):
    n = len(DAYS)
    frames = {}
    for i, ticker in enumerate(builder.required_tickers(config)):
        frames[ticker] = make_frame(growth(n, 0.001 + 0.0002 * i))
    return frames


# ---- config -----------------------------------------------------------------------------------

def test_config_defines_requested_baskets_and_indices(config):
    baskets = {b["series_id"]: b["members"] for b in config["baskets"]}
    assert baskets["us-cpo-optical-broad-ew"] == ["COHR", "LITE", "FN", "AAOI", "CIEN", "ANET", "AVGO", "MRVL", "CRDO"]
    assert baskets["us-cpo-optical-narrow-ew"] == baskets["us-cpo-optical-broad-ew"][:5]
    assert baskets["us-memory-storage-ew"] == ["MU", "WDC", "STX", "SNDK"]
    assert {i["yahoo_symbol"] for i in config["indices"]} == {"^GSPC", "^NDX", "^IXIC"}
    assert config["research_only"] is True and config["actionable"] is False
    assert all(re.fullmatch(r"[a-z][a-z0-9-]*", b["series_id"]) for b in config["baskets"])


def test_existing_market_context_registry_is_untouched_and_indices_map_to_it(config):
    registry = json.loads((Path(__file__).resolve().parents[2] / "config" / "market_context.json").read_text("utf-8"))
    enabled = {i["context_id"] for i in registry["items"] if i["enabled"]}
    assert {i["market_context_id"] for i in config["indices"]} <= enabled
    assert not any(i["context_id"].startswith(("us-cpo", "us-memory")) for i in registry["items"])


def test_config_must_stay_research_only(tmp_path):
    bad = tmp_path / "c.json"
    bad.write_text(json.dumps({"research_only": True, "actionable": True}), "utf-8")
    with pytest.raises(ValueError):
        builder.load_config(bad)


def test_module_never_references_grading():
    text = "".join(p.read_text("utf-8") for p in APP_ROOT.glob("*.py"))
    assert "assign_grade" not in text and "SignalGrade" not in text and "send_mail" not in text


# ---- basket maths -----------------------------------------------------------------------------

def test_equal_weight_basket_is_mean_of_member_returns():
    a = make_frame(100 * np.cumprod(np.r_[1.0, np.full(9, 1.10)]), index=DAYS[:10])
    b = make_frame(100 * np.cumprod(np.r_[1.0, np.full(9, 1.00)]), index=DAYS[:10])
    c = make_frame(100 * np.cumprod(np.r_[1.0, np.full(9, 0.90)]), index=DAYS[:10])
    df, meta = compute.equal_weight_basket({"A": a, "B": b, "C": c}, ["A", "B", "C"], min_members=3)
    assert df["close"].iloc[0] == pytest.approx(100.0)
    # daily ret = (0.10 + 0.00 - 0.10) / 3 = 0
    assert df["close"].iloc[-1] == pytest.approx(100.0)
    assert meta["missing_members"] == []


def test_basket_expands_when_member_lists_and_respects_min_members():
    full = make_frame(growth(30, 0.01), index=DAYS[:30])
    late = make_frame(growth(10, 0.05), index=DAYS[20:30])
    frames = {"A": full, "B": full, "C": full, "D": late}
    df, meta = compute.equal_weight_basket(frames, ["A", "B", "C", "D"], min_members=3)
    assert df["n_members"].iloc[1] == 3 and df["n_members"].iloc[-1] == 4
    assert meta["presence"]["D"]["first"] == str(DAYS[20].date())
    only_two, meta2 = compute.equal_weight_basket(frames, ["A", "B"], min_members=3)
    assert only_two.empty and meta2["error"] == "fewer_than_min_members_overlap"
    assert compute.equal_weight_basket({}, ["A"], 3)[1]["error"] == "no_member_data"


def test_basket_flags_provisional_days_and_reports_missing_members():
    frames = {m: make_frame(growth(30, 0.01), index=DAYS[:30]) for m in "ABC"}
    frames["C"] = make_frame(growth(30, 0.01), index=DAYS[:30], provisional_last=True)
    df, meta = compute.equal_weight_basket(frames, ["A", "B", "C", "Z"], 3)
    assert df.empty and meta["error"] == "missing_requested_members"
    assert meta["missing_members"] == ["Z"]


# ---- return / risk helpers --------------------------------------------------------------------

def test_period_returns_ytd_and_drawdown_are_exact():
    idx = pd.bdate_range("2025-12-22", periods=30)
    close = pd.Series(np.arange(100.0, 130.0), index=idx)
    assert compute.period_return(close, 5) == pytest.approx(129 / 124 - 1)
    assert compute.period_return(close, 40) is None
    prior_year_close = float(close[close.index < "2026-01-01"].iloc[-1])
    assert compute.ytd_return(close) == pytest.approx(129 / prior_year_close - 1)
    assert compute.ytd_return(close[close.index >= "2026-01-01"]) is None  # never invent a base
    dd = compute.drawdown(pd.Series([100.0, 120.0, 90.0, 99.0], index=pd.bdate_range("2026-01-05", periods=4)))
    assert dd["current"] == pytest.approx(99 / 120 - 1) and dd["max"] == pytest.approx(-0.25)


def test_relative_strength_excess_and_overlap_guard():
    idx = pd.bdate_range("2025-01-01", periods=300)
    a = pd.Series(growth(300, 0.002), index=idx)
    b = pd.Series(growth(300, 0.001), index=idx)
    rs = compute.relative_strength(a, b)
    assert rs["excess"]["1m"] == pytest.approx(compute.period_return(a, 21) - compute.period_return(b, 21), abs=1e-5)
    assert rs["daily_return_corr"] is not None
    assert compute.relative_strength(a.head(10), b.head(10)) is None


def test_atr_bucket_uses_repo_fixed_v1_bands_and_baskets_skip_wyckoff():
    calm = make_frame(growth(120, 0.0), spread=0.004)       # ATR% ~0.8% -> low
    wild = make_frame(growth(120, 0.0), spread=0.05)        # ATR% ~10% -> extreme
    low = compute.structure_columns(calm, with_volume=True)
    high = compute.structure_columns(wild, with_volume=False)
    assert low["atr_rule"] == "atr_pct_fixed_v1" and low["atr_risk_bucket"] == "low"
    assert high["atr_risk_bucket"] == "extreme"
    assert high["wyckoff_phase"] == "not_computed"
    assert compute.structure_columns(calm.head(5), with_volume=True)["atr_risk_bucket"] == "unknown"


def test_clean_removes_non_finite_numbers():
    assert compute.clean(float("nan")) is None and compute.clean(float("inf")) is None
    assert compute.clean(np.float64(1.23456789), 3) == 1.235
    assert compute.clean(np.int64(3)) == 3


# ---- provider hygiene -------------------------------------------------------------------------

def _raw(close_last=np.nan):
    idx = pd.to_datetime(["2026-11-11", "2026-11-12", "2026-11-13"]).tz_localize("America/New_York")
    return pd.DataFrame({"Open": [10.0, 11.0, 12.0], "High": [11.0, 12.0, 14.0], "Low": [9.0, 10.0, 11.0],
                         "Close": [10.5, 11.5, close_last], "Adj Close": [10.5, 11.5, close_last],
                         "Volume": [1.0, 2.0, 3.0]}, index=idx)


def test_provisional_close_only_inside_day_range_and_flagged():
    filled, fills = fill_provisional_close(_raw(), 13.0)
    assert fills and filled.iloc[-1]["close_source"] == CLOSE_SOURCE_PROVISIONAL
    frame, dropped = adjust_frame(filled)
    assert frame["close"].iloc[-1] == 13.0 and not dropped
    assert frame["close_source"].iloc[-1] == CLOSE_SOURCE_PROVISIONAL
    outside, none = fill_provisional_close(_raw(), 99.0)   # outside high/low: never invented
    assert not none
    frame2, dropped2 = adjust_frame(outside)
    assert len(frame2) == 2 and dropped2 == [{"date": "2026-11-13", "reason": "missing_or_nonpositive_close"}]
    assert fill_provisional_close(_raw(), None)[1] == []


def test_adjust_frame_applies_adj_factor_and_drops_duplicates():
    raw = pd.DataFrame({"Open": [10.0, 10.0], "High": [11.0, 11.0], "Low": [9.0, 9.0], "Close": [10.0, 10.0],
                        "Adj Close": [5.0, 5.0], "Volume": [1, 1]}, index=pd.to_datetime(["2026-01-02", "2026-01-02"]))
    frame, _ = adjust_frame(raw)
    assert len(frame) == 1 and frame["high"].iloc[0] == pytest.approx(5.5) and frame["close"].iloc[0] == 5.0


def test_csv_provider_reads_utf8_tidy_csv_and_labels_provisional(tmp_path):
    path = tmp_path / "t.csv"
    path.write_bytes(("date,ticker,Open,High,Low,Close,Adj Close,Volume,close_source\n"
                      "2026-11-12,AAA,1,2,0.5,1.5,1.5,10,yfinance_adj_or_close\n"
                      "2026-11-13,AAA,1.5,2,1,1.8,1.8,10,yfinance_fast_info_last_price_provisional\n").encode("utf-8"))
    result = CsvProvider(path).fetch(["AAA", "BBB"], date(2026, 1, 1), date(2026, 11, 14))
    assert result.frames["AAA"]["close_source"].iloc[-1] == CLOSE_SOURCE_PROVISIONAL
    assert result.provisional == [{"ticker": "AAA", "date": "2026-11-13"}]
    assert [a["ok"] for a in result.audit] == [True, False] and result.audit[1]["reason"] == "ticker_not_in_csv"
    assert result.source_label.startswith("csv:")


# ---- builder ----------------------------------------------------------------------------------

def test_build_produces_valid_research_only_part(config, all_frames):
    result = builder.build(config, FakeProvider(all_frames), today=date(2026, 11, 14), now=NOW)
    part = result.part
    assert result.problems == [] and part["availability"] == "available"
    assert part["research_only"] is True and part["actionable"] is False and part["changes_grade"] is False
    assert part["calibration_status"] == "not_calibrated" and part["as_of"] == "2026-11-13"
    ids = [s["series_id"] for s in part["series"]]
    assert ids == ["us-cpo-optical-broad-ew", "us-cpo-optical-narrow-ew", "us-memory-storage-ew",
                   "us-sp500", "us-nasdaq-100", "us-nasdaq-composite"]
    spx = part["series"][3]
    assert set(spx["rs"]) == {"vs_ndx"}                 # no self-comparison
    assert set(part["series"][0]["rs"]) == {"vs_spx", "vs_ndx"}
    assert spx["official_index"] is True and part["series"][0]["official_index"] is False
    assert all(len(s["spark"]) <= contracts.MAX_SPARK_POINTS for s in part["series"])
    assert not result.history.empty and set(result.history["series_id"]) == set(ids)
    json.dumps(part, allow_nan=False)                    # strict JSON, no NaN


def test_build_reports_partial_failed_tickers_and_short_baskets(config, all_frames):
    result = builder.build(config, FakeProvider(all_frames, failed={"SNDK", "^IXIC"}), today=date(2026, 11, 14), now=NOW)
    part = result.part
    assert part["availability"] == "partial" and part["failed_tickers"] == ["SNDK", "^IXIC"]
    memory = next(s for s in part["series"] if s["series_id"] == "us-memory-storage-ew")
    assert memory["available"] is False and memory["reason"] == "missing_requested_members"
    ixic = next(s for s in part["series"] if s["series_id"] == "us-nasdaq-composite")
    assert ixic["available"] is False and ixic["reason"] == "provider_returned_no_data"
    result2 = builder.build(config, FakeProvider(all_frames, failed={"SNDK", "STX"}), today=date(2026, 11, 14), now=NOW)
    short = next(s for s in result2.part["series"] if s["series_id"] == "us-memory-storage-ew")
    assert short["available"] is False and short["reason"] == "missing_requested_members"
    assert result2.problems == []


def test_build_nothing_available_is_unavailable_not_zero(config):
    result = builder.build(config, FakeProvider({}), today=date(2026, 11, 14), now=NOW)
    assert result.part["availability"] == "unavailable" and result.part["as_of"] is None
    assert all(s["available"] is False for s in result.part["series"]) and result.problems == []


def test_build_marks_provisional_close_and_as_of_truncates(config, all_frames):
    frames = deepcopy(all_frames)
    frames["LITE"] = make_frame(growth(len(DAYS), 0.002), provisional_last=True)
    prov = [{"ticker": "LITE", "date": "2026-11-13"}]
    result = builder.build(config, FakeProvider(frames, provisional=prov), today=date(2026, 11, 14), now=NOW)
    broad = result.part["series"][0]
    assert broad["provisional_last_close"] is False and result.part["provisional_closes"] == []
    assert broad["as_of"] == "2026-11-12"
    assert result.part["excluded_provisional_observations"] == [{**prov[0], "excluded_from_metrics": True}]
    assert next(m for m in broad["members"] if m["ticker"] == "LITE")["as_of"] == "2026-11-12"
    older = builder.build(config, FakeProvider(frames), today=date(2026, 11, 14), as_of=date(2026, 6, 30), now=NOW)
    assert older.part["as_of"] <= "2026-06-30" and older.part["series"][0]["provisional_last_close"] is False


def test_write_outputs_is_utf8_lf_and_contains_backfill_from_start_date(config, all_frames, tmp_path):
    result = builder.build(config, FakeProvider(all_frames), today=date(2026, 11, 14), now=NOW)
    files = builder.write_outputs(result, tmp_path / "out")
    raw = Path(files["snapshot"]).read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r\n" not in raw and b"\xff\xfe" not in raw[:2]
    loaded = json.loads(raw.decode("utf-8"))
    assert loaded["series"][0]["label"] == "美股 CPO/光模块（宽口径等权）"
    history = pd.read_csv(files["history"], encoding="utf-8")
    assert history["date"].min() >= config["start_date"] and set(history.columns) >= {"date", "series_id", "close"}


# ---- contract ---------------------------------------------------------------------------------

@pytest.fixture()
def part(config, all_frames):
    return builder.build(config, FakeProvider(all_frames), today=date(2026, 11, 14), now=NOW).part


@pytest.mark.parametrize("mutate,needle", [
    (lambda p: p.update(actionable=True), "actionable"),
    (lambda p: p.update(changes_grade=True), "changes_grade"),
    (lambda p: p.update(calibration_status="calibrated"), "calibration_status"),
    (lambda p: p.update(research_only=False), "research_only"),
    (lambda p: p.update(availability="great"), "availability"),
    (lambda p: p["series"][0].update(actionable=True), "actionable"),
    (lambda p: p["series"][0].update(atr_risk_bucket="spicy"), "atr_risk_bucket"),
    (lambda p: p["series"][0]["returns"].update({"1w": float("nan")}), "finite"),
    (lambda p: p["series"][0]["returns"].update({"5y": 0.1}), "returns"),
    (lambda p: p["series"].append(deepcopy(p["series"][0])), "duplicate"),
    (lambda p: p["series"][0].update(spark=[["2026-01-01"]]), "spark"),
])
def test_contract_rejects_boundary_violations(part, mutate, needle):
    bad = deepcopy(part)
    mutate(bad)
    assert any(needle in problem for problem in contracts.validate_part(bad))


def test_contract_requires_reason_for_unavailable_series(part):
    bad = deepcopy(part)
    bad["series"][0] = {**bad["series"][0], "available": False, "reason": ""}
    assert any("reason" in p for p in contracts.validate_part(bad))
    assert contracts.validate_part("nope") and contracts.validate_part(part) == []


# ---- store ------------------------------------------------------------------------------------

def test_store_is_opt_in_and_rejects_bad_files(part, tmp_path):
    assert store.load_for_bundle({}) is None and store.configured_path({}) is None
    good = tmp_path / "s.json"
    good.write_bytes(json.dumps(part, ensure_ascii=False).encode("utf-8"))
    assert store.load_for_bundle({store.ENV_SNAPSHOT_PATH: str(good)}) == part
    assert store.load_snapshot_file(tmp_path / "missing.json") == (None, "us_markets_research_file_missing")
    bad = tmp_path / "bad.json"
    bad.write_bytes(json.dumps({**part, "actionable": True}).encode("utf-8"))
    assert store.load_snapshot_file(bad) == (None, "us_markets_research_contract_invalid")
    garbage = tmp_path / "g.json"
    garbage.write_bytes(b"\xff\xfe{")
    assert store.load_snapshot_file(garbage) == (None, "us_markets_research_file_unreadable")


def test_envelope_flags_old_source_without_hiding_it(part):
    fresh = store.read_envelope(part, None, now=datetime(2026, 11, 14, tzinfo=timezone.utc))
    old = store.read_envelope(part, None, now=datetime(2026, 11, 30, tzinfo=timezone.utc))
    assert fresh["source_stale"] is False and old["source_stale"] is True and old["research"] is part
    none = store.read_envelope(None, "us_markets_research_not_published")
    assert none["availability"] == "unpublished" and none["available"] is False and none["actionable"] is False


# ---- bundle contract + reader + API -----------------------------------------------------------

GENERATED, EXPIRES = "2026-11-14T03:30:00Z", "2026-11-14T05:30:00Z"


def make_bundle(us_part=None, sequence=9):
    parts = {"overview": {"rows": [], "generated_at": GENERATED}, "details": {}, "charts": {}, "sectors": {"sectors": []}}
    if us_part is not None:
        parts["us_markets_research"] = us_part
    return {"manifest": {"contract_version": CONTRACT_VERSION, "code_sha": "a" * 40, "config_hash": "c" * 64,
                         "sequence": sequence, "generated_at": GENERATED, "expires_at": EXPIRES, "actionable": False,
                         "data_origin": "local_research", "universe": ["510300.SH"],
                         "parts_hashes": compute_parts_hashes(parts)}, "parts": parts}


def test_bundle_without_the_part_is_unchanged_and_valid():
    assert verify_bundle_integrity(make_bundle()) is True


def test_bundle_accepts_valid_part_and_rejects_invalid_or_tampered(part):
    assert verify_bundle_integrity(make_bundle(part)) is True
    bad = deepcopy(part)
    bad["series"][0]["atr_risk_bucket"] = "spicy"
    assert verify_bundle_integrity(make_bundle(bad)) is False
    live = deepcopy(part)
    live["actionable"] = True
    assert verify_bundle_integrity(make_bundle(live)) is False
    tampered = make_bundle(part)
    tampered["parts"]["us_markets_research"] = {**part, "as_of": "2020-01-01"}
    assert verify_bundle_integrity(tampered) is False


def _client(settings, db):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


def test_reader_and_api_serve_published_part_from_bundle(tmp_path, part):
    root = LocalDisplayStore(tmp_path / "store")
    root.publish(make_bundle(part), now=datetime(2026, 11, 14, 4, tzinfo=timezone.utc))
    root2 = LocalDisplayStore(tmp_path / "store2")
    root2.publish(make_bundle(None, sequence=3), now=datetime(2026, 11, 14, 4, tzinfo=timezone.utc))
    view = LocalDisplayReader(root).read_us_markets_research_view("9", now=NOW)
    assert view["available"] is True and view["research"]["series"][0]["series_id"] == "us-cpo-optical-broad-ew"
    assert view["provider_called"] is False and view["actionable"] is False and view["generation"] == 9
    missing = LocalDisplayReader(root2).read_us_markets_research_view("3", now=NOW)
    assert missing["available"] is False and missing["reason"] == "us_markets_research_not_published"
    assert LocalDisplayReader(root2).read_us_markets_research_view("77", now=NOW)["reason"] == "local_display_generation_unavailable"
    settings = Settings(_env_file=None, workspace_research_source="local_bundle", auth_enabled=False,
                        local_display_v2_store_root=str(root.store_dir),
                        shadow_sync_code_sha="a" * 40, shadow_sync_config_hash="c" * 64)
    engine = create_engine("sqlite://")
    with Session(engine) as db, _client(settings, db) as client:
        response = client.get("/api/workspace/us-markets-research?generation=9")
        assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
        body = response.json()
        assert body["research"]["research_only"] is True and body["changes_grade"] is False
        assert client.get("/api/workspace/us-markets-research?generation=12").json()["reason"] == "local_display_generation_unavailable"
    engine.dispose()


def test_api_file_mode_is_unpublished_by_default_and_serves_a_valid_file(monkeypatch, tmp_path, part):
    settings = Settings(_env_file=None, auth_enabled=False)
    engine = create_engine("sqlite://")
    monkeypatch.delenv(store.ENV_SNAPSHOT_PATH, raising=False)
    with Session(engine) as db, _client(settings, db) as client:
        body = client.get("/api/workspace/us-markets-research").json()
        assert body["reason"] == "us_markets_research_not_published" and body["research"] is None
        path = tmp_path / "snap.json"
        path.write_bytes(json.dumps(part, ensure_ascii=False).encode("utf-8"))
        monkeypatch.setenv(store.ENV_SNAPSHOT_PATH, str(path))
        ok = client.get("/api/workspace/us-markets-research").json()
        assert ok["available"] is True and ok["research_source"] == "snapshot_file"
        path.write_bytes(b"{}")
        bad = client.get("/api/workspace/us-markets-research").json()
        assert bad["available"] is False and bad["reason"] == "us_markets_research_contract_invalid"
    engine.dispose()


def test_provisional_close_excluded_even_when_it_would_change_atr_and_returns(config, all_frames):
    a = builder.build(config, FakeProvider(all_frames), as_of=date(2026,11,12), now=NOW)
    bad = deepcopy(all_frames)
    bad['LITE'].loc[DAYS[-1], ['open','high','low','close']] = [9999,19999,1,9999]
    bad['LITE'].loc[DAYS[-1], 'close_source'] = CLOSE_SOURCE_PROVISIONAL
    b = builder.build(config, FakeProvider(bad), today=date(2026,11,14), now=NOW)
    for index in [0,1]:
        for key in ['as_of','returns','atr_pct','drawdown','level']:
            assert a.part['series'][index][key] == b.part['series'][index][key]


def test_regular_sndk_start_excludes_when_issued_and_no_prior_entity_history(config, all_frames):
    result = builder.build(config, FakeProvider(all_frames), today=date(2026,11,14), now=NOW)
    audit = next(q for q in result.part['quality_audit'] if q['ticker']=='SNDK')
    assert audit['regular_trading_start']=='2025-02-24'
    assert audit['excluded_pre_regular_rows'] > 0
    mem = result.part['series'][2]
    sndk = next(m for m in mem['members'] if m['ticker']=='SNDK')
    assert sndk['first_date'] == '2025-02-24'
    assert mem['membership_policy'].endswith('not_point_in_time')


def test_missing_internal_session_does_not_create_zero_return_or_reweight():
    frames={m:make_frame(growth(30,.01), index=DAYS[:30]) for m in 'ABC'}
    frames['C'].loc[DAYS[20],'close']=float('nan')
    out, meta=compute.equal_weight_basket(frames,list('ABC'),3)
    assert out.index[-1]==DAYS[19]
    assert meta['first_gap_date']==str(DAYS[20].date())


def test_common_window_counts_adjacent_daily_pairs_not_compressed_returns():
    idx=pd.bdate_range('2026-01-01',periods=40)
    a=pd.Series(np.arange(100.,140.),index=idx)
    b=pd.Series(np.arange(200.,240.),index=idx).drop(idx[20])
    x=compute.relative_strength(a,b)
    assert x['n_price_pairs']==39
    assert x['n_union_sessions']==40 and x['n_missing_sessions']==1
    assert x['n_daily_return_pairs']==37
    assert x['first_overlap']==str(idx[0].date()) and x['last_overlap']==str(idx[-1].date())
    assert x['excess']['1m'] is None


def test_no_adjustment_factor_fill_or_missing_adjusted_close_fallback():
    raw=_raw(12.5)
    raw.loc[raw.index[1],'Adj Close']=float('nan')
    frame,dropped=adjust_frame(raw)
    assert len(dropped)==1 and len(frame)==2
    frame,dropped=adjust_frame(raw.drop(columns=['Adj Close']))
    assert frame.empty and len(dropped)==3


def test_yfinance_never_accesses_live_quote_to_replace_missing_close(monkeypatch):
    from types import SimpleNamespace
    import sys
    def forbidden_quote(*args, **kwargs):
        raise AssertionError("live quote must never be accessed")
    monkeypatch.setitem(sys.modules, 'yfinance', SimpleNamespace(
        download=lambda *a, **k: _raw(), Ticker=forbidden_quote, __version__='test'))
    result=providers.YFinanceProvider().fetch(['AAA'],date(2026,11,1),date(2026,11,14))
    assert result.frames['AAA'].index[-1] == pd.Timestamp('2026-11-12')
    assert result.provisional==[] and result.audit[0]['reason']=='dropped_rows=1'


def test_old_snapshot_without_confirmed_price_policy_is_rejected(part):
    old=deepcopy(part)
    old.pop('price_policy')
    assert any('price_policy' in x for x in contracts.validate_part(old))
    bad=deepcopy(part)
    bad['series'][0]['provisional_last_close']=True
    assert any('provisional_last_close' in x for x in contracts.validate_part(bad))


def test_producer_opt_in_attaches_confirmed_research_part(part, tmp_path):
    # Real producer, isolated process + DB. Never mutate pytest's session-scoped
    # bootstrap/board state: that corrupts unrelated snapshot/job tests later.
    import os
    import subprocess
    import sys
    repo = Path(__file__).resolve().parents[2]
    snapshot = tmp_path / 'confirmed.json'
    snapshot.write_text(json.dumps(part, ensure_ascii=False), encoding='utf-8')
    code = """
import json,sys
from app.core.config import get_settings
from app.db.session import init_db,session_scope
from app.services.task_service import TaskService
from app.workspace.local_compute import export_local_v2
from app.workspace.local_display_contract import verify_bundle_integrity
init_db()
settings=get_settings()
with session_scope() as db:
    TaskService(settings).run(db,'bootstrap',lookback_days=60,report=False)
    TaskService(settings).run(db,'refresh_decision_board')
result=export_local_v2(settings,sequence=19,code_sha='b'*40,
    universe=['510300.SH'],private_research=True,unavailable_parts=['sectors','market_context'])
assert verify_bundle_integrity(result)
assert result['parts']['us_markets_research']['price_policy'].startswith('provider_adjusted')
"""
    env = {**os.environ, 'PYTHONPATH': str(repo / 'backend'), 'PYTHONUTF8': '1',
           'APP_ENV': 'test', 'AUTH_ENABLED': 'false', 'MARKET_PROVIDER': 'mock',
           'ALLOW_MOCK_FALLBACK': 'false', 'AUTO_CREATE_SCHEMA': 'true',
           'LLM_ENABLED': 'false', 'ANALYSIS_ENABLED': 'false',
           'DATABASE_URL': 'sqlite:///' + (tmp_path / 'producer.sqlite3').as_posix(),
           'REPORTS_DIR': str(tmp_path / 'reports'), store.ENV_SNAPSHOT_PATH: str(snapshot)}
    run = subprocess.run([sys.executable, '-c', code], cwd=repo, env=env,
                         capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stderr[-1500:]


def test_whole_group_common_samples_do_not_claim_full_membership_since_2018(config, all_frames):
    result=builder.build(config,FakeProvider(all_frames),today=date(2026,11,14),now=NOW)
    samples=result.part['common_samples']
    assert samples['all_current_members_adjacent_return_overlap']['first']=='2025-02-25'
    assert samples['all_current_members_adjacent_return_overlap']['n_sessions'] < samples['available_series_level_overlap']['n_sessions']

"""The published optional context status must survive the actual read path."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.workspace.api import router
from app.workspace.local_display_contract import CONTRACT_VERSION, compute_parts_hashes
from app.workspace.local_display_read import LocalDisplayReader, LocalDisplayStore
from app.workspace.shadow_bundle import canonical, digest


GENERATED = "2026-10-12T06:30:00Z"
EXPIRES = "2026-10-12T08:30:00Z"
READ_AT = datetime(2026, 10, 12, 9, tzinfo=timezone.utc)
ITEM = {"context_id": "cn-csi300", "context_kind": "index", "label": "沪深300",
        "observed_value": 4000, "source_timestamp": "2026-10-09T15:00:00+08:00",
        "freshness": "historical", "source": "fixture", "actionable": False}


def publish(store, part=None, sequence=7):
    parts = {"overview": {"rows": [], "generated_at": GENERATED},
             "details": {}, "charts": {}, "sectors": {"sectors": []}}
    if part is not None:
        parts["market_context"] = part
    bundle = {"manifest": {"contract_version": CONTRACT_VERSION, "code_sha": "a" * 40,
                           "config_hash": "c" * 64, "sequence": sequence,
                           "generated_at": GENERATED, "expires_at": EXPIRES,
                           "actionable": False, "data_origin": "local_research", "universe": ["510300.SH"],
                           "parts_hashes": compute_parts_hashes(parts)}, "parts": parts}
    store.publish(bundle, now=datetime(2026, 10, 12, 7, tzinfo=timezone.utc))
    return bundle


def install_hashed_bad_context(store, availability):
    bad = deepcopy(publish(store, {"items": [ITEM], "availability": "available"}))
    bad["parts"]["market_context"]["availability"] = availability
    bad["manifest"]["parts_hashes"] = compute_parts_hashes(bad["parts"])
    identity = digest(bad["manifest"])
    original = next(store.store_dir.glob("bundle_7_*.json"))
    target = store.store_dir / f"bundle_7_{identity[:16]}.json"
    target.write_bytes(canonical(bad))
    pointer = json.loads(store.latest_link.read_bytes())
    pointer.update(bundle_file=target.name, bundle_id=identity)
    pointer["accepted"][-1]["bundle_id"] = identity
    store.latest_link.write_bytes(canonical(pointer))
    original.unlink()


@pytest.mark.parametrize("availability", [{"state": "available"}, ["available"], 1, "unexpected", None, ""])
def test_hashed_bad_context_on_disk_is_unavailable_not_promoted(tmp_path, availability):
    store = LocalDisplayStore(tmp_path / "store")
    install_hashed_bad_context(store, availability)

    assert store.load_bundle("7") is None
    view = LocalDisplayReader(store).read_market_context_view("7", now=READ_AT)
    assert view["availability"] == "unavailable"
    assert view["reason"] == "local_display_generation_unavailable"
    assert view["available"] is False and view["items"] == []
    assert LocalDisplayReader(store).read_market_context("7") is None


@pytest.mark.parametrize("availability", [{"state": "available"}, ["available"], 1, "unexpected", None, ""])
@pytest.mark.parametrize("endpoint,item_key", [("market-context", "latest_view"), ("indexes", "items")])
def test_hashed_bad_context_gets_return_unavailable_not_500(tmp_path, availability, endpoint, item_key):
    store = LocalDisplayStore(tmp_path / "store")
    install_hashed_bad_context(store, availability)
    settings = Settings(_env_file=None, workspace_research_source="local_bundle", auth_enabled=False,
                        local_display_v2_store_root=str(store.store_dir),
                        shadow_sync_code_sha="a" * 40, shadow_sync_config_hash="c" * 64)
    engine = create_engine("sqlite://")
    with Session(engine) as db:
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(f"/api/workspace/{endpoint}?generation=7")
            assert response.status_code == 200
            view = response.json()
            assert view["availability"] == "unavailable"
            assert view["reason"] == "local_display_generation_unavailable"
            assert view["available"] is False and view[item_key] == []
            assert response.headers["cache-control"] == "private, no-store"
    engine.dispose()


def test_legacy_context_without_status_keeps_default_available(tmp_path):
    store = LocalDisplayStore(tmp_path / "store")
    publish(store, {"items": [ITEM]})
    view = LocalDisplayReader(store).read_market_context_view("7", now=READ_AT)
    assert view["availability"] == "available"
    assert view["available"] is True
    assert view["items"] == [ITEM]


@pytest.mark.parametrize("part", [
    {"items": [ITEM], "availability": "available"},
    {"items": [], "availability": "unavailable", "reason": "optional_refresh_failed"},
    {"items": [ITEM], "availability": "partial", "reason": "coverage_incomplete"},
    {"items": [ITEM], "availability": "carried_forward", "reason": "fast_slot_reuses_same_day_refresh",
     "refreshed_in_slot": False, "refreshed_at": "2026-10-12T01:30:00Z",
     "source_as_of": "2026-10-09"},
])
def test_reader_preserves_empty_partial_and_carried_context(tmp_path, part):
    store = LocalDisplayStore(tmp_path / "store")
    original = publish(store, part)
    reader = LocalDisplayReader(store)
    view = reader.read_market_context_view(generation="7", now=READ_AT)
    assert view["read_contract"] == "local-display-context-read-v1"
    assert view["items"] == part["items"]
    for key in part.keys() - {"items"}:
        assert view[key] == part[key]
    assert view["available"] is bool(part["items"])
    assert view["generation"] == 7
    assert view["as_of"] == view["generated_at"] == GENERATED
    assert view["expires_at"] == EXPIRES
    assert view["read_at"] == READ_AT.isoformat()
    assert view["is_stale"] is True
    assert view["is_expired"] is True
    assert view["actionable"] is False
    assert view["research_only"] is True
    assert view["calibration_status"] == "not_calibrated"
    assert view["research_source"] == "local_bundle"
    assert view["index_history_available"] is False
    assert store.load_bundle("7")["parts"] == original["parts"]
    # Existing list consumers retain their contract.
    assert reader.read_market_context("7") == (part["items"] or None)


def test_reader_distinguishes_unpublished_part_and_retired_generation(tmp_path):
    store = LocalDisplayStore(tmp_path / "store")
    publish(store)
    reader = LocalDisplayReader(store)
    unpublished = reader.read_market_context_view("7", now=READ_AT)
    assert unpublished["availability"] == "unpublished"
    assert unpublished["reason"] == "market_context_not_published"
    assert unpublished["generation"] == 7
    assert unpublished["source_as_of"] is None
    retired = reader.read_market_context_view("6", now=READ_AT)
    assert retired["availability"] == "unavailable"
    assert retired["reason"] == "local_display_generation_unavailable"
    assert retired["generation"] is None
    assert retired["requested_generation"] == "6"
    assert retired["generated_at"] is None
    assert retired["as_of"] is None
    assert retired["items"] == []


def test_read_time_staleness_preserves_historical_identity_and_source_dates(tmp_path):
    store = LocalDisplayStore(tmp_path / "store")
    publish(store, {"items": [ITEM]})
    reader = LocalDisplayReader(store, code_sha="b" * 40, config_hash="d" * 64)
    assert reader.read_market_context_view(now=READ_AT)["generation"] is None
    pinned = reader.read_market_context_view("7", now=datetime(2026, 10, 12, 7, tzinfo=timezone.utc))
    assert pinned["historical_identity"] is True
    assert pinned["is_stale"] is True
    assert pinned["is_expired"] is False
    assert pinned["items"][0]["source_timestamp"] == ITEM["source_timestamp"]
    matched = LocalDisplayReader(store).read_market_context_view("7", now=datetime(2026, 10, 12, 7, tzinfo=timezone.utc))
    assert matched["is_stale"] is False


@pytest.mark.parametrize("part", [
    {"items": [], "availability": "unavailable", "reason": "optional_refresh_failed"},
    {"items": [ITEM], "availability": "carried_forward", "reason": "fast_slot_reuses_same_day_refresh",
     "refreshed_at": "2026-10-12T01:30:00Z", "refreshed_in_slot": False, "source_as_of": "2026-10-09"},
])
def test_context_http_gets_keep_status_without_provider_or_sql(tmp_path, monkeypatch, part):
    from app.providers import factory
    from app.services.market_context_service import MarketContextService
    from app.workspace import index_history

    def forbidden(*args, **kwargs):
        pytest.fail("local context GET called Provider or SQL")

    store = LocalDisplayStore(tmp_path / "store")
    publish(store, part)
    settings = Settings(_env_file=None, workspace_research_source="local_bundle", auth_enabled=False,
                        local_display_v2_store_root=str(store.store_dir),
                        shadow_sync_code_sha="a" * 40, shadow_sync_config_hash="c" * 64)
    monkeypatch.setattr(factory, "build_provider", forbidden)
    monkeypatch.setattr(MarketContextService, "latest_view", forbidden)
    monkeypatch.setattr(index_history, "read", forbidden)
    engine = create_engine("sqlite://")
    event.listen(engine, "before_cursor_execute", forbidden)
    with Session(engine) as db:
        monkeypatch.setattr(db, "commit", forbidden)
        monkeypatch.setattr(db, "flush", forbidden)
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app) as client:
            for endpoint, item_key in (("market-context", "latest_view"), ("indexes", "items")):
                response = client.get(f"/api/workspace/{endpoint}?generation=7")
                assert response.status_code == 200
                view = response.json()
                assert view["read_contract"] == "local-display-context-read-v1"
                assert view["availability"] == part["availability"]
                assert view["reason"] == part["reason"]
                assert view["generation"] == 7
                assert view["as_of"] == view["generated_at"] == GENERATED
                assert view["is_stale"] is True
                assert view["index_history_available"] is False
                assert view["provider_called"] is view["actionable"] is False
                assert view["research_only"] is True
                assert view["calibration_status"] == "not_calibrated"
                assert len(view[item_key]) == len(part["items"])
                for actual, expected in zip(view[item_key], part["items"], strict=True):
                    assert {key: actual[key] for key in expected} == expected
                for key in ("source_as_of", "refreshed_at", "refreshed_in_slot"):
                    if key in part:
                        assert view[key] == part[key]
                assert response.headers["cache-control"] == "private, no-store"
            missing = client.get("/api/workspace/market-context?generation=6").json()
            assert missing["generation"] is None
            assert missing["reason"] == "local_display_generation_unavailable"
            assert missing["latest_view"] == []
            assert client.get("/api/workspace/indexes/cn-csi300/chart").status_code == 404
    engine.dispose()

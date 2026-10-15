"""Receiver admission regressions; synthetic temporary bundles only."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.workspace.local_display_read import LocalDisplayStore
from app.workspace.shadow_api import _publish_decoded
from app.workspace.shadow_bundle import canonical
from test_shadow_chunks import _bundle


def candidate(sequence=1, *, generated=None, expires=None):
    now = datetime.now(timezone.utc)
    value = _bundle(sequence, pad=1)
    value["manifest"].update(generated_at=(generated or now - timedelta(seconds=1)).isoformat(),
                             expires_at=(expires or now + timedelta(hours=1)).isoformat())
    return value


@pytest.mark.parametrize("kind", ["expired", "future"])
def test_new_invalid_time_never_activates_or_replaces_previous(tmp_path, kind):
    store = LocalDisplayStore(tmp_path)
    store.publish(candidate(1))
    before = (tmp_path / "latest.json").read_bytes()
    now = datetime.now(timezone.utc)
    value = candidate(2, generated=now - timedelta(hours=2), expires=now - timedelta(hours=1)) if kind == "expired" else candidate(2, generated=now + timedelta(minutes=1))
    with pytest.raises(ValueError):
        store.publish(value)
    assert (tmp_path / "latest.json").read_bytes() == before
    assert store.load_bundle()["manifest"]["sequence"] == 1


def test_historical_read_and_same_identity_retry_do_not_reactivate(tmp_path):
    store = LocalDisplayStore(tmp_path)
    now = datetime.now(timezone.utc)
    value = candidate()
    store.publish(value, now=now)
    assert store.publish(value, now=now + timedelta(days=1))["status"] == "already_accepted"
    assert store.load_bundle()["manifest"]["sequence"] == 1


@pytest.mark.parametrize("sha,config", [("", ""), ("b" * 40, "c" * 64), ("a" * 40, "b" * 64)])
def test_v2_http_publish_requires_explicit_approved_identity(tmp_path, sha, config):
    settings = SimpleNamespace(local_display_v2_store_root=tmp_path / "v2", local_display_v2_max_bytes=65536,
                               shadow_sync_code_sha=sha, shadow_sync_config_hash=config)
    with pytest.raises(ValueError):
        _publish_decoded(canonical(candidate()), None, settings)
    assert not (tmp_path / "v2" / "latest.json").exists()


def test_naive_manifest_times_rejected(tmp_path):
    value = candidate()
    value["manifest"]["generated_at"] = "2026-10-12T06:30:00"
    value["manifest"]["expires_at"] = "2099-10-12T06:30:00"
    with pytest.raises(ValueError):
        LocalDisplayStore(tmp_path).publish(value)


@pytest.mark.parametrize("mutation", ["period_scope", "future_bar", "private_field", "unknown_part"])
def test_optional_period_charts_keep_time_scope_and_privacy_contract(tmp_path, mutation):
    from app.workspace.local_display_contract import compute_parts_hashes
    value = candidate()
    period = {"interval": "1w", "bars": []}
    value["parts"]["chart_periods"] = {"510300.SH": {"1w": period}}
    if mutation == "period_scope":
        period["interval"] = "5m"
    elif mutation == "future_bar":
        period["bars"] = [{"date": "2099-01-01", "open": 1, "close": 1}]
    elif mutation == "private_field":
        period["session_secret"] = "synthetic-private-field"
    else:
        value["parts"]["unreviewed_payload"] = {}
    value["manifest"]["parts_hashes"] = compute_parts_hashes(value["parts"])
    with pytest.raises(ValueError):
        LocalDisplayStore(tmp_path).publish(value)


def test_declared_weekly_chart_is_valid_without_loosening_daily_scope(tmp_path):
    from app.workspace.local_display_contract import compute_parts_hashes
    from app.workspace.shadow_projection import validate_public_chart
    value = candidate()
    weekly = {"interval": "1w", "bars": []}
    with pytest.raises(ValueError):
        validate_public_chart(weekly)
    value["parts"]["chart_periods"] = {"510300.SH": {"1w": weekly}}
    value["manifest"]["parts_hashes"] = compute_parts_hashes(value["parts"])
    assert LocalDisplayStore(tmp_path).publish(value)["status"] == "accepted"

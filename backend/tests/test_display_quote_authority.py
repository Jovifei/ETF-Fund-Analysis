"""One authority for published-quote freshness across every local-bundle consumer.

Every case derives its clock inside the test: a module-level timestamp would age past
the 600-second observation window while the full suite is still running.
"""
from datetime import datetime, timedelta, timezone

from app.core.config import Settings
from app.workspace import read_model
from app.workspace.local_display_contract import compute_parts_hashes
from app.workspace.local_display_read import LocalDisplayReader, LocalDisplayStore


def bundle(now, sequence, quote, *, expires_in=timedelta(hours=1)):
    parts = {
        "overview": {"rows": [], "generated_at": now.isoformat()},
        "details": {"510300.SH": {"quote": quote}},
        "charts": {},
        "sectors": {"sectors": []},
        "market_context": {"items": [], "availability": "unavailable", "reason": "optional_refresh_failed"},
    }
    return {"manifest": {"contract_version": "local-display-v2", "code_sha": "a" * 40,
                         "config_hash": "b" * 64, "sequence": sequence,
                         "generated_at": now.isoformat(), "expires_at": (now + expires_in).isoformat(),
                         "actionable": False, "universe": ["510300.SH"],
                         "parts_hashes": compute_parts_hashes(parts)}, "parts": parts}


def settings_for(root):
    return Settings(_env_file=None, workspace_research_source="local_bundle", market_provider="mock",
                    local_display_v2_store_root=str(root), local_display_v2_max_bytes=64 * 1024 * 1024,
                    shadow_sync_code_sha="a" * 40, shadow_sync_config_hash="b" * 64)


def quote(now, *, age):
    return {"status": "observed", "is_realtime": True, "price": 3.5,
            "source_time": (now - age).isoformat(), "actionable": False}


def test_detail_and_pricing_agree_when_quote_outlives_the_observation_window(tmp_path):
    """A bundle inside its publication TTL can still hold hours-old quotes (weekend).

    The detail page and the watchlist/holdings pricing path must reach the same
    verdict from one threshold instead of two independent ones.
    """
    now = datetime.now(timezone.utc)
    LocalDisplayStore(tmp_path).publish(bundle(now, 1, quote(now, age=timedelta(hours=5))), now=now)
    reader = LocalDisplayReader(LocalDisplayStore(tmp_path), code_sha="a" * 40, config_hash="b" * 64)
    detail = reader.read_instrument_detail("510300.SH")
    _, quotes, generation = read_model.local_bundle_pricing(settings_for(tmp_path))
    assert generation == 1
    assert quotes["510300.SH"]["status"] == "stale"
    assert detail["quote"]["status"] == quotes["510300.SH"]["status"] == "stale"
    assert detail["quote"]["is_realtime"] is False


def test_detail_and_pricing_keep_a_fresh_quote_observed(tmp_path):
    now = datetime.now(timezone.utc)
    LocalDisplayStore(tmp_path).publish(bundle(now, 1, quote(now, age=timedelta(seconds=20))), now=now)
    reader = LocalDisplayReader(LocalDisplayStore(tmp_path), code_sha="a" * 40, config_hash="b" * 64)
    detail = reader.read_instrument_detail("510300.SH")
    _, quotes, _ = read_model.local_bundle_pricing(settings_for(tmp_path))
    assert quotes["510300.SH"]["status"] == "observed"
    assert detail["quote"]["status"] == "observed"
    assert detail["quote"]["is_realtime"] is True


def test_expired_bundle_marks_quote_stale_in_both_paths(tmp_path):
    now = datetime.now(timezone.utc)
    LocalDisplayStore(tmp_path).publish(bundle(now, 1, quote(now, age=timedelta(seconds=20))), now=now)
    reader = LocalDisplayReader(LocalDisplayStore(tmp_path), code_sha="a" * 40, config_hash="b" * 64)
    later = now + timedelta(hours=3)
    detail = reader.read_instrument_detail("510300.SH", now=later)
    _, quotes, _ = read_model.local_bundle_pricing(settings_for(tmp_path), now=later)
    assert detail["is_stale"] is True
    assert detail["quote"]["status"] == quotes["510300.SH"]["status"] == "stale"


class _ManifestWithoutExpiry:
    def load_bundle(self, generation=None):
        now = datetime.now(timezone.utc)
        return {"manifest": {"sequence": 7, "generated_at": now.isoformat()},
                "parts": {"details": {"510300.SH": {"quote": quote(now, age=timedelta(seconds=20))}}}}


def test_unusable_expiry_fails_closed_instead_of_raising():
    detail = LocalDisplayReader(_ManifestWithoutExpiry()).read_instrument_detail("510300.SH")
    assert detail["is_stale"] is True
    assert detail["quote"]["status"] == "stale"
    assert detail["quote"]["is_realtime"] is False

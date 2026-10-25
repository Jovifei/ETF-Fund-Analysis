"""Approved producer identities for local-display bundles.

The ECS consumer compares ``SHADOW_SYNC_CODE_SHA``/``SHADOW_SYNC_CONFIG_HASH`` with the
producer identity inside each bundle. Application releases and producer identity are
deliberately decoupled (a website-only release must keep an existing bundle readable),
but that decoupling only stays honest while the expected identity is registered here.
Advancing the producer is a deliberate, recorded act, never a deploy side effect.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

REGISTRY_VERSION = "bundle-producer-identities-v1"
DEFAULT_REGISTRY = Path(__file__).resolve().parents[3] / "config" / "bundle_identity_registry.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def validate_registry(data) -> list[dict]:
    if not isinstance(data, dict) or data.get("registry_version") != REGISTRY_VERSION:
        raise ValueError("invalid bundle identity registry version")
    identities = data.get("identities")
    if not isinstance(identities, list) or not identities:
        raise ValueError("registry requires at least one approved identity")
    seen, previous = set(), None
    for entry in identities:
        if not isinstance(entry, dict):
            raise ValueError("invalid identity entry")
        code_sha, config_hash, approved_at = (entry.get("code_sha"), entry.get("config_hash"),
                                              entry.get("approved_at"))
        if not isinstance(code_sha, str) or not SHA_RE.fullmatch(code_sha):
            raise ValueError("invalid producer code_sha")
        if not isinstance(config_hash, str) or not HASH_RE.fullmatch(config_hash):
            raise ValueError("invalid producer config_hash")
        try:
            approved = date.fromisoformat(approved_at) if isinstance(approved_at, str) else None
        except ValueError:
            approved = None
        if approved is None:
            raise ValueError("invalid approval date")
        if previous is not None and approved < previous:
            raise ValueError("registry identities must be ordered by approval date")
        previous = approved
        if (code_sha, config_hash) in seen:
            raise ValueError("duplicate producer identity")
        seen.add((code_sha, config_hash))
        for prior in entry.get("superseded") or []:
            if (not isinstance(prior, dict) or not isinstance(prior.get("code_sha"), str)
                    or not SHA_RE.fullmatch(prior["code_sha"])):
                raise ValueError("invalid superseded identity")
    return identities


def load_identities(path=None) -> list[dict]:
    return validate_registry(json.loads(Path(path or DEFAULT_REGISTRY).read_text(encoding="utf-8")))


def approved_identity(code_sha: str, config_hash: str, *, path=None) -> dict | None:
    for entry in load_identities(path):
        if entry["code_sha"] == code_sha and entry["config_hash"] == config_hash:
            return entry
    return None


def current_identity(path=None) -> dict:
    """The newest approved identity; the producer a new compute worktree should use."""
    return load_identities(path)[-1]


def check_expected_identity(code_sha: str, config_hash: str, *, path=None) -> dict:
    """Deploy-time gate: the consumer expectation must be a registered producer."""
    entry = approved_identity(code_sha, config_hash, path=path)
    return {"status": "approved" if entry else "unregistered", "code_sha": code_sha,
            "config_hash": config_hash, "approved_at": entry.get("approved_at") if entry else None}

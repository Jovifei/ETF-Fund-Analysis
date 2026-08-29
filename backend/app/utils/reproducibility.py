from __future__ import annotations

import os
import subprocess
from typing import Any, Iterable

from app.utils.hashing import stable_hash

UNKNOWN_COMMIT = "unknown"


def current_git_commit() -> str:
    """Return a bounded source revision without exposing repository credentials."""
    for name in ("GIT_COMMIT_SHA", "SOURCE_COMMIT_SHA", "RENDER_GIT_COMMIT"):
        value = (os.getenv(name) or "").strip()
        if value:
            return value[:64]
    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            timeout=2,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN_COMMIT
    return value[:64] if value else UNKNOWN_COMMIT


def feature_schema_hash(features: Iterable[str]) -> str:
    return stable_hash(sorted({str(item) for item in features}))


def reproducibility_payload(
    *,
    strategy: dict[str, Any],
    feature_schema_version: str,
    features: Iterable[str],
    code_component: str,
) -> dict[str, Any]:
    selected = tuple(str(item) for item in features)
    return {
        "git_commit_sha": current_git_commit(),
        "config_hash": stable_hash(strategy),
        "feature_schema_version": feature_schema_version,
        "feature_schema_hash": feature_schema_hash(selected),
        "code_component": code_component,
    }

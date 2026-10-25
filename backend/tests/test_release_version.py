import json
from pathlib import Path
import tomllib
from app.core.config import Settings


def test_release_versions_agree_with_canonical_package(monkeypatch):
    import re
    monkeypatch.delenv("APP_VERSION", raising=False)
    root = Path(__file__).resolve().parents[2]
    expected = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    latest = re.search(r"^## \[(\d+\.\d+\.\d+)\] — ", changelog, re.MULTILINE)
    assert latest is not None and latest.group(1) == expected, "pyproject version must match latest CHANGELOG section"
    assert Settings(_env_file=None).app_version == expected
    package = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))
    assert package["version"] == lock["version"] == lock["packages"][""]["version"] == expected


def test_workspace_status_does_not_publish_an_old_hardcoded_version(db_session):
    from app.workspace.actions_api import status
    settings = Settings(_env_file=None, market_provider='mock', app_version='1.0.7')
    payload = status(db_session, settings, None)
    assert payload['workspace_version'] == payload['app_version'] == settings.app_version

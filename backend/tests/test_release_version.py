import json
from pathlib import Path
import tomllib
from app.core.config import Settings


def test_release_versions_agree_with_canonical_package(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    root = Path(__file__).resolve().parents[2]
    expected = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert expected == "1.0.4"
    assert Settings(_env_file=None).app_version == expected
    package = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))
    assert package["version"] == lock["version"] == lock["packages"][""]["version"] == expected

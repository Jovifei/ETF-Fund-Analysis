from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from app.workspace.local_compute import (
    local_settings,
    compute_local,
    export_local_v2,
    doctor_check,
    ROW_FIELDS_V2,
    CONTRACT_VERSION,
)
from app.core.config import get_settings
from app.services.task_service import TaskService
from app.utils.hashing import stable_hash


def test_local_settings_root_and_ownership(tmp_path):
    root = tmp_path / "etf_root"
    root.mkdir()
    db_file = root / "research.sqlite3"
    db_file.touch()

    # Without marker file, it should raise ValueError
    with pytest.raises(ValueError, match="ownership marker"):
        local_settings(root, db_file, profile="live")

    # With marker file (.local-live)
    marker = root / ".local-live"
    marker.touch()

    # Wrong db name should raise
    wrong_db = root / "wrong.sqlite3"
    wrong_db.touch()
    with pytest.raises(ValueError, match="dedicated existing local SQLite database required"):
        local_settings(root, wrong_db, profile="live")

    # Correct root and db
    settings = local_settings(root, db_file, profile="live", market_provider="akshare")
    assert settings.database_url == f"sqlite:///{db_file.as_posix()}"
    assert settings.allow_mock_fallback is False
    assert settings.auth_enabled is False
    assert settings.llm_enabled is False
    assert settings.ocr_mode == "disabled"
    assert settings.market_provider == "akshare"


def test_local_compute_live_guard(tmp_path):
    root = tmp_path / "etf_root"
    root.mkdir()
    marker = root / ".local-live"
    marker.touch()
    db_file = root / "research.sqlite3"
    db_file.touch()

    # If mock provider is used with live profile, local_settings rejects it
    with pytest.raises(ValueError, match="live profile rejects mock"):
        local_settings(root, db_file, profile="live", market_provider="mock")


def test_doctor_check_detects_disk_and_structure(tmp_path):
    root = tmp_path / "etf_root"
    root.mkdir()
    marker = root / ".local-live"
    marker.touch()
    db_file = root / "research.sqlite3"
    db_file.touch()

    status = doctor_check(root, db_file, profile="live")
    assert "root_exists" in status
    assert "marker_exists" in status
    assert "disk_free_gb" in status
    assert "provider_status" in status
    assert status["root_exists"] is True
    assert status["marker_exists"] is True


def test_export_local_v2_bundle_contract(database, bootstrapped, db_session, tmp_path):
    settings = get_settings()
    TaskService(settings).run(db_session, "refresh_decision_board")
    db_session.commit()

    bundle = export_local_v2(
        settings,
        sequence=1,
        code_sha="b" * 40,
        universe=["510300.SH", "512480.SH"],
    )

    manifest = bundle["manifest"]
    assert manifest["contract_version"] == CONTRACT_VERSION
    assert manifest["code_sha"] == "b" * 40
    assert "overview" in bundle["parts"]
    assert "details" in bundle["parts"]
    assert "charts" in bundle["parts"]
    assert bundle["manifest"]["actionable"] is False
    assert bundle["manifest"]["data_origin"] == "local_research"

"""Verify that upload and pre-upload validation failures persist specific error messages and failure stages."""
import json
import os
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

from app.workspace.local_job_ledger import public_error_type
from app.workspace.local_atomic import write_json_atomic


def test_public_error_type_mapping():
    assert public_error_type(ValueError("test")) == "ValueError"
    assert public_error_type(TimeoutError("slow")) == "TimeoutError"
    assert public_error_type(Exception("generic")) == "Exception"


def test_upload_failure_persists_detailed_diagnostics(tmp_path, capsys):
    """When an upload fails in cmd_run, the exact error_message, error_type, and last_upload_error.json must be written."""
    import argparse
    from scripts.run_local_compute import cmd_run

    (tmp_path / ".local-live").write_text("live", encoding="utf-8")
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True)
    (db_dir / "research.sqlite3").write_bytes(b"")

    outbox = tmp_path / "outbox"
    outbox.mkdir(parents=True)
    config = tmp_path / "config" / "live.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"universe": ["510300.SH"]}), encoding="utf-8")
    
    auth_file = tmp_path / "config" / "producer_auth.json"
    auth_file.write_text(json.dumps({
        "producer_token": "token",
        "key_id": "key",
        "signing_secret": "secret"
    }), encoding="utf-8")

    bundle = {
        "manifest": {"sequence": 12345, "universe": ["510300.SH"]},
        "parts": {"overview": {"rows": []}}
    }
    bundle_file = outbox / "bundle_12345.json"
    write_json_atomic(bundle_file, bundle)

    args = argparse.Namespace(
        root=str(tmp_path),
        config=str(config),
        profile="live",
        provider="public_composite",
        expected_sha="0" * 40,
        no_upload=False,
        compute_only=False,
        board_only=False,
        prepare_base=False,
        private_research=False,
        closed_session_research=False,
        skip_trade_day_check=True,
        cadence_mode="full",
        db=None,
        sync_url="https://example.com/api/shadow/sync"
    )

    with patch("scripts.run_local_compute.get_current_git_sha", return_value="0" * 40), \
         patch("scripts.run_local_compute.validate_provider_admission", return_value={"operation_permitted": True}), \
         patch("scripts.run_local_compute.export_local_v2", return_value=bundle), \
         patch("scripts.run_local_compute.LocalRunLock.acquire", return_value=True), \
         patch("scripts.run_local_compute.LocalRunLock.release", return_value=None), \
         patch("scripts.run_local_compute.compute_local", return_value=[{"task_name": "refresh_decision_board", "status": "succeeded", "required": False}]), \
         patch("app.workspace.shadow_client.upload_bundle_auto", side_effect=ValueError("fast observation quote expired or outside session")):
        
        rc = cmd_run(args)
        assert rc == 1

    err_file = outbox / "last_upload_error.json"
    assert err_file.exists(), "last_upload_error.json was not created"
    saved = json.loads(err_file.read_text(encoding="utf-8"))
    assert saved["status"] == "upload_failed"
    assert saved["error_type"] == "ValueError"
    assert "fast observation quote expired or outside session" in saved["error_message"]
    assert saved["phase"] == "transport_receipt"

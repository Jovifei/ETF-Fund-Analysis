from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_backup_script_forces_owner_only_permissions() -> None:
    source = (ROOT / "scripts" / "backup_postgres.sh").read_text(encoding="utf-8")
    assert "umask 077" in source
    assert "chmod 700 backups" in source
    assert 'chmod 600 "$file" "${file}.sha256"' in source


def test_aliyun_deploy_hardens_server_local_private_directories() -> None:
    source = (ROOT / "deploy" / "aliyun" / "deploy.sh").read_text(encoding="utf-8")
    assert "umask 077" in source
    assert "chmod 700 reports backups" in source
    assert "chmod 600 .env" in source


def test_standard_production_example_does_not_enable_uninstalled_ocr_extra() -> None:
    source = (ROOT / "deploy" / ".env.production.example").read_text(encoding="utf-8")
    assert "OCR_MODE=disabled" in source
    assert "OCR_MODE=local_paddle" not in source


def test_provider_smoke_uses_application_quote_timestamp_qualification() -> None:
    source = (ROOT / "scripts" / "provider_smoke.py").read_text(encoding="utf-8")
    assert "MarketService._qualify_quote_timestamp" in source
    assert '"verified_realtime"' in source
    assert '"provider_realtime"' in source

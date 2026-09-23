from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_backup_script_forces_owner_only_permissions() -> None:
    source = (ROOT / "scripts" / "backup_postgres.sh").read_text(encoding="utf-8")
    assert "umask 077" in source
    assert 'chmod 700 "$backup_dir"' in source
    assert 'chmod 600 "$pending/archive.sql.gz" "$pending/archive.sha256"' in source


def test_linux_shell_entrypoints_use_lf_line_endings() -> None:
    scripts = [
        *(ROOT / "deploy" / "aliyun").glob("*.sh"),
        *(ROOT / "scripts").glob("*.sh"),
    ]
    assert scripts
    for path in scripts:
        assert b"\r" not in path.read_bytes(), f"{path.relative_to(ROOT)} must use LF for Linux shebangs"


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


def test_production_dockerfile_installs_the_wheel_built_from_current_source() -> None:
    source = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert '"china-fund-decision[market]"' in source
    assert "china-fund-decision[market]==" not in source
    assert "--no-index --find-links=/wheels" in source


def test_frontend_builder_caps_node_heap_for_small_production_hosts() -> None:
    source = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert "ENV NODE_OPTIONS=--max-old-space-size=1024" in source

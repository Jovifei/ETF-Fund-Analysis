"""Recovery-script contract checks never call the Windows Task Scheduler service."""
import shutil
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "recover_local_compute_task.ps1"


def source():
    return SCRIPT.read_text(encoding="utf-8")


def test_preview_dead_tree_guard_and_owned_task_scope():
    text = source()
    for token in ("ExpectedSha", "PREVIEW ONLY", "ETF-Local-Live-Compute",
                  "China Standard Time", "Test-Path -LiteralPath $deadTree",
                  "migrate_local_cadence_task.ps1", "--expected-sha",
                  "Find-DeadPathReferences", "run_local_compute.py",
                  "producer_auth.json", "F:\\ETF_Data\\ETF-Fund-Analysis"):
        assert token in text
    # Preview returns before any file write or scheduler mutation.
    assert text.index("if (-not $Apply)") < text.index("[IO.File]::Open")
    assert text.index("if (-not $Apply)") < text.index("Unregister-ScheduledTask")
    # The dead-tree scan is report-only: the only task ever unregistered or
    # registered is the owned one, by literal name.
    assert "Unregister-ScheduledTask -TaskName $TaskName" in text
    assert text.count("Register-ScheduledTask") == 2  # recover + rollback restore
    assert "Set-TimeZone" not in text
    assert "Get-Content -LiteralPath $auth" not in text


def test_recovery_preserves_sections_and_registers_disabled():
    text = source()
    for token in ("Export-ScheduledTask", "Get-TaskSection", "'Triggers', 'Settings', 'Principals'",
                  "Disable-ScheduledTask", "SecurityElement]::Escape",
                  "original task restored and verified"):
        assert token in text
    # Never starts a computation itself: the controlled first run is manual.
    assert "Start-ScheduledTask" not in text
    assert "-Force" not in text


def test_immutable_backup_format_and_clean_source_gate():
    text = source()
    assert "FileMode]::CreateNew" in text
    assert "[Text.Encoding]::Unicode" in text
    assert "Get-FileHash" in text
    assert "ReparsePoint" in text
    assert "Assert-CleanSource $resolvedTree $ExpectedSha" in text
    assert "3.12" in text


def test_powershell_parser_accepts_recovery_script():
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        pytest.skip("PowerShell unavailable")
    command = r"""
    $errors=$null; $tokens=$null
    $ast=[System.Management.Automation.Language.Parser]::ParseFile($env:ETF_RECOVERY_SCRIPT,[ref]$tokens,[ref]$errors)
    if($errors.Count){throw ($errors | Out-String)}
    'parsed'
    """
    import os
    import subprocess
    env = {**os.environ, "ETF_RECOVERY_SCRIPT": str(SCRIPT)}
    result = subprocess.run([shell, "-NoProfile", "-Command", command],
                            capture_output=True, text=True, env=env, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "parsed" in result.stdout

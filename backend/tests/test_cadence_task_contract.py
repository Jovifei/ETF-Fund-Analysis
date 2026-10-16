"""Migration contract checks never call the Windows Task Scheduler service."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_local_cadence_task.ps1"


def source():
    return SCRIPT.read_text(encoding="utf-8")


def test_preview_and_exact_owned_task_guards():
    text = source()
    for token in ("ExpectedPreviousSha", "ExpectedSha", "BackupReceipt", "PREVIEW ONLY", "ETF-Local-Live-Compute",
                  "China Standard Time", "Ready", "--private-research --closed-session-research"):
        assert token in text
    assert text.index("if (-not $Apply)") < text.index("[IO.File]::Open")
    assert "Register-ScheduledTask" not in text
    assert "Set-TimeZone" not in text
    assert "-Principal" not in text
    assert "-Force" not in text


def test_daily_repetition_and_setting_preservation_contract():
    text = source()
    for token in ("New-CadenceTrigger", "-Daily", "13", "50", "PT1M", "PT3H", "StartWhenAvailable = $true",
                  "IgnoreNew", "PT20M", "CimInstance]::new($task.Settings)", "Assert-TaskDefinition"):
        assert token in text
    assert "-Action $originalAction -Trigger $originalTriggers -Settings $originalSettings" in text
    assert "Principal" in text and "Settings" in text and "InnerXml" in text


def test_private_backup_format_and_no_credential_reads():
    text = source()
    assert "FileMode]::CreateNew" in text
    assert "[Text.Encoding]::Unicode" in text
    assert "Get-FileHash" in text
    assert "ReparsePoint" in text
    assert "producer_auth.json" in text
    assert "Get-Content -LiteralPath $auth" not in text
    assert "Start-ScheduledTask" not in text


def test_powershell_parser_and_trigger_function_without_scheduler_calls():
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        pytest.skip("PowerShell unavailable")
    # Only define the trigger helper, stubbing both constructors. No full script
    # invocation, task enumeration, OS changes or provider calls are possible.
    command = r'''
    $errors=$null; $tokens=$null
    $ast=[System.Management.Automation.Language.Parser]::ParseFile($env:ETF_CADENCE_SCRIPT,[ref]$tokens,[ref]$errors)
    if($errors.Count){throw ($errors | Out-String)}
    $fn=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'New-CadenceTrigger'},$true)
    if(-not $fn){throw 'trigger helper missing'}
    function New-ScheduledTaskTrigger {param([switch]$Daily,$At) [pscustomobject]@{Daily=[bool]$Daily;At=$At;Repetition=$null}}
    function New-CimInstance {param($Namespace,$ClassName,[switch]$ClientOnly,$Property) [pscustomobject]$Property}
    Invoke-Expression $fn.Extent.Text
    $trigger=New-CadenceTrigger
    [pscustomobject]@{daily=$trigger.Daily;at=$trigger.At.ToString('HH:mm');interval=$trigger.Repetition.Interval;duration=$trigger.Repetition.Duration;stop=$trigger.Repetition.StopAtDurationEnd} | ConvertTo-Json -Compress
    '''
    result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", command],
                            env={**os.environ, "ETF_CADENCE_SCRIPT": str(SCRIPT)}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"daily": True, "at": "13:50", "interval": "PT1M", "duration": "PT3H", "stop": False}


def test_xml_verifier_rejects_principal_setting_and_trigger_drift():
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        pytest.skip("PowerShell unavailable")
    command = r'''
    $ErrorActionPreference='Stop';$errors=$null;$tokens=$null
    $ast=[System.Management.Automation.Language.Parser]::ParseFile($env:ETF_CADENCE_SCRIPT,[ref]$tokens,[ref]$errors)
    foreach($name in @('Get-TaskSection','Settings-WithoutCatchup','Assert-TaskDefinition')){
      $fn=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true)
      Invoke-Expression $fn.Extent.Text
    }
    $resolvedPython='E:\test\python.exe';$resolvedTree='E:\test\new'
    $originalAction=[pscustomobject]@{WorkingDirectory='E:\test\old'}
    $candidate=[pscustomobject]@{Actions=@([pscustomobject]@{Execute=$resolvedPython;Arguments='dispatch';WorkingDirectory=$resolvedTree})}
    $old='<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Principals><Principal id="unit"><UserId>unit</UserId></Principal></Principals><Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><StartWhenAvailable>false</StartWhenAvailable><ExecutionTimeLimit>PT20M</ExecutionTimeLimit></Settings><Triggers><CalendarTrigger><StartBoundary>2026-10-16T14:20:20</StartBoundary></CalendarTrigger></Triggers></Task>'
    $new='<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Principals><Principal id="unit"><UserId>unit</UserId></Principal></Principals><Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><StartWhenAvailable>true</StartWhenAvailable><ExecutionTimeLimit>PT20M</ExecutionTimeLimit></Settings><Triggers><CalendarTrigger><StartBoundary>2026-10-16T13:50:00</StartBoundary><Repetition><Interval>PT1M</Interval><Duration>PT3H</Duration></Repetition><ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger></Triggers></Task>'
    Assert-TaskDefinition $candidate $new $old 'dispatch'
    $failures=0
    foreach($bad in @($new.Replace('<UserId>unit</UserId>','<UserId>other</UserId>'),$new.Replace('PT20M','PT60M'),$new.Replace('PT1M','PT5M'),$new.Replace('StartWhenAvailable>true','StartWhenAvailable>false'))){
      try { Assert-TaskDefinition $candidate $bad $old 'dispatch' } catch { $failures++ }
    }
    if($failures -ne 4){throw 'drift guard not enforced'}
    Write-Output 'PASS'
    '''
    result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", command],
                            env={**os.environ, "ETF_CADENCE_SCRIPT": str(SCRIPT)}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PASS"

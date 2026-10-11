param(
    [string]$Python = "E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe",
    [string]$Workspace = "E:\project\ETF-Fund-Analysis",
    [string]$LocalRoot = "F:\ETF_Data\ETF-Fund-Analysis",
    [string]$Config = "F:\ETF_Data\ETF-Fund-Analysis\config\live.json",
    [string]$Provider = "public_composite",
    [string[]]$Slots = @("14:20", "14:30", "14:45", "14:50", "14:55", "15:00", "15:15", "16:10"),
    [string]$TaskName = "ETF-Local-Live-Compute"
)

foreach ($val in @($Python, $Workspace, $LocalRoot, $Config, $Provider, $TaskName)) {
    if ($val -match '["`\r\n]') { throw "Unsafe task parameter" }
}

if ((Get-TimeZone).Id -ne 'China Standard Time') {
    throw "Task registration requires China Standard Time (Asia/Shanghai) Windows timezone"
}

$scriptPath = Join-Path (Resolve-Path -LiteralPath $Workspace) "scripts\run_local_compute.py"
$resolvedPython = (Resolve-Path -LiteralPath $Python).Path

$arguments = '"{0}" run --root "{1}" --profile live --provider "{2}" --config "{3}"' -f $scriptPath, $LocalRoot, $Provider, $Config

$action = New-ScheduledTaskAction -Execute $resolvedPython -Argument $arguments -WorkingDirectory (Resolve-Path -LiteralPath $Workspace).Path
$triggers = @($Slots | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ })
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings -Description "Deterministic local ETF research compute and HTTPS display upload" -Force

Write-Output "Successfully registered Windows Scheduled Task: $TaskName"
Write-Output "Triggers: $($Slots -join ', ')"
Write-Output "Action: $resolvedPython $arguments"
Write-Output "Stop command: Stop-ScheduledTask -TaskName '$TaskName'"
Write-Output "Unregister command: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"

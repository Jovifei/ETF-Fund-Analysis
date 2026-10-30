<# Preview by default. Register only a new, disabled task for notification dispatch. #>
param(
    [string]$Python = "E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe",
    [string]$Workspace = "E:\project\ETF-Fund-Analysis",
    [string]$LocalRoot = "F:\ETF_Data\ETF-Fund-Analysis",
    [string[]]$Slots = @("11:40", "14:30", "14:45", "18:00"),
    [string]$TaskName = "ETF-Local-Notifications",
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
foreach ($val in @($Python, $Workspace, $LocalRoot, $TaskName)) {
    if ([string]::IsNullOrWhiteSpace($val) -or $val -match '["`\r\n]') { throw "Unsafe or empty task parameter" }
}
if ($TaskName -match '[*?\[\]]') { throw "Task name must be literal" }
if ((Get-TimeZone).Id -ne 'China Standard Time') { throw "Requires China Standard Time; never changes system timezone" }
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { throw "Task already exists; refusing to overwrite" }

$resolvedTree = (Resolve-Path -LiteralPath $Workspace).Path
$resolvedPython = (Resolve-Path -LiteralPath $Python).Path
$scriptPath = Join-Path $resolvedTree "scripts\run_local_notifications.py"
foreach ($path in @($scriptPath, (Join-Path $LocalRoot '.local-live'))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required local file missing" }
}

foreach ($slot in $Slots) {
    if ($slot -notmatch '^(?:[01][0-9]|2[0-3]):[0-5][0-9]$') { throw "Invalid slot format: $slot" }
}

$arguments = '"{0}" dispatch --root "{1}"' -f $scriptPath, $LocalRoot
$action = New-ScheduledTaskAction -Execute $resolvedPython -Argument $arguments -WorkingDirectory $resolvedTree
$triggers = @($Slots | ForEach-Object { New-ScheduledTaskTrigger -Daily -At ([TimeSpan]::Parse($_).ToString()) })
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
$description = "Deterministic local ETF decision digest and notification dispatcher. Slots=$($Slots -join ', ')"

Write-Output "Task: $TaskName; Slots=$($Slots -join ', ')"
if (-not $Apply) {
    Write-Output 'PREVIEW ONLY; -Apply registers disabled task, manually verify before enabling'
    return
}

$definition = New-ScheduledTask -Action $action -Trigger $triggers -Settings $settings -Description $description
$definition.Settings.Enabled = $false
Register-ScheduledTask -TaskName $TaskName -InputObject $definition | Out-Null
Write-Output "Registered DISABLED: $TaskName"

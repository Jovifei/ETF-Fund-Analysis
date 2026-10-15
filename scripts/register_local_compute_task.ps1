<# Preview by default. Register only a new, disabled task pinned to a clean SHA. #>
param(
    [string]$Python = "E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe",
    [string]$Workspace = "E:\project\ETF-Fund-Analysis",
    [string]$LocalRoot = "F:\ETF_Data\ETF-Fund-Analysis",
    [string]$Config = "F:\ETF_Data\ETF-Fund-Analysis\config\live.json",
    [string]$Provider = "public_composite",
    [string[]]$Slots = @("14:20", "14:30", "14:45", "14:50", "14:55", "15:00", "15:15", "16:10"),
    [string]$TaskName = "ETF-Local-Live-Compute",
    [switch]$Apply,
    [switch]$PrivateResearch,
    [switch]$ClosedSessionResearch
)
$ErrorActionPreference = 'Stop'
if ($ClosedSessionResearch -and -not $PrivateResearch) { throw 'ClosedSessionResearch requires explicit PrivateResearch' }
foreach ($val in @($Python, $Workspace, $LocalRoot, $Config, $Provider, $TaskName)) {
    if ([string]::IsNullOrWhiteSpace($val) -or $val -match '["`\r\n]') { throw "Unsafe or empty task parameter" }
}
if ($TaskName -match '[*?\[\]]') { throw "Task name must be literal" }
if ((Get-TimeZone).Id -ne 'China Standard Time') { throw "Requires China Standard Time; never changes system timezone" }
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { throw "Task already exists; refusing to overwrite" }
$resolvedTree = (Resolve-Path -LiteralPath $Workspace).Path
$resolvedPython = (Resolve-Path -LiteralPath $Python).Path
$scriptPath = Join-Path $resolvedTree "scripts\run_local_compute.py"
foreach ($path in @($scriptPath, $Config, (Join-Path $LocalRoot '.local-live'), (Join-Path $LocalRoot 'db\research.sqlite3'))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required local file missing" }
}
$sha = (& git -C $resolvedTree rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sha -notmatch '^[0-9a-f]{40}$') { throw "Cannot identify worktree" }
$dirty = (& git -C $resolvedTree status --porcelain backend scripts config frontend pyproject.toml)
if ($LASTEXITCODE -ne 0 -or $dirty) { throw "Worktree runtime identity is not clean" }
$arguments = '"{0}" run --root "{1}" --profile live --provider "{2}" --config "{3}" --expected-sha {4}' -f $scriptPath, $LocalRoot, $Provider, $Config, $sha
if ($PrivateResearch) { $arguments += ' --private-research' }
if ($ClosedSessionResearch) { $arguments += ' --closed-session-research' }
$action = New-ScheduledTaskAction -Execute $resolvedPython -Argument $arguments -WorkingDirectory $resolvedTree
$triggers = @($Slots | ForEach-Object { New-ScheduledTaskTrigger -Daily -At ([TimeSpan]::Parse($_).ToString()) })
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
$description = "Deterministic local ETF compute. owner=bot/local-live-phase1-closure code=$sha"
Write-Output "Task: $TaskName; code=$sha; slots=$($Slots -join ', ')"
if (-not $Apply) { Write-Output 'PREVIEW ONLY; -Apply registers disabled, manually verify before enabling'; return }
$definition = New-ScheduledTask -Action $action -Trigger $triggers -Settings $settings -Description $description
$definition.Settings.Enabled = $false
Register-ScheduledTask -TaskName $TaskName -InputObject $definition | Out-Null
Write-Output "Registered DISABLED: $TaskName"

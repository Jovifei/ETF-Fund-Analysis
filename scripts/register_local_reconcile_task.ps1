<#
16:30 weekday local reconcile task (plan 05 §G): Preview by default, -Apply to register.
- Refuses if a task with the same name already exists (never -Force overwrite).
- Registers DISABLED first; enable only after one verified manual run (-Enable on a later call).
- Bounded validity (EndBoundary) so the soak task does not silently live forever.
- No secrets in argv; reconcile is read-only over the owned local root.
#>
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$Worktree,
    [Parameter(Mandatory = $true)][string]$LocalRoot,
    [string]$TaskName = "ETF-Local-Reconcile-1630",
    [string]$At = "16:30",
    [int]$ValidDays = 30,
    [switch]$Apply,
    [switch]$Enable
)
$ErrorActionPreference = 'Stop'
foreach ($val in @($Python, $Worktree, $LocalRoot, $TaskName, $At)) {
    if ([string]::IsNullOrWhiteSpace($val) -or $val -match '["`\r\n]') { throw "Unsafe or empty task parameter" }
}
if ((Get-TimeZone).Id -ne 'China Standard Time') { throw "Requires China Standard Time; this script never changes the system timezone" }
if ($ValidDays -lt 1 -or $ValidDays -gt 60) { throw "ValidDays must be 1..60" }

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Enable) {
    if (-not $existing) { throw "Task $TaskName not found" }
    if ($existing.Description -notlike '*owner=bot/local-live-phase1-closure*') { throw "Task $TaskName is not owned by this phase; refusing" }
    Enable-ScheduledTask -TaskName $TaskName | Out-Null
    Write-Output "Enabled: $TaskName"
    return
}

$resolvedPython = (Resolve-Path -LiteralPath $Python).Path
$resolvedTree = (Resolve-Path -LiteralPath $Worktree).Path
$script = Join-Path $resolvedTree "scripts\run_local_compute.py"
if (-not (Test-Path -LiteralPath $script)) { throw "run_local_compute.py not found in worktree" }
if (-not (Test-Path -LiteralPath (Join-Path $LocalRoot '.local-live'))) { throw "Local root owner marker missing" }
$sha = (& git -C $resolvedTree rev-parse HEAD).Trim()
$dirty = (& git -C $resolvedTree status --porcelain backend scripts config)
if ($dirty) { throw "Worktree has uncommitted runtime changes; refusing" }

$arguments = '"{0}" reconcile --root "{1}" --profile live' -f $script, $LocalRoot
$start = (Get-Date).Date.Add([TimeSpan]::Parse($At))
if ($start -lt (Get-Date)) { $start = $start.AddDays(1) }
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $start
$trigger.EndBoundary = (Get-Date).AddDays($ValidDays).ToString('s')
$action = New-ScheduledTaskAction -Execute $resolvedPython -Argument $arguments -WorkingDirectory $resolvedTree
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -StartWhenAvailable
$description = "ETF 16:30 local reconcile (read-only). owner=bot/local-live-phase1-closure code=$sha"
$definition = "$TaskName|$resolvedPython|$arguments|$resolvedTree|$At|MonFri|end=$($trigger.EndBoundary)|$description"
$defHash = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($definition))).Replace('-', '').ToLower()

Write-Output "TaskName: $TaskName"
Write-Output "Action: $resolvedPython $arguments"
Write-Output "WorkingDirectory: $resolvedTree"
Write-Output "Trigger: Mon-Fri $At, EndBoundary $($trigger.EndBoundary)"
Write-Output "DefinitionSha256: $defHash"
if ($existing) { throw "Task $TaskName already exists (owner unknown); refusing to overwrite" }
if (-not $Apply) { Write-Output "PREVIEW ONLY (pass -Apply to register disabled)"; return }

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description $description | Out-Null
Disable-ScheduledTask -TaskName $TaskName | Out-Null
Write-Output "Registered DISABLED: $TaskName"
Write-Output "Manual verify (task stays disabled): & '$resolvedPython' $arguments ; then re-run with -Enable"
Write-Output "Stop: Disable-ScheduledTask -TaskName '$TaskName'; Unregister: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"

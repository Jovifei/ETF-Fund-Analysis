param([Parameter(Mandatory=$true)][string]$Python,[Parameter(Mandatory=$true)][string]$Workspace,[Parameter(Mandatory=$true)][string]$LocalRoot,[Parameter(Mandatory=$true)][string]$Database,[Parameter(Mandatory=$true)][string]$CodeSha,[string]$SyncUrl='', [string[]]$Slots=@('14:30','14:45','14:50','14:55','15:00','15:15'))
foreach ($value in @($Python,$Workspace,$LocalRoot,$Database,$CodeSha,$SyncUrl)) { if ($value -match '["`\r\n]') { throw 'Unsafe task argument' } }
# Registration is explicit; the process needs no Codex chat and no GPU.
if ((Get-TimeZone).Id -ne 'China Standard Time') { throw 'Task registration requires existing Asia/Shanghai Windows timezone; no timezone is changed' }
$scriptPath = Join-Path (Resolve-Path -LiteralPath $Workspace) 'scripts\shadow_local_job.py'
$resolvedPython = (Resolve-Path -LiteralPath $Python).Path
foreach ($slot in $Slots) { if ($slot -notmatch '^1[45]:[0-5][0-9]$') { throw 'Invalid slot' } }
$arguments = '"{0}" --root "{1}" --database "{2}" --code-sha "{3}" --slots "{4}"' -f $scriptPath,$LocalRoot,$Database,$CodeSha,($Slots -join ',')
if ($Slots.Count -lt 1 -or $Slots.Count -gt 8) { throw 'At most eight slots required' }
if ($SyncUrl) {
    $uri = [Uri]$SyncUrl
    if (-not $uri.IsAbsoluteUri -or $uri.Scheme -ne 'https' -or -not $uri.Host -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -ne '/api/shadow/sync') { throw 'Exact HTTPS sync endpoint required' }
    $arguments += ' --sync-url "{0}"' -f $SyncUrl
}
$action = New-ScheduledTaskAction -Execute $resolvedPython -Argument $arguments -WorkingDirectory (Resolve-Path -LiteralPath $Workspace).Path
$triggers = @($Slots | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ })
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName 'ETF-Shadow-Local-Research' -Action $action -Trigger $triggers -Settings $settings -Description 'Offline local research; market-calendar gated; canonical production untouched'

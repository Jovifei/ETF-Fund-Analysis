<# Migrate one verified owned task. Preview first; never start a computation here. #>
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-f0-9]{40}$')][string]$ExpectedPreviousSha,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-f0-9]{40}$')][string]$ExpectedSha,
    [Parameter(Mandatory = $true)][ValidateSet('ETF-Local-Live-Compute')][string]$TaskName,
    [Parameter(Mandatory = $true)][string]$Workspace,
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$LocalRoot,
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][string]$BackupDirectory,
    [string]$BackupReceipt,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'

function Assert-SafePath([string]$Path, [switch]$Directory) {
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -match '["`\r\n]' -or
        -not [IO.Path]::IsPathRooted($Path) -or $Path.StartsWith('\\')) { throw 'Unsafe local path' }
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $item = Get-Item -LiteralPath $full
    if (($Directory -and -not $item.PSIsContainer) -or (-not $Directory -and $item.PSIsContainer)) { throw 'Unexpected path type' }
    $cursor = $item
    while ($null -ne $cursor) {
        if ($cursor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'ReparsePoint path refused' }
        if ($cursor.PSIsContainer) { $cursor = $cursor.Parent } else { $cursor = $cursor.Directory }
    }
    return $full
}

function Assert-CleanSource([string]$Tree, [string]$Sha) {
    $actual = (& git -C $Tree rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -cne $Sha) { throw 'Fixed source identity mismatch' }
    $dirty = (& git -C $Tree status --porcelain --untracked-files=all backend scripts config frontend pyproject.toml)
    if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Runtime source must be clean' }
}

function New-CadenceTrigger {
    $trigger = New-ScheduledTaskTrigger -Daily -At ((Get-Date).Date.AddHours(13).AddMinutes(50))
    $trigger.Repetition = New-CimInstance -Namespace 'root/Microsoft/Windows/TaskScheduler' `
        -ClassName 'MSFT_TaskRepetitionPattern' -ClientOnly `
        -Property @{ Interval = 'PT1M'; Duration = 'PT3H'; StopAtDurationEnd = $false }
    return $trigger
}

function Get-TaskSection([string]$XmlText, [string]$Name) {
    [xml]$document = $XmlText
    $node = $document.DocumentElement.SelectSingleNode("*[local-name()='$Name']")
    if ($null -eq $node) { throw 'Required task XML section missing' }
    return $node
}

function Settings-WithoutCatchup([string]$XmlText) {
    $node = Get-TaskSection $XmlText 'Settings'
    $catchup = $node.SelectSingleNode("*[local-name()='StartWhenAvailable']")
    if ($null -ne $catchup) { [void]$node.RemoveChild($catchup) }
    return $node.InnerXml
}

function Assert-TaskDefinition($Candidate, [string]$XmlText, [string]$OriginalXml,
                               [string]$ExpectedArguments, [switch]$Restored) {
    if (@($Candidate.Actions).Count -ne 1 -or $Candidate.Actions[0].Execute -ne $resolvedPython -or
        $Candidate.Actions[0].Arguments -cne $ExpectedArguments) { throw 'Task action verification failed' }
    $expectedDirectory = if ($Restored) { $originalAction.WorkingDirectory } else { $resolvedTree }
    if ($Candidate.Actions[0].WorkingDirectory -ne $expectedDirectory) { throw 'Task working directory changed' }
    if ((Get-TaskSection $XmlText 'Principals').OuterXml -cne (Get-TaskSection $OriginalXml 'Principals').OuterXml) {
        throw 'Principal preservation verification failed'
    }
    if ($Restored) {
        foreach ($section in @('Triggers', 'Settings')) {
            if ((Get-TaskSection $XmlText $section).OuterXml -cne (Get-TaskSection $OriginalXml $section).OuterXml) {
                throw 'Rollback scheduling verification failed'
            }
        }
        return
    }
    if ((Settings-WithoutCatchup $XmlText) -cne (Settings-WithoutCatchup $OriginalXml)) { throw 'Unrelated settings changed' }
    $settingsNode = Get-TaskSection $XmlText 'Settings'
    if ($settingsNode.SelectSingleNode("*[local-name()='StartWhenAvailable']").InnerText -ne 'true') { throw 'Catchup setting absent' }
    $triggersNode = Get-TaskSection $XmlText 'Triggers'
    $triggers = @($triggersNode.ChildNodes)
    if ($triggers.Count -ne 1 -or $triggers[0].LocalName -ne 'CalendarTrigger') { throw 'One daily controller required' }
    $trigger = $triggers[0]
    $start = [datetime]::Parse($trigger.SelectSingleNode("*[local-name()='StartBoundary']").InnerText)
    if ($start.Hour -ne 13 -or $start.Minute -ne 50 -or $start.Second -ne 0 -or
        $trigger.SelectSingleNode("*[local-name()='ScheduleByDay']/*[local-name()='DaysInterval']").InnerText -ne '1' -or
        $trigger.SelectSingleNode("*[local-name()='Repetition']/*[local-name()='Interval']").InnerText -ne 'PT1M' -or
        $trigger.SelectSingleNode("*[local-name()='Repetition']/*[local-name()='Duration']").InnerText -ne 'PT3H') {
        throw 'Daily repetition verification failed'
    }
}

if ((Get-TimeZone).Id -ne 'China Standard Time') { throw 'China Standard Time required; no timezone changes allowed' }
if ($ExpectedSha -eq $ExpectedPreviousSha -or $ExpectedSha -eq ('0' * 40) -or $ExpectedPreviousSha -eq ('0' * 40)) {
    throw 'Distinct nonzero source identities required'
}
$resolvedTree = Assert-SafePath $Workspace -Directory
$resolvedPython = Assert-SafePath $Python
$resolvedRoot = Assert-SafePath $LocalRoot -Directory
$resolvedConfig = Assert-SafePath $Config
$resolvedBackup = Assert-SafePath $BackupDirectory -Directory
if ($resolvedRoot -ne 'F:\ETF_Data\ETF-Fund-Analysis' -or $resolvedConfig -ne (Join-Path $resolvedRoot 'config\live.json')) {
    throw 'Canonical owned data/config root required'
}
$script = Assert-SafePath (Join-Path $resolvedTree 'scripts\run_local_compute.py')
$database = Assert-SafePath (Join-Path $resolvedRoot 'db\research.sqlite3')
$null = Assert-SafePath (Join-Path $resolvedRoot '.local-live')
# Existence/path checks only: credentials are never read or copied.
$auth = Join-Path $resolvedRoot 'config\producer_auth.json'
$null = Assert-SafePath $auth
Assert-CleanSource $resolvedTree $ExpectedSha
$pythonVersion = (& $resolvedPython -c 'import sys;print("%s.%s" % sys.version_info[:2])').Trim()
if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne '3.12') { throw 'Approved Python 3.12 required' }

$task = Get-ScheduledTask -TaskName $TaskName -TaskPath '\'
if ($task.State -ne 'Ready' -or @($task.Actions).Count -ne 1 -or @($task.Triggers).Count -ne 8) {
    throw 'Original owned task must be Ready, idle, with one action and eight triggers'
}
if ([string]$task.Settings.MultipleInstances -notin @('IgnoreNew', '2') -or
    [string]$task.Settings.ExecutionTimeLimit -ne 'PT20M') { throw 'Original bounded scheduling semantics changed' }
$expectedSlots = @('14:20:20', '14:30:20', '14:45:20', '14:50:20', '14:55:20', '15:00:20', '15:15:20', '16:10:20')
$existingSlots = @($task.Triggers | ForEach-Object {
    if ($_.CimClass.CimClassName -ne 'MSFT_TaskDailyTrigger' -or $_.DaysInterval -ne 1 -or
        -not $_.Enabled -or -not [string]::IsNullOrEmpty([string]$_.Repetition.Interval)) {
        throw 'Original daily trigger semantics changed'
    }
    ([datetime]::Parse($_.StartBoundary)).ToString('HH:mm:ss')
} | Sort-Object)
if (($existingSlots -join ',') -cne ($expectedSlots -join ',')) { throw 'Original eight slot times changed' }
$originalAction = $task.Actions[0]
$previousTree = Assert-SafePath $originalAction.WorkingDirectory -Directory
Assert-CleanSource $previousTree $ExpectedPreviousSha
$previousScript = Assert-SafePath (Join-Path $previousTree 'scripts\run_local_compute.py')
$previousArguments = '"{0}" run --root "{1}" --profile live --provider public_composite --config "{2}" --expected-sha {3} --private-research --closed-session-research' -f $previousScript, $resolvedRoot, $resolvedConfig, $ExpectedPreviousSha
if ($originalAction.Execute -ne $resolvedPython -or $originalAction.Arguments -cne $previousArguments) {
    throw 'Original owned action/arguments mismatch; refusing overwrite'
}
$arguments = '"{0}" dispatch --root "{1}" --profile live --provider public_composite --config "{2}" --expected-sha {3} --private-research --closed-session-research' -f $script, $resolvedRoot, $resolvedConfig, $ExpectedSha
$originalXml = Export-ScheduledTask -TaskName $TaskName -TaskPath '\'
$originalTriggers = $task.Triggers
$originalSettings = [Microsoft.Management.Infrastructure.CimInstance]::new($task.Settings)
$settings = [Microsoft.Management.Infrastructure.CimInstance]::new($task.Settings)
$settings.StartWhenAvailable = $true
$action = New-ScheduledTaskAction -Execute $resolvedPython -Argument $arguments -WorkingDirectory $resolvedTree
$trigger = New-CadenceTrigger
if (-not $Apply) {
    Write-Output "PREVIEW ONLY: $TaskName; source=$ExpectedSha; daily13:50 every1min for3h; same principal/canonical data; not started"
    return
}

if ([string]::IsNullOrWhiteSpace($BackupReceipt)) { throw 'Fresh canonical SQLite backup receipt required for Apply' }
$receiptPath = Assert-SafePath $BackupReceipt
$receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
$created = [DateTimeOffset]::Parse($receipt.created_at)
$age = ([DateTimeOffset]::UtcNow - $created).TotalHours
if ($receipt.source -ne $database -or $receipt.sqlite_backup_api -ne 'PASS' -or $receipt.quick_check -ne 'PASS' -or
    $receipt.sha256 -notmatch '^[a-f0-9]{64}$' -or $age -lt -0.1 -or $age -gt 24 -or $receipt.source_modified_by_backup -ne $false) {
    throw 'Canonical backup receipt qualification failed'
}
$backupFile = Assert-SafePath $receipt.backup_file
if (-not $backupFile.StartsWith((Join-Path $resolvedRoot 'backups\'), [StringComparison]::OrdinalIgnoreCase) -or
    (Get-Item -LiteralPath $backupFile).Length -ne $receipt.bytes -or
    (Get-FileHash -LiteralPath $backupFile -Algorithm SHA256).Hash.ToLowerInvariant() -cne $receipt.sha256) {
    throw 'Canonical backup file integrity failed'
}
$backupName = '{0}-pre-cadence-{1}.xml' -f $TaskName, $ExpectedSha.Substring(0, 7)
$xmlPath = Join-Path $resolvedBackup $backupName
$hashPath = "$xmlPath.sha256"
if ((Test-Path -LiteralPath $xmlPath) -or (Test-Path -LiteralPath $hashPath)) { throw 'Immutable task backup already exists' }
# Export-ScheduledTask declares UTF-16: write matching UTF16LE BOM atomically.
$stream = [IO.File]::Open($xmlPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try {
    $encoding = [Text.Encoding]::Unicode
    $preamble = $encoding.GetPreamble(); $body = $encoding.GetBytes($originalXml)
    $stream.Write($preamble, 0, $preamble.Length); $stream.Write($body, 0, $body.Length); $stream.Flush($true)
} finally { $stream.Dispose() }
$xmlHash = (Get-FileHash -LiteralPath $xmlPath -Algorithm SHA256).Hash.ToLowerInvariant()
$hashStream = [IO.File]::Open($hashPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try {
    $hashBytes = [Text.Encoding]::ASCII.GetBytes($xmlHash + "`n")
    $hashStream.Write($hashBytes, 0, $hashBytes.Length); $hashStream.Flush($true)
} finally { $hashStream.Dispose() }

# Recheck before mutation: a run or another owner's edit invalidates this plan.
$recheck = Get-ScheduledTask -TaskName $TaskName -TaskPath '\'
if ($recheck.State -ne 'Ready' -or (Export-ScheduledTask -TaskName $TaskName -TaskPath '\') -cne $originalXml) {
    throw 'Task changed after preview; backup retained, no mutation performed'
}
try {
    Set-ScheduledTask -TaskName $TaskName -TaskPath '\' -Action $action -Trigger $trigger -Settings $settings | Out-Null
    $updated = Get-ScheduledTask -TaskName $TaskName -TaskPath '\'
    $updatedXml = Export-ScheduledTask -TaskName $TaskName -TaskPath '\'
    Assert-TaskDefinition $updated $updatedXml $originalXml $arguments
    Write-Output "Migrated: $TaskName; source=$ExpectedSha; task backup SHA256=$xmlHash; not started manually"
} catch {
    $originalFailure = $_.Exception.GetType().Name
    try {
        Set-ScheduledTask -TaskName $TaskName -TaskPath '\' -Action $originalAction -Trigger $originalTriggers -Settings $originalSettings | Out-Null
        $restored = Get-ScheduledTask -TaskName $TaskName -TaskPath '\'
        Assert-TaskDefinition $restored (Export-ScheduledTask -TaskName $TaskName -TaskPath '\') $originalXml $previousArguments -Restored
    } catch { throw 'Migration failed and rollback verification failed; immutable backup retained; inspect owned task before further work' }
    throw "Migration rejected ($originalFailure); original task restored and verified; backup retained"
}

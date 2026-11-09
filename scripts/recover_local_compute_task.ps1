<# Recover the owned compute task when its working directory was deleted.
   Preview by default. The cadence migration script cannot cover this case:
   it requires the previous tree to still exist and be clean. Here the old
   tree is gone (LastTaskResult 0x8007010b ERROR_DIRECTORY), so the task is
   rebuilt from its own exported XML with only the action's tree path and
   --expected-sha replaced. Triggers, settings and principal are preserved
   byte-for-byte, the original XML is backed up immutably first, and the
   recovered task is registered DISABLED for a controlled first run. #>
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-f0-9]{40}$')][string]$ExpectedSha,
    [Parameter(Mandatory = $true)][ValidateSet('ETF-Local-Live-Compute')][string]$TaskName,
    [Parameter(Mandatory = $true)][string]$Workspace,
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$LocalRoot,
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][string]$BackupDirectory,
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

function Get-TaskSection([string]$XmlText, [string]$Name) {
    [xml]$document = $XmlText
    $node = $document.DocumentElement.SelectSingleNode("*[local-name()='$Name']")
    if ($null -eq $node) { throw 'Required task XML section missing' }
    return $node
}

function Find-DeadPathReferences([string]$DeadPath) {
    <# Report-only scan: every task whose action still points at the dead tree.
       Only $TaskName itself is ever modified by this script. #>
    $hits = @()
    foreach ($candidate in @(Get-ScheduledTask)) {
        foreach ($action in @($candidate.Actions)) {
            if ($action.WorkingDirectory -eq $DeadPath -or
                ([string]$action.Arguments).Contains($DeadPath) -or
                ([string]$action.Execute).StartsWith($DeadPath)) {
                $hits += '{0}{1}' -f $candidate.TaskPath, $candidate.TaskName
            }
        }
    }
    return $hits
}

if ((Get-TimeZone).Id -ne 'China Standard Time') { throw 'China Standard Time required; no timezone changes allowed' }
if ($ExpectedSha -eq ('0' * 40)) { throw 'Distinct nonzero source identity required' }
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
if (@($task.Actions).Count -ne 1) { throw 'Owned task must have exactly one action' }
$originalAction = $task.Actions[0]
$deadTree = [string]$originalAction.WorkingDirectory
if ([string]::IsNullOrWhiteSpace($deadTree)) { throw 'Original action has no working directory' }
if (Test-Path -LiteralPath $deadTree) {
    throw 'Original working directory still exists; use migrate_local_cadence_task.ps1 instead'
}
$oldArguments = [string]$originalAction.Arguments
$oldScript = Join-Path $deadTree 'scripts\run_local_compute.py'
if (-not $oldArguments.Contains($oldScript)) { throw 'Original arguments do not invoke the owned compute script under the dead tree; refusing free-form rewrite' }
$shaMatch = [regex]::Match($oldArguments, '--expected-sha\s+([0-9a-f]{40})')
if (-not $shaMatch.Success) { throw 'Original arguments carry no --expected-sha pin; refusing free-form rewrite' }
$oldSha = $shaMatch.Groups[1].Value
if ($oldSha -eq $ExpectedSha) { throw 'Original task already pins the target source identity' }
$newArguments = $oldArguments.Replace($oldScript, $script).Replace($oldSha, $ExpectedSha)
if ($newArguments -eq $oldArguments -or $newArguments.Contains($deadTree) -or -not $newArguments.Contains($ExpectedSha)) {
    throw 'Argument rewrite verification failed'
}
$references = Find-DeadPathReferences $deadTree
Write-Output "Dead tree: $deadTree"
Write-Output "Tasks still referencing the dead tree (report only): $($references -join ', ')"
Write-Output "New action: $resolvedPython $newArguments (working directory $resolvedTree)"
if (-not $Apply) {
    Write-Output "PREVIEW ONLY: $TaskName; dead=$deadTree; source=$ExpectedSha; not started"
    return
}

$originalXml = Export-ScheduledTask -TaskName $TaskName -TaskPath '\'
$backupName = '{0}-pre-recovery-{1}.xml' -f $TaskName, $ExpectedSha.Substring(0, 7)
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
if ((Export-ScheduledTask -TaskName $TaskName -TaskPath '\') -cne $originalXml) {
    throw 'Task changed after preview; backup retained, no mutation performed'
}
$escapedCommand = [System.Security.SecurityElement]::Escape($resolvedPython)
$escapedArguments = [System.Security.SecurityElement]::Escape($newArguments)
$escapedDirectory = [System.Security.SecurityElement]::Escape($resolvedTree)
$escapedOldCommand = [System.Security.SecurityElement]::Escape([string]$originalAction.Execute)
$escapedOldArguments = [System.Security.SecurityElement]::Escape($oldArguments)
$escapedOldDirectory = [System.Security.SecurityElement]::Escape($deadTree)
$newXml = $originalXml.Replace("<Command>$escapedOldCommand</Command>", "<Command>$escapedCommand</Command>")
$newXml = $newXml.Replace("<Arguments>$escapedOldArguments</Arguments>", "<Arguments>$escapedArguments</Arguments>")
$newXml = $newXml.Replace("<WorkingDirectory>$escapedOldDirectory</WorkingDirectory>", "<WorkingDirectory>$escapedDirectory</WorkingDirectory>")
if ($newXml -eq $originalXml -or $newXml.Contains($escapedOldDirectory)) { throw 'Task XML rewrite verification failed' }
try {
    Unregister-ScheduledTask -TaskName $TaskName -TaskPath '\' -Confirm:$false
    Register-ScheduledTask -TaskName $TaskName -TaskPath '\' -Xml $newXml | Out-Null
    Disable-ScheduledTask -TaskName $TaskName -TaskPath '\' | Out-Null
    $updated = Get-ScheduledTask -TaskName $TaskName -TaskPath '\'
    $updatedXml = Export-ScheduledTask -TaskName $TaskName -TaskPath '\'
    if (@($updated.Actions).Count -ne 1 -or $updated.Actions[0].Execute -ne $resolvedPython -or
        $updated.Actions[0].Arguments -cne $newArguments -or
        $updated.Actions[0].WorkingDirectory -ne $resolvedTree) { throw 'Recovered task action verification failed' }
    foreach ($section in @('Triggers', 'Settings', 'Principals')) {
        if ((Get-TaskSection $updatedXml $section).OuterXml -cne (Get-TaskSection $originalXml $section).OuterXml) {
            throw "Recovered task $section section changed"
        }
    }
    Write-Output "Recovered DISABLED: $TaskName; source=$ExpectedSha; task backup SHA256=$xmlHash; not started manually"
    Write-Output 'Next: run once under control, verify LastTaskResult and new artifacts, then Enable-ScheduledTask.'
} catch {
    $originalFailure = $_.Exception.GetType().Name
    try {
        if (Get-ScheduledTask -TaskName $TaskName -TaskPath '\' -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $TaskName -TaskPath '\' -Confirm:$false
        }
        Register-ScheduledTask -TaskName $TaskName -TaskPath '\' -Xml $originalXml | Out-Null
        $restored = Get-ScheduledTask -TaskName $TaskName -TaskPath '\'
        if ((Export-ScheduledTask -TaskName $TaskName -TaskPath '\') -cne $originalXml) { throw 'restore mismatch' }
    } catch { throw 'Recovery failed and rollback verification failed; immutable backup retained; inspect owned task before further work' }
    throw "Recovery rejected ($originalFailure); original task restored and verified; backup retained"
}

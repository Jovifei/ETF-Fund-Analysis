"""Local runner file privacy and child environment; no auth-file copying.

Windows ACL checks use SIDs, not localized account names. Existing insecure
folders fail closed. Only a newly created empty directory is provisioned.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess


class RuntimeSafetyError(ValueError):
    pass


def acl_is_private(value: dict, current_sid: str, *, require_protected: bool = True) -> bool:
    allowed = {current_sid, 'S-1-5-18', 'S-1-5-32-544'}
    if not current_sid or value.get('owner') != current_sid or (require_protected and value.get('protected') is not True):
        return False
    own = False
    for rule in value.get('rules', []):
        if rule.get('allow') is not True:
            continue
        if rule.get('sid') not in allowed:
            return False
        if rule.get('sid') == current_sid and int(rule.get('rights', 0)) & 2032127 == 2032127:
            own = True
    return own


def windows_private_directory(path: Path, *, created: bool, directory: bool = True) -> None:
    # Passing the target through an environment variable avoids PowerShell
    # interpolation of a path containing quotes/metacharacters.
    script = r'''
$ErrorActionPreference = 'Stop'
$p = $env:ETF_ACL_TARGET
$me = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
if ($env:ETF_ACL_CREATE -eq '1') {
    if ($env:ETF_ACL_DIRECTORY -eq '1') {
        $acl = New-Object System.Security.AccessControl.DirectorySecurity
        $inherit = 'ContainerInherit,ObjectInherit'
    } else {
        $acl = New-Object System.Security.AccessControl.FileSecurity
        $inherit = 'None'
    }
    $acl.SetOwner($me)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($me.Value, 'S-1-5-18', 'S-1-5-32-544')) {
        $who = New-Object System.Security.Principal.SecurityIdentifier($sid)
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($who, 'FullControl', $inherit, 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $p -AclObject $acl
}
$a = Get-Acl -LiteralPath $p
$rules = @($a.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]) | ForEach-Object {
    @{sid=$_.IdentityReference.Value;allow=($_.AccessControlType -eq 'Allow');rights=[int]$_.FileSystemRights}
})
@{current=$me.Value;owner=$a.GetOwner([System.Security.Principal.SecurityIdentifier]).Value;protected=$a.AreAccessRulesProtected;rules=$rules} | ConvertTo-Json -Depth 5 -Compress
'''
    env = {k: v for k, v in os.environ.items() if k in {'PATH', 'SystemRoot', 'WINDIR', 'TEMP', 'TMP'}}
    env.update(ETF_ACL_TARGET=str(path), ETF_ACL_CREATE='1' if created else '0', ETF_ACL_DIRECTORY='1' if directory else '0')
    try:
        run = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
            env=env, capture_output=True, text=True, timeout=20)
        value = json.loads(run.stdout) if run.returncode == 0 else {}
        if not acl_is_private(value, value.get('current', ''), require_protected=directory):
            raise RuntimeSafetyError('bridge_directory_acl_unsafe')
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        if isinstance(exc, RuntimeSafetyError):
            raise
        raise RuntimeSafetyError('bridge_directory_acl_not_verified') from None


def ensure_private_directory(path: Path) -> Path:
    # Check every existing component before resolve/mkdir so a symlink/junction
    # cannot redirect jobs or runner-home outside the dedicated tree.
    for component in (path, *path.parents):
        if component.is_symlink() or (hasattr(component, 'is_junction') and component.is_junction()):
            raise RuntimeSafetyError('symlink_directory_rejected')
    if not path.parent.exists():
        ensure_private_directory(path.parent)
    created = not path.exists()
    path.mkdir(mode=0o700, exist_ok=True)
    if not path.is_dir():
        raise RuntimeSafetyError('private_directory_required')
    if os.name == 'nt':
        windows_private_directory(path, created=created)
    else:
        if path.stat().st_uid != os.getuid():
            raise RuntimeSafetyError('bridge_directory_owner_mismatch')
        path.chmod(0o700)
    return path


def child_environment(home: Path) -> dict[str, str]:
    ensure_private_directory(home)
    codex_home = ensure_private_directory(home / '.codex')
    env = {k: v for k, v in os.environ.items() if k in {'PATH', 'SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'LANG'}}
    env.update(HOME=str(home), USERPROFILE=str(home), CODEX_HOME=str(codex_home))
    return env


def check_private_file(path: Path, *, created: bool = False) -> None:
    if path.is_symlink() or not path.is_file():
        raise RuntimeSafetyError('regular_private_file_required')
    if os.name == 'nt':
        windows_private_directory(path, created=created, directory=False)
    else:
        if path.stat().st_uid != os.getuid():
            raise RuntimeSafetyError('private_file_owner_mismatch')
        if created:
            path.chmod(0o600)
        elif path.stat().st_mode & 0o077:
            raise RuntimeSafetyError('private_file_permissions_unsafe')

"""Native NTFS descriptor access through pinned pywin32 (Windows only).

No PowerShell process, shell parsing, user-name translation or network call.
Only paths just created by the caller may have their ACL provisioned here.
"""
from __future__ import annotations
from pathlib import Path


def descriptor(path: Path, *, created: bool, directory: bool) -> dict:
    import win32api
    import win32con
    import win32security as security
    import ntsecuritycon

    token = security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        current = security.GetTokenInformation(token, security.TokenUser)[0]
    finally:
        token.Close()
    current_sid = security.ConvertSidToStringSid(current)
    info = security.OWNER_SECURITY_INFORMATION | security.DACL_SECURITY_INFORMATION
    if created:
        # A protected DACL contains only current user, SYSTEM and Administrators.
        # Never repair an existing broad directory behind the user's back.
        acl = security.ACL()
        inheritance = (security.OBJECT_INHERIT_ACE | security.CONTAINER_INHERIT_ACE) if directory else 0
        for sid in (current_sid, 'S-1-5-18', 'S-1-5-32-544'):
            acl.AddAccessAllowedAceEx(security.ACL_REVISION, inheritance,
                ntsecuritycon.FILE_ALL_ACCESS, security.ConvertStringSidToSid(sid))
        security.SetNamedSecurityInfo(str(path), security.SE_FILE_OBJECT,
            info | security.PROTECTED_DACL_SECURITY_INFORMATION, current, None, acl, None)
    sd = security.GetNamedSecurityInfo(str(path), security.SE_FILE_OBJECT, info)
    acl = sd.GetSecurityDescriptorDacl()
    control, _revision = sd.GetSecurityDescriptorControl()
    rules = []
    if acl is not None:
        for index in range(acl.GetAceCount()):
            ace = acl.GetAce(index)
            kind, flags = ace[0]
            if kind not in (security.ACCESS_ALLOWED_ACE_TYPE, security.ACCESS_DENIED_ACE_TYPE):
                raise ValueError('unreviewed_acl_entry')
            rules.append({'sid': security.ConvertSidToStringSid(ace[-1]),
                'allow': kind == security.ACCESS_ALLOWED_ACE_TYPE,
                # INHERIT_ONLY does not grant rights on the object itself.
                'rights': 0 if flags & security.INHERIT_ONLY_ACE else int(ace[1])})
    return {'current': current_sid,
        'owner': security.ConvertSidToStringSid(sd.GetSecurityDescriptorOwner()),
        'protected': bool(control & security.SE_DACL_PROTECTED), 'rules': rules}

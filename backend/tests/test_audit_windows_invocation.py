"""The native ACL adapter retains fail-closed policy without a shell process.

Replaces the encoded-PowerShell invocation experiment, not the real NTFS tests.
"""
from types import SimpleNamespace
import pytest
from app.workspace import bridge_runtime as runtime, windows_acl


def test_native_acl_never_spawns_shell_or_mutates_existing_directory(tmp_path,monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw:pytest.fail('ACL must not start shell'))
    me='S-1-5-21-1-2-3-1000';calls=[]
    def read(path,**kwargs):
        calls.append((path,kwargs))
        return {'current':me,'owner':me,'protected':True,'rules':[{'sid':me,'allow':True,'rights':2032127}]}
    monkeypatch.setattr(windows_acl,'descriptor',read)
    path=tmp_path/"with 'quotes' 中文"
    runtime.windows_private_directory(path,created=False)
    assert calls==[(path,{'created':False,'directory':True})]


def test_missing_native_dependency_is_not_acl_success(tmp_path,monkeypatch):
    def missing(*a,**kw):raise ImportError('no win32security')
    monkeypatch.setattr(windows_acl,'descriptor',missing)
    with pytest.raises(runtime.RuntimeSafetyError,match='dependency_missing'):
        runtime.windows_private_directory(tmp_path,created=False)


def test_unreadable_acl_is_rejected_without_os_details(tmp_path,monkeypatch):
    def failure(*a,**kw):raise OSError('private username/path')
    monkeypatch.setattr(windows_acl,'descriptor',failure)
    with pytest.raises(runtime.RuntimeSafetyError) as caught:
        runtime.windows_private_directory(tmp_path,created=False)
    assert str(caught.value)=='bridge_directory_acl_not_verified'

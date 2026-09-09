"""Owner-bound AES-GCM credentials. Master key is never stored in the database.

On Windows the file contains a CurrentUser DPAPI envelope; on Unix it is an
owner-only key file in a private directory. This is not a browser secret store.
"""
from __future__ import annotations
import base64
import ctypes
import os
from pathlib import Path
import stat
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.workspace.jobs import WorkspaceError

ROOT=Path(__file__).resolve().parents[3]


def _dpapi(data: bytes, *, decrypt=False) -> bytes:
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_char))]
    source=ctypes.create_string_buffer(data);inp=Blob(len(data),ctypes.cast(source,ctypes.POINTER(ctypes.c_char)));out=Blob()
    crypt=ctypes.windll.crypt32
    # CRYPTPROTECT_UI_FORBIDDEN: no interactive credential fallback.
    fn=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.restype=wintypes.BOOL
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    free=ctypes.windll.kernel32.LocalFree;free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p
    if not fn(ctypes.byref(inp),None,None,None,None,1,ctypes.byref(out)):
        raise WorkspaceError(503,'ai_key_store_unavailable')
    try:return ctypes.string_at(out.data,out.size)
    finally:free(out.data)


def key_path() -> Path:
    raw=os.environ.get('WORKSPACE_AI_KEY_FILE','')
    if not raw:raise WorkspaceError(503,'ai_key_store_not_configured')
    path=Path(raw).expanduser().absolute()
    if any(p.is_symlink() for p in (path,*path.parents)) or path.resolve().is_relative_to(ROOT):
        raise WorkspaceError(503,'ai_key_store_must_be_private_outside_repository')
    return path


def create_master(path: Path) -> None:
    os.environ['WORKSPACE_AI_KEY_FILE']=str(path)
    path=key_path()
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name!='nt' and (path.parent.stat().st_mode & 0o077):
        raise WorkspaceError(503,'ai_key_directory_permissions')
    key=os.urandom(32)
    payload=b'DPAPI1\n'+_dpapi(key) if os.name=='nt' else b'AESKEY1\n'+key
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())


def master() -> bytes:
    path=key_path()
    try:
        flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)
        fd=os.open(path,flags)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size>16384:
                raise WorkspaceError(503,'invalid_ai_key_file')
            if os.name!='nt' and (info.st_uid!=os.getuid() or info.st_mode & 0o077 or path.parent.stat().st_mode & 0o077):
                raise WorkspaceError(503,'ai_key_permissions')
            value=stream.read(16385)
        if os.name=='nt':
            if not value.startswith(b'DPAPI1\n'):raise WorkspaceError(503,'ai_dpapi_key_required')
            key=_dpapi(value[7:],decrypt=True)
        else:
            if not value.startswith(b'AESKEY1\n'):raise WorkspaceError(503,'invalid_ai_key_file')
            key=value[8:]
        if len(key)!=32:raise WorkspaceError(503,'invalid_ai_key_file')
        return key
    except WorkspaceError:raise
    except (OSError,ValueError):raise WorkspaceError(503,'ai_key_store_unavailable') from None


def encrypt(value: str, owner: str) -> str:
    nonce=os.urandom(12)
    return base64.b64encode(nonce+AESGCM(master()).encrypt(nonce,value.encode(),owner.encode())).decode()


def decrypt(value: str, owner: str) -> str:
    try:
        raw=base64.b64decode(value,validate=True)
        return AESGCM(master()).decrypt(raw[:12],raw[12:],owner.encode()).decode()
    except WorkspaceError:raise
    except Exception:raise WorkspaceError(503,'ai_credential_decryption_failed') from None

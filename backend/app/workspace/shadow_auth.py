"""Request authenticity and durable replay reservations for WRITE_ONLY_SHADOW."""
import hashlib,hmac,os,re
from datetime import datetime,timezone
from pathlib import Path
from secrets import token_hex
DOMAIN=b'ETF-SHADOW-REQUEST-V1\x00WRITE_ONLY_SHADOW\x00POST\x00/api/shadow/sync\x00'
SIGNED_PATHS=('/api/shadow/sync','/api/shadow/sync/chunk','/api/shadow/sync/commit')
def _domain(path):
    if path not in SIGNED_PATHS:raise ValueError('unsigned path')
    # The legacy single-request domain bytes are unchanged for /api/shadow/sync.
    return b'ETF-SHADOW-REQUEST-V1\x00WRITE_ONLY_SHADOW\x00POST\x00'+path.encode('ascii')+b'\x00'
def message(body,key_id,stamp,nonce,path='/api/shadow/sync'):
    return _domain(path)+key_id.encode('ascii')+b'\x00'+stamp.encode('ascii')+b'\x00'+nonce.encode('ascii')+b'\x00'+hashlib.sha256(body).digest()
def signed_headers(body,key_id,secret,*,now=None,nonce=None,path='/api/shadow/sync'):
    now=now or datetime.now(timezone.utc);stamp=now.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ');nonce=nonce or token_hex(16)
    if not re.fullmatch('[a-zA-Z0-9_-]{1,32}',key_id) or not re.fullmatch('[a-f0-9]{32}',nonce) or len(secret)<32:raise ValueError('signing configuration unavailable')
    signature=hmac.new(secret.encode('utf-8'),message(body,key_id,stamp,nonce,path),hashlib.sha256).hexdigest()
    return {'X-Shadow-Key-Id':key_id,'X-Shadow-Timestamp':stamp,'X-Shadow-Nonce':nonce,'X-Shadow-Signature':signature}
def verify_request(body,headers,root,active_key_id,secret,*,now=None,max_nonces=3000,path='/api/shadow/sync',domain=None):
    now=now or datetime.now(timezone.utc)
    key=headers.get('X-Shadow-Key-Id','');stamp=headers.get('X-Shadow-Timestamp','');nonce=headers.get('X-Shadow-Nonce','');signature=headers.get('X-Shadow-Signature','')
    if key!=active_key_id or not re.fullmatch('[a-zA-Z0-9_-]{1,32}',key) or len(secret)<32 or not re.fullmatch('[a-f0-9]{32}',nonce) or not re.fullmatch('[a-f0-9]{64}',signature):raise ValueError('request authentication rejected')
    try:created=datetime.strptime(stamp,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError:raise ValueError('request authentication rejected') from None
    if abs((now-created).total_seconds())>120:raise ValueError('request authentication rejected')
    expected=hmac.new(secret.encode('utf-8'),message(body,key,stamp,nonce,path),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature,expected):raise ValueError('request authentication rejected')
    root=Path(root)
    if root.is_symlink():raise ValueError('unsafe replay root')
    root.mkdir(parents=True,exist_ok=True);directory=root/'nonces'
    if directory.is_symlink():raise ValueError('unsafe replay directory')
    directory.mkdir(exist_ok=True);lock=directory/'reserve.lock'
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:raise ValueError('replay reservation busy') from None
    try:
        os.close(fd)
        for path in directory.iterdir():
            if re.fullmatch('[a-f0-9]{64}',path.name) and not path.is_symlink():
                expiry=float(path.read_text())
                if expiry<now.timestamp():path.unlink()
        if len(list(directory.iterdir()))-1>=max_nonces:raise ValueError('replay budget exhausted')
        if domain is not None:domain.reserve(64)
        identity=hashlib.sha256((key+'\x00'+nonce).encode('ascii')).hexdigest();path=directory/identity
        try:fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError:raise ValueError('request replay rejected') from None
        with os.fdopen(fd,'w') as handle:handle.write(str(created.timestamp()+241));handle.flush();os.fsync(handle.fileno())
    finally:lock.unlink(missing_ok=True)

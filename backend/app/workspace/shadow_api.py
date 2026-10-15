"""Disabled-by-default shadow synchronization; producer authority is write-only."""
import hmac
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.core.config import get_settings
from app.core.security import require_current_user, require_private_access
from app.workspace.shadow_bundle import ShadowStore
from app.workspace.shadow_auth import verify_request
router=APIRouter(prefix='/api/shadow',tags=['shadow'])
def store():
    settings=get_settings()
    if not settings.shadow_sync_enabled:raise HTTPException(404,'shadow disabled')
    return ShadowStore(settings.shadow_sync_root,code_sha=settings.shadow_sync_code_sha,config_hash=settings.shadow_sync_config_hash,max_bytes=settings.shadow_sync_max_bytes,max_generations=settings.shadow_sync_max_generations)
def sync_domain(settings):
    from app.workspace.sync_domain import SyncDomain
    return SyncDomain(settings.shadow_sync_root,
                      roots=(getattr(settings, 'local_display_v2_store_root', settings.shadow_sync_root),),
                      max_bytes=getattr(settings, 'local_display_v2_max_bytes', 67108864))


def _verify(body, request, settings, domain, *, path='/api/shadow/sync'):
    try:
        verify_request(body,request.headers,settings.shadow_sync_root,settings.shadow_sync_active_key_id,
                       settings.shadow_sync_signing_secret.get_secret_value(),path=path,domain=domain)
    except (ValueError,OSError):
        raise HTTPException(401, 'request authentication rejected') from None


@router.post('/sync')
async def sync(request: Request):
    target=store();settings=get_settings();_producer_auth(request,settings)
    raw=await _read_bounded(request,settings.shadow_sync_max_request_bytes)
    domain=sync_domain(settings)
    try:
        with domain.locked():
            _verify(raw,request,settings,domain)
            if request.headers.get('content-encoding','').lower() == 'gzip':
                import gzip
                from io import BytesIO
                limit=min(getattr(settings,'local_display_v2_max_decompressed_bytes',67108864),
                          settings.shadow_sync_max_request_bytes)
                if type(limit) is not int or limit <= 0:
                    raise HTTPException(413,'invalid decompressed bundle limit')
                try:
                    with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:
                        raw=stream.read(limit+1)
                except Exception:
                    raise HTTPException(400,'invalid gzip payload') from None
                if len(raw)>limit:
                    raise HTTPException(413,'decompressed bundle too large')
            return _publish_decoded(raw,target,settings,domain)
    except HTTPException:
        raise
    except (ValueError,TypeError,KeyError,OSError,RecursionError):
        raise HTTPException(409,'bundle rejected') from None


def _publish_decoded(raw_body,target,settings,domain=None):
    """Shared atomic publish for single-request and reassembled chunked bundles."""
    import json
    value = json.loads(raw_body)
    if not isinstance(value, dict) or not isinstance(value.get('manifest'), dict):
        raise ValueError('invalid bundle envelope')
    manifest = value.get('manifest', {})
    contract = manifest.get('contract_version') or manifest.get('contract')
    if contract == 'local-display-v2':
        import re
        approved_sha = getattr(settings, 'shadow_sync_code_sha', '')
        approved_config = getattr(settings, 'shadow_sync_config_hash', '')
        if not re.fullmatch(r'[0-9a-f]{40}', approved_sha) or not re.fullmatch(r'[0-9a-f]{64}', approved_config):
            raise ValueError('approved runtime identity unavailable')
        if manifest.get('code_sha') != approved_sha or manifest.get('config_hash') != approved_config:
            raise ValueError('runtime identity mismatch')
        from app.workspace.local_display_read import LocalDisplayStore
        store_v2 = LocalDisplayStore(settings.local_display_v2_store_root, max_bytes=getattr(settings, 'local_display_v2_max_bytes', 67108864),domain=domain)
        return store_v2.publish(value)
    if domain is not None:
        # V1 retains its own exact receipt/validation contract, but shares the disk
        # domain. This conservative peak allowance covers blobs, manifest and pointers.
        domain.reserve(2 * len(raw_body) + 4096)
    return target.publish(value)


def _producer_auth(request,settings):
    secret=settings.shadow_sync_producer_token.get_secret_value()
    supplied=request.headers.get('Authorization','')
    if len(secret)<32 or not hmac.compare_digest(supplied.encode('utf-8'),('Bearer '+secret).encode('utf-8')):raise HTTPException(401,'producer credential required')


async def _read_bounded(request,limit):
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>limit:raise HTTPException(413,'request too large')
    return bytes(body)


@router.post('/sync/chunk')
async def sync_chunk(request:Request):
    from app.workspace.shadow_chunks import CHUNK_MAX_WIRE_BYTES, ChunkBusy, ChunkRejected, ChunkStaging, chunk_meta
    store();settings=get_settings();_producer_auth(request,settings)
    wire=await _read_bounded(request,CHUNK_MAX_WIRE_BYTES)
    h=request.headers
    try:
        upload_id=h.get('X-Chunk-Upload-Id','');index=int(h.get('X-Chunk-Index',''));total=int(h.get('X-Chunk-Total',''));chunk_sha=h.get('X-Chunk-Sha256','')
        signed=chunk_meta(upload_id,index,total,chunk_sha)+b'\n'+wire
    except (ValueError,UnicodeError):
        raise HTTPException(400,'invalid chunk headers') from None
    domain=sync_domain(settings)
    try:
        with domain.locked():
            _verify(signed,request,settings,domain,path='/api/shadow/sync/chunk')
            return ChunkStaging(settings.shadow_sync_root,domain=domain).put(upload_id,index,total,chunk_sha,wire)
    except ChunkBusy:
        raise HTTPException(409,'chunk staging busy') from None
    except ChunkRejected as exc:
        raise HTTPException(422,str(exc)) from None
    except (ValueError,OSError):
        raise HTTPException(409,'sync domain rejected') from None


@router.post('/sync/commit')
async def sync_commit(request:Request):
    import json
    from app.workspace.shadow_chunks import ChunkRejected, ChunkStaging
    target=store();settings=get_settings();_producer_auth(request,settings)
    body=await _read_bounded(request,512)
    domain=sync_domain(settings)
    try:
        with domain.locked():
            _verify(body,request,settings,domain,path='/api/shadow/sync/commit')
            spec=json.loads(body)
            if not isinstance(spec,dict) or set(spec)!={'upload_id','total'}:
                raise HTTPException(400,'invalid commit')
            return ChunkStaging(settings.shadow_sync_root,domain=domain).commit(
                spec['upload_id'],spec['total'],lambda raw:_publish_decoded(raw,target,settings,domain))
    except ChunkRejected as exc:
        raise HTTPException(422,str(exc)) from None
    except HTTPException:
        raise
    except (ValueError,TypeError,KeyError,OSError,RecursionError):
        raise HTTPException(409,'bundle rejected') from None


@router.get('/bundle',dependencies=[Depends(require_private_access),Depends(require_current_user)])
def bundle(response:Response,bundle_id:str|None=None):
    response.headers["Cache-Control"]="private, no-store"
    settings = get_settings()
    if getattr(settings, 'workspace_research_source', 'database') == 'local_bundle':
        from app.workspace.local_display_read import LocalDisplayStore
        store_v2 = LocalDisplayStore(settings.local_display_v2_store_root, max_bytes=getattr(settings, 'local_display_v2_max_bytes', 67108864))
        loaded = store_v2.load_bundle(generation=bundle_id)
        if not loaded:
            raise HTTPException(410, 'local display bundle unavailable or expired')
        return loaded
    try:return store().read(bundle_id=bundle_id)
    except (ValueError,KeyError,FileNotFoundError):raise HTTPException(410,'shadow bundle unavailable or expired') from None

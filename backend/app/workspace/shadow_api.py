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
@router.post('/sync')
async def sync(request:Request):
    target=store();settings=get_settings();secret=settings.shadow_sync_producer_token.get_secret_value()
    supplied=request.headers.get('Authorization','')
    if len(secret)<32 or not hmac.compare_digest(supplied.encode('utf-8'),('Bearer '+secret).encode('utf-8')):raise HTTPException(401,'producer credential required')
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>settings.shadow_sync_max_request_bytes:raise HTTPException(413,'bundle too large')
    try:
        verify_request(bytes(body),request.headers,settings.shadow_sync_root,settings.shadow_sync_active_key_id,settings.shadow_sync_signing_secret.get_secret_value())
    except (ValueError,OSError):raise HTTPException(401,"request authentication rejected") from None
    try:
        raw_body = bytes(body)
        if request.headers.get('content-encoding', '').lower() == 'gzip':
            import gzip
            try:
                from io import BytesIO
                limit = getattr(settings, 'local_display_v2_max_decompressed_bytes', 67108864)
                if type(limit) is not int or limit <= 0:
                    raise HTTPException(413, 'invalid decompressed bundle limit')
                with gzip.GzipFile(fileobj=BytesIO(raw_body)) as stream:
                    raw_body = stream.read(limit + 1)
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(400, 'invalid gzip payload')
            max_decompressed = getattr(settings, 'local_display_v2_max_decompressed_bytes', 67108864)
            if len(raw_body) > max_decompressed:
                raise HTTPException(413, 'decompressed bundle too large')
        return _publish_decoded(raw_body,target,settings)
    except HTTPException:
        raise
    except (ValueError,TypeError,KeyError,FileNotFoundError,RecursionError):raise HTTPException(409,'bundle rejected') from None


def _publish_decoded(raw_body,target,settings):
    """Shared atomic publish for single-request and reassembled chunked bundles."""
    import json
    value = json.loads(raw_body)
    if not isinstance(value, dict) or not isinstance(value.get('manifest'), dict):
        raise ValueError('invalid bundle envelope')
    manifest = value.get('manifest', {})
    contract = manifest.get('contract_version') or manifest.get('contract')
    if contract == 'local-display-v2':
        from app.workspace.local_display_read import LocalDisplayStore
        store_v2 = LocalDisplayStore(settings.local_display_v2_store_root, max_bytes=getattr(settings, 'local_display_v2_max_bytes', 67108864))
        return store_v2.publish(value)
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
    except ValueError:raise HTTPException(400,'invalid chunk headers') from None
    try:
        verify_request(chunk_meta(upload_id,index,total,chunk_sha)+b'\n'+wire,h,settings.shadow_sync_root,settings.shadow_sync_active_key_id,settings.shadow_sync_signing_secret.get_secret_value(),path='/api/shadow/sync/chunk')
    except (ValueError,OSError):raise HTTPException(401,'request authentication rejected') from None
    try:return ChunkStaging(settings.shadow_sync_root).put(upload_id,index,total,chunk_sha,wire)
    except ChunkBusy:raise HTTPException(409,'chunk staging busy') from None
    except ChunkRejected as exc:raise HTTPException(422,str(exc)) from None


@router.post('/sync/commit')
async def sync_commit(request:Request):
    import json
    from app.workspace.shadow_chunks import ChunkRejected, ChunkStaging
    target=store();settings=get_settings();_producer_auth(request,settings)
    body=await _read_bounded(request,512)
    try:
        verify_request(body,request.headers,settings.shadow_sync_root,settings.shadow_sync_active_key_id,settings.shadow_sync_signing_secret.get_secret_value(),path='/api/shadow/sync/commit')
    except (ValueError,OSError):raise HTTPException(401,'request authentication rejected') from None
    try:
        spec=json.loads(body)
        if not isinstance(spec,dict) or set(spec)!={'upload_id','total'}:raise ValueError('invalid commit')
        raw=ChunkStaging(settings.shadow_sync_root).assemble(spec['upload_id'],spec['total'])
    except ChunkRejected as exc:raise HTTPException(422,str(exc)) from None
    except (ValueError,TypeError):raise HTTPException(400,'invalid commit') from None
    try:return _publish_decoded(raw,target,settings)
    except HTTPException:raise
    except (ValueError,TypeError,KeyError,FileNotFoundError,RecursionError):raise HTTPException(409,'bundle rejected') from None


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

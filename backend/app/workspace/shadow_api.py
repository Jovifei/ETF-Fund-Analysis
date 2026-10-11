"""Disabled-by-default shadow synchronization; producer authority is write-only."""
import hmac
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.core.config import get_settings
from app.core.security import require_current_user, require_private_access
from app.workspace.shadow_bundle import ShadowStore
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
        import json
        value=json.loads(body)
        return target.publish(value)
    except (ValueError,TypeError,KeyError,FileNotFoundError):raise HTTPException(409,'bundle rejected') from None
@router.get('/bundle',dependencies=[Depends(require_private_access),Depends(require_current_user)])
def bundle(response:Response,bundle_id:str|None=None):
    response.headers["Cache-Control"]="private, no-store"
    try:return store().read(bundle_id=bundle_id)
    except (ValueError,KeyError,FileNotFoundError):raise HTTPException(410,'shadow bundle unavailable or expired') from None

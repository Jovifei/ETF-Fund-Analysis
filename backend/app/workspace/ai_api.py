"""User-owned API configuration; sensitive validation never echoes inputs."""
from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session
from pydantic import Field
from app.db.session import get_db
from app.core.security import require_current_user,require_enrolled_admin
from app.models import AuthUser
from app.workspace import ai_profiles as svc,memberships
from app.workspace.jobs import WorkspaceError
from app.workspace.protocol import StrictModel,JobId
from app.workspace.data_jobs import view as job_view

class SafeRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handler(request:Request):
            # Catch Pydantic's input field and raw JSON errors before FastAPI's
            # default handler can echo an API key from a malformed request.
            try:
                if request.headers.get('content-length') and int(request.headers['content-length'])>16000:
                    return JSONResponse({'detail':'ai_request_too_large'},413)
                if request.method in {'POST','PUT','PATCH'}:
                    raw=bytearray()
                    async for chunk in request.stream():
                        raw.extend(chunk)
                        if len(raw)>16000:
                            return JSONResponse({'detail':'ai_request_too_large'},413,headers={'Cache-Control':'no-store'})
                    request._body=bytes(raw)
                response=await original(request)
                response.headers['Cache-Control']='private, no-store'
                return response
            except RequestValidationError:return JSONResponse({'detail':'invalid_ai_configuration_or_request'},422)
            except WorkspaceError as exc:return JSONResponse({'detail':exc.code},exc.status)
            except ValueError:return JSONResponse({'detail':'invalid_request'},422)
        return handler

router=APIRouter(prefix='/workspace/ai',route_class=SafeRoute)
DB=Annotated[Session,Depends(get_db)]
User=Annotated[AuthUser,Depends(require_current_user)]
Admin=Annotated[AuthUser,Depends(require_enrolled_admin)]

class Run(StrictModel):
    confirm_cost: bool
    request_key: str=Field(pattern=r'^[a-zA-Z0-9_-]{16,64}$')

class ResearchRun(Run):
    research_id: JobId

@router.get('/profiles')
def profiles(db:DB,user:User):return svc.list_profiles(db,user.id)

@router.post('/profiles',status_code=201)
def create(payload:svc.ProfileInput,db:DB,user:User):
    result=svc.save(db,user.id,payload);db.commit();return result

@router.put('/profiles/{profile_id}')
def update(profile_id:JobId,payload:svc.ProfileInput,db:DB,user:User):
    result=svc.save(db,user.id,payload,profile_id);db.commit();return result

@router.delete('/profiles/{profile_id}')
def remove(profile_id:JobId,db:DB,user:User):
    svc.remove(db,user.id,profile_id);db.commit();return {'deleted':True}

@router.post('/profiles/{profile_id}/default')
def default(profile_id:JobId,db:DB,user:User):
    svc.set_default(db,user.id,profile_id);db.commit();return {'default_id':profile_id}

@router.post('/profiles/{profile_id}/test',status_code=202)
def test(profile_id:JobId,payload:Run,db:DB,user:User):
    if not payload.confirm_cost:raise WorkspaceError(422,'explicit_model_cost_consent_required')
    row,created=svc.enqueue(db,user.id,profile_id,request_key=payload.request_key)
    db.commit();return {'job':job_view(row),'created':created,'model_called':False}

@router.post('/profiles/{profile_id}/run',status_code=202)
def run(profile_id:JobId,payload:ResearchRun,db:DB,user:User):
    if not payload.confirm_cost:raise WorkspaceError(422,'explicit_model_cost_consent_required')
    row,created=svc.enqueue(db,user.id,profile_id,research_id=payload.research_id,request_key=payload.request_key)
    db.commit();return {'job':job_view(row),'created':created,'model_called':False}

members=APIRouter(prefix='/workspace',route_class=SafeRoute)
@members.get('/membership')
def membership(db:DB,user:User):return {**memberships.meta(db,user.id),'policy':memberships.policy(db)}

@members.get('/members')
def member_list(db:DB,user:Admin):
    from sqlalchemy import select
    users=db.scalars(select(AuthUser).order_by(AuthUser.id).limit(1000)).all()
    # Small private installation; never expose credentials or user portfolios.
    return {'items':[{'id':u.id,'username':u.username,'role':u.role,'status':u.status,**memberships.meta(db,u.id)} for u in users],
        'policy':memberships.policy(db),'removal':'reversible_disable_retains_private_data'}

@members.post('/members/{user_id}')
def member_update(user_id:int,payload:memberships.Change,db:DB,user:Admin):
    result=memberships.change(db,user,user_id,payload);db.commit();return result

@members.put('/membership-policy')
def policy_update(payload:memberships.Policy,db:DB,user:Admin):
    result=memberships.set_policy(db,user,payload);db.commit();return result

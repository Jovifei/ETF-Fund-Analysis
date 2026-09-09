"""Account tiers and reversible removal. No billing, no portfolio deletion.

Feature enforcement is opt-in. Both middleware and the worker apply the same
policy so hiding a navigation item is never the access-control boundary.
"""
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4
from pydantic import Field
from sqlalchemy import func, select
from app.models import AuthUser
from app.services.auth_service import AuthService, UserLifecycleError
from app.workspace.jobs import WorkspaceError, lock_owner
from app.workspace.models import WorkspacePreference
from app.workspace.protocol import StrictModel

POLICY='membership:policy'
FEATURES=('api_research','factor_research','monthly_research')

class Policy(StrictModel):
    enabled: bool=False
    plus_features: list[Literal['api_research','factor_research','monthly_research']]=Field(default_factory=list,max_length=3)

class Change(StrictModel):
    action: Literal['plan','role','disable','reactivate','remove','restore']
    plan: Literal['free','plus']|None=None
    role: Literal['member','admin']|None=None
    confirm_username: str=Field(min_length=1,max_length=128)


def meta(db,user_id):
    row=db.get(WorkspacePreference,'membership:'+str(user_id))
    return dict(row.settings_json) if row else {'plan':'free','removed':False}


def plan_for(db,user_id): return meta(db,user_id).get('plan','free')


def policy(db):
    row=db.get(WorkspacePreference,POLICY)
    return Policy.model_validate(row.settings_json if row else {}).model_dump()


def check_feature(db,user,feature):
    if not user or user.role=='admin':return
    cfg=policy(db)
    if cfg['enabled'] and feature in cfg['plus_features'] and plan_for(db,user.id)!='plus':
        raise WorkspaceError(403,'plus_feature_required')


def path_feature(path):
    if path.startswith('/api/workspace/ai/') and path.endswith(('/test','/run')):return 'api_research'
    if path.startswith(('/api/workspace/factor','/api/factor')):return 'factor_research'
    if path.startswith('/api/workspace/research-outlook'):return 'monthly_research'
    return None


def audit(db,actor,target,action,old,new):
    db.add(WorkspacePreference(owner_scope='member:audit:'+uuid4().hex,user_id=actor.id,
        settings_json={'actor_id':actor.id,'target_id':target,'action':action,'before':old,'after':new,'at':datetime.now(UTC).isoformat()}))


def change(db,actor,target_id,data:Change):
    if actor.role!='admin' or actor.status!='active':raise WorkspaceError(403,'administrator_access_required')
    service=AuthService();service._acquire_bootstrap_guard(db)
    target=db.get(AuthUser,target_id)
    if not target:raise WorkspaceError(404,'account_not_found')
    if target.username!=data.confirm_username.strip().casefold():raise WorkspaceError(409,'confirm_target_username')
    if actor.id==target_id and data.action in ('role','disable','remove'):raise WorkspaceError(409,'cannot_change_own_access')
    old={'role':target.role,'status':target.status,**meta(db,target_id)};extra=meta(db,target_id)
    if data.action=='plan':
        if data.plan is None:raise WorkspaceError(422,'plan_required')
        extra['plan']=data.plan
    elif data.action=='role':
        if data.role is None or target.status!='active':raise WorkspaceError(422,'active_account_and_role_required')
        if target.role=='admin' and data.role!='admin':
            total=db.scalar(select(func.count()).select_from(AuthUser).where(AuthUser.role=='admin',AuthUser.status=='active')) or 0
            if total<=1:raise WorkspaceError(409,'last_active_admin_protected')
        target.role=data.role;service.revoke_user_sessions(db,target_id)
    elif data.action in ('remove','disable'):
        try:service.disable_user(db,target_id)
        except UserLifecycleError:raise WorkspaceError(409,'last_active_admin_protected') from None
        if data.action=='remove':extra['removed']=True
    else:
        if data.action=='reactivate' and extra.get('removed'):raise WorkspaceError(409,'restore_removed_user_first')
        service.reactivate_user(db,target_id);extra['removed']=False
    row=db.get(WorkspacePreference,'membership:'+str(target_id))
    if not row:row=WorkspacePreference(owner_scope='membership:'+str(target_id),user_id=target_id);db.add(row)
    row.settings_json=extra
    new={'role':target.role,'status':target.status,**extra};audit(db,actor,target_id,data.action,old,new);db.flush()
    return {'id':target.id,'username':target.username,**new}


def set_policy(db,actor,data:Policy):
    lock_owner(db,'membership:policy:lock');old=policy(db)
    row=db.get(WorkspacePreference,POLICY)
    if row is None:row=WorkspacePreference(owner_scope=POLICY);db.add(row)
    row.settings_json=data.model_dump();audit(db,actor,None,'policy',old,row.settings_json);db.flush()
    return row.settings_json

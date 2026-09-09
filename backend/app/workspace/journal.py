"""Private human review notes, independent of forecasts and shared strategies."""
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from app.core.config import Settings, get_settings
from app.core.security import optional_current_user
from app.db.session import get_db
from app.models import AuthUser
from app.services.decision_board_service import DecisionBoardService
from app.workspace.jobs import owner_scope, lock_owner
from app.workspace.models import WorkspacePreference
from app.workspace.protocol import StrictModel, safe_text, content_hash

router=APIRouter(prefix='/workspace/review-notes')
DB=Annotated[Session,Depends(get_db)]
User=Annotated[AuthUser|None,Depends(optional_current_user)]
Config=Annotated[Settings,Depends(get_settings)]


class Note(StrictModel):
    revision: int=Field(default=0,ge=0,le=100000)
    thesis: str=Field(min_length=1,max_length=6000)
    outcome: str=Field(default='',max_length=4000)
    proposal: str=Field(default='',max_length=4000)

    @field_validator('thesis','outcome','proposal')
    @classmethod
    def safe(cls,value): return safe_text(value)


def scope(user_id):
    return 'journal:'+content_hash(owner_scope(user_id))[:16]+':'


@router.get('')
def recent(db:DB,user:User,response:Response,limit:int=Query(default=30,ge=1,le=100)):
    response.headers['Cache-Control']='private, no-store'
    prefix=scope(user.id if user else None)
    rows=db.scalars(select(WorkspacePreference).where(WorkspacePreference.owner_scope.startswith(prefix)).order_by(WorkspacePreference.owner_scope.desc()).limit(limit)).all()
    return {'items':[row.settings_json for row in rows],'model_called':False,'actionable':False}


@router.get('/{day}')
def get_note(day:date,db:DB,user:User,response:Response):
    response.headers['Cache-Control']='private, no-store'
    row=db.get(WorkspacePreference,scope(user.id if user else None)+day.isoformat())
    return {'note':row.settings_json if row else None,'model_called':False,'actionable':False}


@router.put('/{day}')
def save_note(day:date,payload:Note,db:DB,user:User,settings:Config):
    if day>datetime.now(ZoneInfo('Asia/Shanghai')).date():
        raise HTTPException(422,'future_review_date_rejected')
    user_id=user.id if user else None
    key=scope(user_id)+day.isoformat()
    lock_owner(db,key)
    row=db.get(WorkspacePreference,key)
    previous=dict(row.settings_json or {}) if row else {}
    if payload.revision!=previous.get('revision',0):
        raise HTTPException(409,'review_note_revision_conflict')
    # Context is captured at authoring time, NOT pretended to be known on day.
    board = (DecisionBoardService(settings).read_latest(db) or {}) if not previous else {}
    context=previous.get('context') or {'snapshot_id':board.get('snapshot_id'),
        'snapshot_generated_at':board.get('generated_at'), 'snapshot_hash':content_hash(board)}
    data={'day':day.isoformat(),'revision':payload.revision+1,'source':'manual',
        'thesis':payload.thesis,'outcome':payload.outcome,'proposal':payload.proposal,
        'saved_at':datetime.now(UTC).isoformat(),'context':context,'previous_hash':previous.get('note_hash'),
        'actionable':False,'strategy_modified':False}
    data['note_hash']=content_hash(data)
    history=list(previous.get('recent_revisions',[]))
    if previous: history.append({k:v for k,v in previous.items() if k!='recent_revisions'})
    data['recent_revisions']=history[-20:]
    try:
        if row is None:
            db.add(WorkspacePreference(owner_scope=key,user_id=user_id,settings_json=data));db.flush()
        else:
            changed=db.execute(update(WorkspacePreference).where(WorkspacePreference.owner_scope==key,
                WorkspacePreference.settings_json['revision'].as_integer()==payload.revision).values(settings_json=data))
            if changed.rowcount!=1: raise HTTPException(409,'review_note_revision_conflict')
        db.commit()
    except (IntegrityError,OperationalError):
        db.rollback();raise HTTPException(409,'review_note_revision_conflict') from None
    return {'note':data,'model_called':False,'strategy_modified':False}

"""A-U1: bounded self-service account operations, separate from admin controls.

Contact providers are deliberately unavailable until verified delivery/OAuth is
implemented and configured. An existing email column is NOT proof of ownership.
Closure disables access and preserves records; it is not permanent erasure.
"""
from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool, field_validator
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import csrf_cookie_name, require_current_user, require_private_access, session_cookie_name
from app.db.session import get_db
from app.models import AuthUser
from app.services.auth_service import AuthService, LastActiveAdminError
from app.workspace.memberships import plan_for
from app.workspace.models import WorkspaceBridgeDevice, WorkspaceDataJob, WorkspacePreference, WorkspaceResearchJob


class AccountRoute(APIRoute):
    """Never echo a submitted password/contact in a validation error."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                    body = bytearray()
                    async for chunk in request.stream():
                        body.extend(chunk)
                        if len(body) > 8192:
                            raise HTTPException(413, "account_request_too_large")
                    request._body = bytes(body)
                response = await original(request)
            except RequestValidationError:
                response = JSONResponse({"detail": "invalid_account_request"}, status_code=422)
            except HTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return handler


router = APIRouter(prefix="/api/workspace/account", route_class=AccountRoute,
                   dependencies=[Depends(require_private_access)])
DB = Annotated[Session, Depends(get_db)]
User = Annotated[AuthUser, Depends(require_current_user)]
Config = Annotated[Settings, Depends(get_settings)]


class AccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")  # Do not strip or normalize passwords.


class ProfileInput(AccountInput):
    display_name: str = Field(min_length=1, max_length=48)

    @field_validator("display_name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        value = unicodedata.normalize("NFC", value).strip()
        if not value or any(unicodedata.category(c).startswith("C") for c in value):
            raise ValueError("invalid_display_name")
        return value


class PasswordInput(AccountInput):
    current_password: SecretStr = Field(min_length=1, max_length=1024)
    new_password: SecretStr = Field(min_length=15, max_length=1024)


class ClosureInput(AccountInput):
    current_password: SecretStr = Field(min_length=1, max_length=1024)
    confirmation: Literal["注销当前账户"]
    acknowledge_retention: StrictBool

    @field_validator("acknowledge_retention")
    @classmethod
    def acknowledged(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("retention_acknowledgement_required")
        return value


def _preference(db: Session, user_id: int, kind: str) -> WorkspacePreference:
    scope = f"account:{kind}:{user_id}"
    row = db.get(WorkspacePreference, scope)
    if row is None:
        row = WorkspacePreference(owner_scope=scope, user_id=user_id, settings_json={})
        db.add(row)
    return row


def _audit(db: Session, user_id: int, action: str) -> None:
    # Event names and time only: no passwords, cookie/session token or contact.
    db.add(WorkspacePreference(owner_scope="account:audit:" + uuid4().hex,
                               user_id=user_id, settings_json={"action": action, "at": datetime.now(UTC).isoformat()}))


def _lock_current(db: Session, user: AuthUser, request: Request, settings: Settings) -> AuthUser:
    svc = AuthService()
    svc._acquire_bootstrap_guard(db)  # Same lifecycle lock used by admin disable.
    if not svc.session_is_current_for_user(db, request.cookies.get(session_cookie_name(settings)), user.id):
        db.rollback()
        raise HTTPException(401, "database_user_session_required")
    current = db.get(AuthUser, user.id, populate_existing=True)
    if current is None or current.status != "active":
        db.rollback()
        raise HTTPException(401, "database_user_session_required")
    return current


def _reauthenticate(db: Session, user: AuthUser, password: SecretStr) -> None:
    # Database-backed across API workers. Wrong-password attempts commit only
    # the bounded counter; successful mutations reset it in their transaction.
    row = _preference(db, user.id, "reauth")
    state = dict(row.settings_json)
    now = int(datetime.now(UTC).timestamp())
    start = int(state.get("window_start", now))
    count = int(state.get("failures", 0))
    if now - start >= 900 or now < start:
        start, count = now, 0
    if count >= 5:
        db.rollback()
        raise HTTPException(429, "account_reauthentication_limited", headers={"Retry-After": str(max(1, 900 - (now - start)))})
    if not AuthService().verify_password(password.get_secret_value(), user.password_hash):
        row.settings_json = {"window_start": start, "failures": count + 1}
        db.commit()
        raise HTTPException(403, "current_password_invalid")
    row.settings_json = {"window_start": now, "failures": 0}


def _clear_cookies(response: Response, settings: Settings) -> None:
    for name in (session_cookie_name(settings), csrf_cookie_name(settings)):
        response.delete_cookie(name, path="/", secure=settings.auth_cookie_secure, samesite="lax")


def account_view(db: Session, user: AuthUser) -> dict:
    row = db.get(WorkspacePreference, f"account:profile:{user.id}")
    meta = row.settings_json if row else {}
    email = user.email or ""
    local, sep, domain = email.partition("@")
    masked = f"{local[:1]}***@{domain}" if sep else "***" if email else None
    return {
        "identifier": user.username, "display_name": meta.get("display_name", user.username),
        "role": user.role, "plan": plan_for(db, user.id), "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "email": {"masked": masked, "state": "recorded_unverified" if email else "not_bound"},
        "phone": {"masked": None, "state": "unavailable"},
        "wechat": {"masked": None, "state": "unavailable"},
        "capabilities": {"profile": True, "change_password": True, "close_access": True,
                         "email_verification": False, "sms_verification": False,
                         "wechat_oauth": False, "permanent_erasure": False},
        "closure_policy": "access_disabled_records_retained",
    }


@router.get("")
def profile(db: DB, user: User) -> dict:
    return account_view(db, user)


@router.patch("/profile")
def update_profile(payload: ProfileInput, request: Request, db: DB, user: User, settings: Config) -> dict:
    current = _lock_current(db, user, request, settings)
    row = _preference(db, user.id, "profile")
    row.settings_json = {**row.settings_json, "display_name": payload.display_name}
    _audit(db, user.id, "display_name_changed")
    db.commit()
    return account_view(db, current)


@router.put("/password")
def change_password(payload: PasswordInput, request: Request, response: Response, db: DB, user: User, settings: Config) -> dict:
    current = _lock_current(db, user, request, settings)
    _reauthenticate(db, current, payload.current_password)
    if payload.current_password.get_secret_value() == payload.new_password.get_secret_value():
        db.rollback()
        raise HTTPException(409, "new_password_unchanged")
    AuthService().reset_user_password(db, user.id, password=payload.new_password.get_secret_value())
    _audit(db, user.id, "password_changed_sessions_revoked")
    db.commit()
    _clear_cookies(response, settings)
    return {"status": "password_changed", "reauthenticate": True}


@router.post("/closure")
def close_access(payload: ClosureInput, request: Request, response: Response, db: DB, user: User, settings: Config) -> dict:
    current = _lock_current(db, user, request, settings)
    _reauthenticate(db, current, payload.current_password)
    try:
        AuthService().disable_user(db, user.id)
    except LastActiveAdminError:
        db.rollback()
        raise HTTPException(409, "last_active_admin_protected") from None
    db.execute(update(WorkspaceBridgeDevice).where(WorkspaceBridgeDevice.user_id == user.id)
               .values(status="revoked", pairing_hash=None, token_hash=None))
    db.execute(update(WorkspaceResearchJob).where(WorkspaceResearchJob.user_id == user.id,
               WorkspaceResearchJob.status.in_(["queued", "running"]))
               .values(status="cancelled", failure_reason="account_access_closed", lease_id=None, lease_until=None))
    db.execute(update(WorkspaceDataJob).where(WorkspaceDataJob.user_id == user.id,
               WorkspaceDataJob.status == "queued").values(status="cancelled", failure_reason="account_access_closed"))
    _audit(db, user.id, "account_access_closed_records_retained")
    db.commit()
    _clear_cookies(response, settings)
    return {"status": "access_closed", "data_erased": False, "reauthenticate": True}

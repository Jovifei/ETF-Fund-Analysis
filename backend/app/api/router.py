from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.schemas import (
    AdminPasswordReset,
    AdminUserCreate,
    AdminUserResponse,
    AuthStatusResponse,
    BoardFundAdd,
    DemoLoadRequest,
    HoldingImportCandidatePatch,
    HoldingImportCandidateResponse,
    HoldingImportCloudConsent,
    HoldingImportResponse,
    HoldingUpsert,
    LoginRequest,
    MarketProbeRequest,
    RegisterRequest,
    ReviewCandidateResponse,
    ReviewEnqueueRequest,
    ReviewRunner,
    ReviewTransitionRequest,
    RuntimeUpdate,
    TaskRequest,
)
from app.core.config import Settings, get_settings
from app.core.security import (
    csrf_cookie_name,
    login_throttle,
    optional_current_user,
    require_admin,
    require_enrolled_admin,
    require_private_access,
    session_cookie_name,
)
from app.db.session import SessionLocal, get_db
from app.models import AuthUser, EventLog, ReportArtifact
from app.ocr.image_validation import ImageValidationError, read_limited_bytes
from app.services.analysis_persistence_service import AnalysisStorageNotMigrated
from app.services.auth_service import (
    AuthService,
    LastActiveAdminError,
    UserNotFoundError,
)
from app.services.board_service import BoardService
from app.services.dashboard_service import DashboardService
from app.services.decision_board_service import DecisionBoardRefreshBusy, DecisionBoardService
from app.services.demo_service import DemoService
from app.services.holding_import_service import (
    HoldingImportConflict,
    HoldingImportError,
    HoldingImportNotFound,
    HoldingImportService,
    HoldingImportUnavailable,
)
from app.services.holding_service import HoldingNotFoundError, HoldingService
from app.services.market_context_service import MarketContextService
from app.services.report_service import ReportService
from app.services.review_service import CandidateNotFoundError, ReviewService
from app.services.runtime_service import RuntimeService
from app.services.signal_center_service import SignalCenterService
from app.services.signal_grade_service import SignalGradeService
from app.services.task_service import TaskBusyError, TaskExecutionError, TaskService, UnknownTaskError

router = APIRouter(prefix="/api")
private_router = APIRouter(dependencies=[Depends(require_private_access)])
_USER_SCOPED_EVENT_TYPES = frozenset({"holdings.updated", "report.generated", "portfolio.optimization.completed"})


def _review_response(candidate: Any) -> ReviewCandidateResponse:
    """Project an ORM candidate without exposing storage or runner internals."""
    return ReviewCandidateResponse(
        candidate_id=candidate.candidate_id,
        runner=candidate.runner,
        bundle_hash=candidate.bundle_hash,
        memo_hash=candidate.memo_hash,
        memo=candidate.memo_payload,
        review_status=candidate.review_status,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
        accepted_at=candidate.accepted_at,
        rejected_at=candidate.rejected_at,
        review_note=candidate.review_note,
    )


def _admin_user_response(user: AuthUser) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        status=user.status,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def _event_is_visible_to_user(event: EventLog, user_id: int | None) -> bool:
    """Expose market-wide events plus records explicitly owned by this session."""

    payload = event.payload_json if isinstance(event.payload_json, dict) else {}
    owner_id = payload.get("user_id")
    if owner_id is None:
        # A private event without an owner is malformed; fail closed instead of
        # turning a persistence mistake into a cross-account disclosure.
        return event.event_type not in _USER_SCOPED_EVENT_TYPES
    return user_id is not None and isinstance(owner_id, int) and not isinstance(owner_id, bool) and owner_id == user_id


@router.get("/health")
def health(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "provider": settings.market_provider,
        "auth_enabled": settings.auth_enabled,
    }


def _login_throttle_key(request: Request) -> str:
    client = request.client.host if request.client else "unknown"
    # Keep the limiter bounded without retaining a readable client address.
    # Per-IP keys prevent identifier rotation from evading the verifier budget.
    return hashlib.sha256(client.encode()).hexdigest()


def _set_auth_cookies(response: Response, settings: Settings, session_token: str, csrf_token: str) -> None:
    max_age = settings.auth_session_ttl_minutes * 60
    response.set_cookie(
        key=session_cookie_name(settings),
        value=session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=csrf_cookie_name(settings),
        value=csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    for name in (session_cookie_name(settings), csrf_cookie_name(settings)):
        response.delete_cookie(key=name, path="/", secure=settings.auth_cookie_secure, samesite="lax")


@router.post("/auth/login", response_model=AuthStatusResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthStatusResponse:
    failure = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录失败，请检查凭据后重试")
    if not settings.auth_enabled:
        raise failure
    key = _login_throttle_key(request)
    if login_throttle.is_limited(key):
        login_throttle.record_failure(key)
        raise failure
    try:
        user = AuthService().authenticate(db, identifier=payload.identifier, password=payload.password)
    except ValueError:
        user = None
    if user is None:
        login_throttle.record_failure(key)
        raise failure
    login_throttle.record_success(key)
    issued = AuthService().create_session(db, user, ttl=timedelta(minutes=settings.auth_session_ttl_minutes), user_agent=request.headers.get("User-Agent"), client_ip=request.client.host if request.client else None)
    db.commit()
    _set_auth_cookies(response, settings, issued.session_token, issued.csrf_token)
    return AuthStatusResponse(authenticated=True, identifier=user.username, role=user.role)


@router.post("/auth/register", response_model=AuthStatusResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthStatusResponse:
    if not settings.auth_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="认证服务未启用")
    if not settings.registration_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前未开放自主注册")

    key = _login_throttle_key(request)
    if login_throttle.is_limited(key):
        login_throttle.record_failure(key)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="尝试次数过多，请稍后再试")

    configured_invite = (settings.registration_invite_code or "").strip()
    if not configured_invite or not secrets.compare_digest(payload.invite_code.strip(), configured_invite):
        login_throttle.record_failure(key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀请码错误，无法创建账户")

    try:
        user = AuthService().create_user(
            db,
            username=payload.identifier,
            email=payload.email,
            password=payload.password,
            role="member",
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    except Exception as exc:
        from sqlalchemy.exc import IntegrityError

        if isinstance(exc, IntegrityError):
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该用户名或邮箱已被注册") from None
        db.rollback()
        raise

    login_throttle.record_success(key)
    issued = AuthService().create_session(
        db,
        user,
        ttl=timedelta(minutes=settings.auth_session_ttl_minutes),
        user_agent=request.headers.get("User-Agent"),
        client_ip=request.client.host if request.client else None,
    )
    db.commit()
    _set_auth_cookies(response, settings, issued.session_token, issued.csrf_token)
    return AuthStatusResponse(authenticated=True, identifier=user.username, role=user.role)


@router.get("/auth/me", response_model=AuthStatusResponse)
def auth_me(request: Request, db: Annotated[Session, Depends(get_db)], settings: Annotated[Settings, Depends(get_settings)]) -> AuthStatusResponse:
    if not settings.auth_enabled:
        return AuthStatusResponse(authenticated=True)
    user = AuthService().resolve_session(db, request.cookies.get(session_cookie_name(settings)))
    if user is not None:
        return AuthStatusResponse(authenticated=True, identifier=user.username, role=user.role)
    return AuthStatusResponse(authenticated=False)


@router.post("/auth/logout", response_model=AuthStatusResponse, dependencies=[Depends(require_private_access)])
def logout(request: Request, response: Response, db: Annotated[Session, Depends(get_db)], settings: Annotated[Settings, Depends(get_settings)]) -> AuthStatusResponse:
    AuthService().revoke_session(db, request.cookies.get(session_cookie_name(settings)))
    db.commit()
    _clear_auth_cookies(response, settings)
    return AuthStatusResponse(authenticated=False)


@private_router.get("/admin/users", response_model=list[AdminUserResponse], dependencies=[Depends(require_enrolled_admin)])
def list_admin_users(db: Annotated[Session, Depends(get_db)]) -> list[AdminUserResponse]:
    return [_admin_user_response(user) for user in AuthService().list_users(db)]


@private_router.post(
    "/admin/users",
    response_model=AdminUserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_enrolled_admin)],
)
def create_admin_user(payload: AdminUserCreate, db: Annotated[Session, Depends(get_db)]) -> AdminUserResponse:
    try:
        user = AuthService().create_user(
            db,
            username=payload.username,
            email=payload.email,
            password=payload.password,
            role=payload.role,
        )
        db.commit()
        return _admin_user_response(user)
    except ValueError:
        db.rollback()
        raise HTTPException(status_code=422, detail="account creation rejected") from None
    except Exception as exc:
        # Username/email uniqueness is enforced by the database.  Keep its
        # constraint details private while returning a deterministic conflict.
        from sqlalchemy.exc import IntegrityError

        if isinstance(exc, IntegrityError):
            db.rollback()
            raise HTTPException(status_code=409, detail="account already exists") from None
        db.rollback()
        raise


@private_router.post(
    "/admin/users/{user_id}/disable",
    response_model=AdminUserResponse,
    dependencies=[Depends(require_enrolled_admin)],
)
def disable_admin_user(
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> AdminUserResponse:
    try:
        user = AuthService().disable_user(db, user_id)
        db.commit()
        return _admin_user_response(user)
    except UserNotFoundError:
        db.rollback()
        raise HTTPException(status_code=404, detail="account not found") from None
    except LastActiveAdminError:
        db.rollback()
        raise HTTPException(status_code=409, detail="the last active admin cannot be disabled") from None


@private_router.post(
    "/admin/users/{user_id}/reactivate",
    response_model=AdminUserResponse,
    dependencies=[Depends(require_enrolled_admin)],
)
def reactivate_admin_user(user_id: int, db: Annotated[Session, Depends(get_db)]) -> AdminUserResponse:
    try:
        user = AuthService().reactivate_user(db, user_id)
        db.commit()
        return _admin_user_response(user)
    except UserNotFoundError:
        db.rollback()
        raise HTTPException(status_code=404, detail="account not found") from None


@private_router.post(
    "/admin/users/{user_id}/reset-password",
    response_model=AdminUserResponse,
    dependencies=[Depends(require_enrolled_admin)],
)
def reset_admin_user_password(
    user_id: int, payload: AdminPasswordReset, db: Annotated[Session, Depends(get_db)]
) -> AdminUserResponse:
    try:
        user = AuthService().reset_user_password(db, user_id, password=payload.password)
        db.commit()
        return _admin_user_response(user)
    except UserNotFoundError:
        db.rollback()
        raise HTTPException(status_code=404, detail="account not found") from None


@private_router.get("/bootstrap")
def bootstrap(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthUser | None, Depends(optional_current_user)],
) -> dict:
    return DashboardService(settings).bootstrap(
        db,
        user_id=user.id if user is not None else None,
        include_operational_details=user is None or user.role == "admin",
    )


@private_router.get("/decision-board")
def decision_board(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    horizon: int = Query(default=1),
    snapshot_id: str | None = Query(default=None, min_length=1, max_length=64),
) -> dict:
    try:
        payload = DecisionBoardService(settings).read_latest(db, horizon=horizon, snapshot_id=snapshot_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="horizon must be one of 1, 3, 5, 10") from None
    if payload is None:
        raise HTTPException(status_code=404, detail="decision-board snapshot not found")
    return payload


@private_router.get("/decision-board/{ts_code}")
def decision_board_detail(
    ts_code: str,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    horizon: int = Query(default=1),
    snapshot_id: str | None = Query(default=None, min_length=1, max_length=64),
) -> dict:
    try:
        row = DecisionBoardService(settings).read_instrument(
            db, ts_code, horizon=horizon, snapshot_id=snapshot_id
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="horizon must be one of 1, 3, 5, 10") from None
    if row is None:
        raise HTTPException(status_code=404, detail="decision-board instrument not found")
    return row


@private_router.post("/decision-board/refresh", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_admin)])
def queue_decision_board_refresh(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    try:
        result = DecisionBoardService(settings).enqueue_refresh(db)
        db.commit()
        return result
    except DecisionBoardRefreshBusy:
        db.rollback()
        raise HTTPException(status_code=409, detail="decision-board refresh already active") from None


@private_router.post("/demo/load", dependencies=[Depends(require_admin)])
def load_demo(
    settings: Annotated[Settings, Depends(get_settings)],
    _payload: Annotated[DemoLoadRequest | None, Body()] = None,
) -> dict[str, Any]:
    del settings
    return DemoService().load()


@private_router.get("/demo/bootstrap")
def demo_bootstrap() -> dict[str, Any]:
    return DemoService().bootstrap()


@private_router.post("/demo/reset", dependencies=[Depends(require_admin)])
def reset_demo() -> dict[str, Any]:
    return DemoService.reset()


@private_router.get("/instruments")
def instruments(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthUser | None, Depends(optional_current_user)],
) -> list[dict]:
    return DashboardService(settings).instrument_rows(db, user_id=user.id if user is not None else None)


@private_router.get("/market-context")
def market_context(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    return {"latest_view": MarketContextService(provider=None, settings=settings).latest_view(db)}


@private_router.get("/instruments/{ts_code}/bars")
def bars(
    ts_code: str,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = Query(default=260, ge=10, le=1500),
) -> list[dict]:
    result = DashboardService(settings).bars(db, ts_code, limit)
    if not result:
        raise HTTPException(status_code=404, detail="未找到标的或历史 K 线")
    return result


@private_router.get("/news")
def news(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = Query(default=30, ge=1, le=200),
) -> list[dict]:
    return DashboardService(settings).recent_news(db, limit)


@private_router.get("/holdings")
def holdings(db: Annotated[Session, Depends(get_db)], user: Annotated[AuthUser | None, Depends(optional_current_user)]) -> list[dict]:
    return HoldingService().list(db, user_id=user.id if user is not None else None)


@private_router.put("/holdings/{ts_code}")
def upsert_holding(
    ts_code: str,
    payload: HoldingUpsert,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[AuthUser | None, Depends(optional_current_user)],
) -> dict:
    if payload.ts_code != ts_code.upper():
        raise HTTPException(status_code=400, detail="路径代码与请求体 ts_code 不一致")
    try:
        HoldingService().upsert(
            db,
            user_id=user.id if user is not None else None,
            ts_code=payload.ts_code,
            shares=payload.shares,
            cost_price=payload.cost_price,
            target_weight=payload.target_weight,
            notes=payload.notes,
        )
        db.commit()
    except HoldingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok", "holding": HoldingService().list(db, user_id=user.id if user is not None else None)}


@private_router.delete("/holdings/{ts_code}")
def delete_holding(ts_code: str, db: Annotated[Session, Depends(get_db)], user: Annotated[AuthUser | None, Depends(optional_current_user)]) -> dict:
    try:
        deleted = HoldingService().delete(db, ts_code.upper(), user_id=user.id if user is not None else None)
        db.commit()
    except HoldingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok", "deleted": deleted}



def _holding_import_candidate_response(candidate: Any) -> HoldingImportCandidateResponse:
    return HoldingImportCandidateResponse(
        id=candidate.id,
        row_index=candidate.row_index,
        ts_code=candidate.ts_code,
        name=candidate.name,
        shares=float(candidate.shares) if candidate.shares is not None else None,
        cost_price=float(candidate.cost_price) if candidate.cost_price is not None else None,
        target_weight=candidate.target_weight,
        user_note=candidate.user_note,
        match_status=candidate.match_status,
        status=candidate.status,
        action=candidate.action,
        safe_alternatives=list(candidate.safe_alternatives_json or ()),
        field_confidence=[item.model_dump() for item in (candidate.field_confidence_json or ())],
        selected_code=candidate.selected_code,
    )


def _holding_import_response(session: Any) -> HoldingImportResponse:
    return HoldingImportResponse(
        session_id=session.session_id,
        status=session.status,
        candidate_count=session.candidate_count,
        expires_at=session.expires_at,
        confirmed_at=session.confirmed_at,
        cancelled_at=session.cancelled_at,
        cloud_consent=session.cloud_consent,
        cloud_consent_at=session.cloud_consent_at,
        ocr_mode=session.ocr_mode,
        ocr_backend=session.ocr_backend,
        ocr_model=session.ocr_model,
        ocr_version=session.ocr_version,
        candidates=[_holding_import_candidate_response(item) for item in session.candidates],
    )


def _import_http_error(exc: HoldingImportError) -> HTTPException:
    if isinstance(exc, HoldingImportNotFound):
        return HTTPException(status_code=404, detail="holding import session not found")
    if isinstance(exc, HoldingImportUnavailable):
        return HTTPException(status_code=503, detail="local OCR is unavailable")
    if isinstance(exc, HoldingImportConflict):
        code_status = {
            "expired": 409,
            "cloud_disabled": 409,
            "confirming": 409,
            "storage_path": 400,
            "invalid_code": 422,
            "unknown_code": 422,
            "invalid_numeric": 422,
            "invalid_text": 422,
            "invalid_action": 422,
        }
        return HTTPException(status_code=code_status.get(exc.code, 409), detail="holding import state cannot change")
    return HTTPException(status_code=422, detail="holding import request rejected")


@private_router.post(
    "/holding-imports",
    response_model=HoldingImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_holding_import(
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthUser | None, Depends(optional_current_user)],
) -> HoldingImportResponse:
    try:
        payload = read_limited_bytes(file.file, max_bytes=settings.ocr_max_bytes)
        session = HoldingImportService(settings).import_bytes(db, payload, file.content_type, user_id=user.id if user is not None else None)
        return _holding_import_response(session)
    except ImageValidationError as exc:
        if exc.code == "too_large":
            raise HTTPException(status_code=413, detail="image exceeds the configured size limit") from None
        if exc.code in {"mime_mismatch", "unsupported_format"}:
            raise HTTPException(status_code=415, detail="unsupported image type") from None
        raise HTTPException(status_code=422, detail="image validation failed") from None
    except HoldingImportError as exc:
        raise _import_http_error(exc) from None
    except Exception:
        raise HTTPException(status_code=503, detail="holding import unavailable") from None
    finally:
        await file.close()


@private_router.get("/holding-imports/{session_id}", response_model=HoldingImportResponse)
def get_holding_import(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthUser | None, Depends(optional_current_user)],
) -> HoldingImportResponse:
    try:
        return _holding_import_response(HoldingImportService(settings).get(db, session_id, user_id=user.id if user is not None else None))
    except HoldingImportError as exc:
        raise _import_http_error(exc) from None


@private_router.patch(
    "/holding-imports/{session_id}/candidates/{candidate_id}",
    response_model=HoldingImportCandidateResponse,
)
def edit_holding_import_candidate(
    session_id: str,
    candidate_id: int,
    payload: HoldingImportCandidatePatch,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthUser | None, Depends(optional_current_user)],
) -> HoldingImportCandidateResponse:
    try:
        candidate = HoldingImportService(settings).edit_candidate(db, session_id, candidate_id, payload, user_id=user.id if user is not None else None)
        return _holding_import_candidate_response(candidate)
    except HoldingImportError as exc:
        raise _import_http_error(exc) from None


@private_router.post("/holding-imports/{session_id}/confirm")
def confirm_holding_import(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthUser | None, Depends(optional_current_user)],
) -> dict[str, Any]:
    service = HoldingImportService(settings)
    try:
        result = service.confirm(db, session_id, user_id=user.id if user is not None else None)
        return result
    except HoldingImportError as exc:
        raise _import_http_error(exc) from None
    except Exception:
        raise HTTPException(status_code=409, detail="holding import could not be confirmed") from None


@private_router.post("/holding-imports/{session_id}/cancel")
def cancel_holding_import(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthUser | None, Depends(optional_current_user)],
) -> dict[str, Any]:
    service = HoldingImportService(settings)
    try:
        result = service.cancel(db, session_id, user_id=user.id if user is not None else None)
        return result
    except HoldingImportError as exc:
        raise _import_http_error(exc) from None


@private_router.post("/holding-imports/{session_id}/cloud-consent", response_model=HoldingImportResponse)
def set_holding_import_cloud_consent(
    session_id: str,
    payload: HoldingImportCloudConsent,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthUser | None, Depends(optional_current_user)],
) -> HoldingImportResponse:
    try:
        session = HoldingImportService(settings).set_cloud_consent(db, session_id, payload.consent, user_id=user.id if user is not None else None)
        return _holding_import_response(session)
    except HoldingImportError as exc:
        raise _import_http_error(exc) from None


@private_router.get("/signals/center")
def signal_center(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthUser | None, Depends(optional_current_user)],
    coefficient: float | None = Query(default=None, ge=0.5, le=1.5),
    days: int = Query(default=60, ge=5, le=250),
) -> dict:
    stored = RuntimeService(settings).get_all(db).get("signal_center_coefficient")
    effective = coefficient
    if effective is None and stored is not None:
        effective = float(stored)
    payload = SignalCenterService(settings).build(db, coefficient=effective, days=days, user_id=user.id if user is not None else None)
    db.commit()  # 持久化 ensure_defaults 写入的默认设置
    return payload


@private_router.get("/signals/grade")
def signal_grade(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    return SignalGradeService(settings).build(db)


@private_router.get("/signals/boards")
def signal_boards(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    return BoardService(settings).build(db)


@private_router.post("/signals/boards/{board_id}/funds", dependencies=[Depends(require_admin)])
def add_board_fund(
    board_id: str,
    payload: BoardFundAdd,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    try:
        result = BoardService(settings).add_fund(db, board_id, payload.ts_code, payload.name)
        db.commit()
        return result
    except KeyError:
        db.rollback()
        raise HTTPException(status_code=404, detail="board not found") from None
    except ValueError:
        db.rollback()
        raise HTTPException(status_code=422, detail="invalid fund code") from None


@private_router.get("/settings", dependencies=[Depends(require_admin)])
def runtime_settings(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    service = RuntimeService(settings)
    result = service.get_all(db)
    db.commit()
    return result


@private_router.put("/settings", dependencies=[Depends(require_admin)])
def update_runtime_settings(
    payload: RuntimeUpdate,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    try:
        result = RuntimeService(settings).update(db, payload.compact())
    except ValueError:
        db.rollback()
        raise HTTPException(status_code=422, detail="settings update rejected") from None
    db.commit()
    return result


@private_router.post("/settings/market-probe", dependencies=[Depends(require_admin)])
def probe_market_settings(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    payload: MarketProbeRequest | None = None,
) -> dict:
    token = payload.tushare_token if payload is not None else None
    tier = payload.market_data_tier if payload is not None else None
    try:
        result = RuntimeService(settings).probe_market(db, token_override=token, tier_override=tier)
    except ValueError:
        db.rollback()
        raise HTTPException(status_code=422, detail="market probe rejected") from None
    db.commit()
    return result


@private_router.get("/tasks", dependencies=[Depends(require_admin)])
def task_history(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = Query(default=30, ge=1, le=200),
) -> list[dict]:
    return DashboardService(settings).task_runs(db, limit)


@private_router.post(
    "/analysis/reviews",
    response_model=ReviewCandidateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def enqueue_analysis_review(
    payload: ReviewEnqueueRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ReviewCandidateResponse:
    try:
        candidate = ReviewService.enqueue_from_hash(
            db,
            runner=payload.runner,
            bundle_hash=payload.bundle_hash,
            memo=payload.memo,
            memo_hash=payload.memo_hash,
        )
        db.commit()
        return _review_response(candidate)
    except AnalysisStorageNotMigrated:
        db.rollback()
        raise HTTPException(status_code=503, detail="review storage unavailable") from None
    except ValueError:
        db.rollback()
        raise HTTPException(status_code=422, detail="review request rejected") from None


@private_router.get("/analysis/reviews", response_model=list[ReviewCandidateResponse], dependencies=[Depends(require_admin)])
def list_analysis_reviews(
    db: Annotated[Session, Depends(get_db)],
    review_status: Annotated[Literal["pending", "accepted", "rejected"] | None, Query()] = None,
    runner: Annotated[ReviewRunner | None, Query()] = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[ReviewCandidateResponse]:
    try:
        return [_review_response(candidate) for candidate in ReviewService.list(
            db, review_status=review_status, runner=runner, limit=limit
        )]
    except AnalysisStorageNotMigrated:
        raise HTTPException(status_code=503, detail="review storage unavailable") from None
    except ValueError:
        raise HTTPException(status_code=422, detail="review query rejected") from None


@private_router.get("/analysis/reviews/{candidate_id}", response_model=ReviewCandidateResponse, dependencies=[Depends(require_admin)])
def get_analysis_review(
    candidate_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ReviewCandidateResponse:
    try:
        return _review_response(ReviewService.get(db, candidate_id))
    except CandidateNotFoundError:
        raise HTTPException(status_code=404, detail="review candidate not found") from None
    except AnalysisStorageNotMigrated:
        raise HTTPException(status_code=503, detail="review storage unavailable") from None


@private_router.post(
    "/analysis/reviews/{candidate_id}/accept",
    response_model=ReviewCandidateResponse,
    dependencies=[Depends(require_admin)],
)
def accept_analysis_review(
    candidate_id: str,
    payload: ReviewTransitionRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ReviewCandidateResponse:
    try:
        candidate = ReviewService.accept(db, candidate_id, note=payload.note)
        db.commit()
        return _review_response(candidate)
    except CandidateNotFoundError:
        db.rollback()
        raise HTTPException(status_code=404, detail="review candidate not found") from None
    except AnalysisStorageNotMigrated:
        db.rollback()
        raise HTTPException(status_code=503, detail="review storage unavailable") from None
    except ValueError:
        db.rollback()
        raise HTTPException(status_code=409, detail="review candidate cannot change state") from None


@private_router.post(
    "/analysis/reviews/{candidate_id}/reject",
    response_model=ReviewCandidateResponse,
    dependencies=[Depends(require_admin)],
)
def reject_analysis_review(
    candidate_id: str,
    payload: ReviewTransitionRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ReviewCandidateResponse:
    try:
        candidate = ReviewService.reject(db, candidate_id, note=payload.note)
        db.commit()
        return _review_response(candidate)
    except CandidateNotFoundError:
        db.rollback()
        raise HTTPException(status_code=404, detail="review candidate not found") from None
    except AnalysisStorageNotMigrated:
        db.rollback()
        raise HTTPException(status_code=503, detail="review storage unavailable") from None
    except ValueError:
        db.rollback()
        raise HTTPException(status_code=409, detail="review candidate cannot change state") from None


@private_router.post("/tasks/{task_name}", dependencies=[Depends(require_admin)])
def run_task(
    task_name: str,
    payload: TaskRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthUser | None, Depends(require_admin)],
) -> dict:
    service = TaskService(settings)
    try:
        arguments = payload.compact()
        if task_name == "optimize_portfolio" and user is not None:
            arguments["user_id"] = user.id
        result = service.run(db, task_name, **arguments)
        db.commit()
        return result
    except UnknownTaskError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TaskBusyError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TaskExecutionError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={"run_id": exc.run_id, "failure_class": exc.failure_class},
        ) from None
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="task execution failed") from None
    finally:
        service.close()


@private_router.post("/reports")
def generate_report(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthUser | None, Depends(optional_current_user)],
) -> dict:
    result = ReportService(settings).generate(db, user_id=user.id if user is not None else None)
    db.commit()
    return result


@private_router.get("/reports")
def list_reports(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthUser | None, Depends(optional_current_user)],
    limit: int = Query(default=30, ge=1, le=200),
) -> list[dict]:
    del request
    owner_filter = ReportArtifact.user_id == user.id if user is not None else ReportArtifact.user_id.is_(None)
    rows = db.scalars(select(ReportArtifact).where(owner_filter).order_by(ReportArtifact.created_at.desc())).all()
    reports_root = settings.reports_dir.resolve()
    reports: list[dict] = []
    for row in rows:
        candidate = Path(row.file_path)
        safe_name = candidate.name
        allowed = safe_name.endswith(".html") or safe_name.endswith(".json")
        if not (safe_name == candidate.name and allowed and candidate.is_file()):
            continue
        try:
            candidate.resolve(strict=True).relative_to(reports_root)
        except (OSError, ValueError):
            continue
        reports.append(
            {
                "id": row.id,
                "type": row.report_type,
                "as_of_time": row.as_of_time,
                "filename": safe_name,
                "content_hash": row.content_hash,
                "metadata": row.metadata_json,
                "url": f"/api/reports/{safe_name}",
            }
        )
        if len(reports) >= limit:
            break
    return reports


@private_router.get("/reports/{filename}")
def download_report(
    filename: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthUser | None, Depends(optional_current_user)],
) -> FileResponse:
    safe_name = Path(filename).name
    allowed = safe_name.endswith(".html") or safe_name.endswith(".json")
    if safe_name != filename or not allowed:
        raise HTTPException(status_code=400, detail="非法报告文件名")
    del request
    owner_filter = ReportArtifact.user_id == user.id if user is not None else ReportArtifact.user_id.is_(None)
    reports_root = settings.reports_dir.resolve()
    path: Path | None = None
    for artifact in db.scalars(select(ReportArtifact).where(owner_filter)):
        candidate = Path(artifact.file_path)
        if candidate.name != safe_name or not candidate.is_file():
            continue
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(reports_root)
        except (OSError, ValueError):
            continue
        path = resolved
        break
    if path is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    media_type = "text/html; charset=utf-8" if safe_name.endswith(".html") else "application/json"
    return FileResponse(path, media_type=media_type, filename=safe_name)


async def _event_stream(
    *,
    auth_enabled: bool,
    session_token: str | None,
    user_id: int | None,
    after_id: int,
    poll_interval_seconds: float = 2,
):
    """Yield visible events only while the original DB session remains valid."""

    cursor = after_id
    yield "retry: 3000\n\n"
    while True:
        with SessionLocal() as db:
            if auth_enabled and not AuthService().session_is_current_for_user(db, session_token, user_id):
                return
            rows = db.scalars(
                select(EventLog).where(EventLog.id > cursor).order_by(EventLog.id).limit(100)
            ).all()
        for row in rows:
            cursor = row.id
            if not _event_is_visible_to_user(row, user_id):
                continue
            # Do not retain a DB transaction across an await/yield.  A fresh
            # read also closes an established stream immediately after logout,
            # disable, password reset, expiry, or a user/session mismatch.
            with SessionLocal() as db:
                if auth_enabled and not AuthService().session_is_current_for_user(db, session_token, user_id):
                    return
            payload = json.dumps(row.payload_json if isinstance(row.payload_json, dict) else {}, ensure_ascii=False, default=str)
            yield f"id: {row.id}\nevent: {row.event_type}\ndata: {payload}\n\n"
        yield ": keepalive\n\n"
        await asyncio.sleep(poll_interval_seconds)


@private_router.get("/events")
async def events(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthUser | None, Depends(optional_current_user)],
    after_id: int = Query(default=0, ge=0),
) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(
            auth_enabled=settings.auth_enabled,
            session_token=request.cookies.get(session_cookie_name(settings)) if settings.auth_enabled else None,
            user_id=user.id if user is not None else None,
            after_id=after_id,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


router.include_router(private_router)

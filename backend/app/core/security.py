from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import AuthUser
from app.services.auth_service import AuthService

SESSION_COOKIE_NAME = "__Host-fund-session"
CSRF_COOKIE_NAME = "__Host-fund-csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
password_hasher = PasswordHash.recommended()
# A non-secret fixed input whose only purpose is equal password-verification
# work for unknown identifiers. It is never sent to clients or logged.
_DUMMY_PASSWORD_HASH = password_hasher.hash("not-a-real-login-password")


def session_cookie_name(settings: Settings) -> str:
    return SESSION_COOKIE_NAME if settings.auth_cookie_secure else "fund-session"


def csrf_cookie_name(settings: Settings) -> str:
    return CSRF_COOKIE_NAME if settings.auth_cookie_secure else "fund-csrf"


def hash_password(password: str) -> str:
    """Hash a password with pwdlib's recommended Argon2id parameters."""

    return password_hasher.hash(password)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class AuthSessionManager:
    """Issue and verify compact HMAC-signed, server-only session credentials."""

    def __init__(self, settings: Settings):
        self._secret = settings.auth_session_secret.get_secret_value().encode("utf-8")
        self._ttl_seconds = settings.auth_session_ttl_minutes * 60

    def issue(self, identifier: str, *, now: float | None = None) -> str:
        issued_at = time.time() if now is None else now
        payload = json.dumps(
            {"v": 1, "sub": identifier, "exp": int(issued_at + self._ttl_seconds), "nonce": secrets.token_urlsafe(24)},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        encoded = _b64encode(payload)
        signature = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        return f"{encoded}.{_b64encode(signature)}"

    def verify(self, token: str | None, *, now: float | None = None) -> str | None:
        if not token or not self._secret:
            return None
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected_signature = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
            if not hmac.compare_digest(_b64encode(expected_signature), supplied_signature):
                return None
            payload = json.loads(_b64decode(encoded))
            if not isinstance(payload, dict):
                return None
            if payload.get("v") != 1 or not isinstance(payload.get("sub"), str) or not isinstance(payload.get("exp"), int):
                return None
            if payload["exp"] <= (time.time() if now is None else now):
                return None
            return payload["sub"]
        except (ValueError, TypeError, OverflowError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError):
            return None


@dataclass
class LoginThrottle:
    """Small process-local failure limiter; no identifiers are persisted."""

    max_entries: int = 1024
    max_failures: int = 5
    window_seconds: int = 60
    _attempts: dict[str, deque[float]] = field(default_factory=dict)

    def is_limited(self, key: str, *, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        attempts = self._attempts.get(key)
        if attempts is None:
            return False
        self._discard_expired(attempts, current)
        return len(attempts) >= self.max_failures

    def record_failure(self, key: str, *, now: float | None = None) -> None:
        current = time.time() if now is None else now
        if key not in self._attempts and len(self._attempts) >= self.max_entries:
            self._attempts.pop(next(iter(self._attempts)))
        attempts = self._attempts.setdefault(key, deque())
        self._discard_expired(attempts, current)
        attempts.append(current)

    def record_success(self, key: str) -> None:
        self._attempts.pop(key, None)

    def reset_for_tests(self) -> None:
        self._attempts.clear()

    def _discard_expired(self, attempts: deque[float], current: float) -> None:
        while attempts and current - attempts[0] >= self.window_seconds:
            attempts.popleft()


login_throttle = LoginThrottle()


def password_matches(settings: Settings, identifier: str, password: str) -> bool:
    """Verify account credentials while preserving equal work for unknown users."""

    normalized = identifier.strip().casefold()
    expected_hash = _DUMMY_PASSWORD_HASH
    matched_identifier = settings.password_auth_configured and normalized in {
        settings.auth_username,
        settings.auth_email,
    }
    if matched_identifier:
        expected_hash = settings.auth_password_hash.get_secret_value()
    try:
        verified = password_hasher.verify(password, expected_hash)
    except Exception:
        verified = False
    return bool(matched_identifier and verified)


def _extract_bearer(value: str | None) -> str | None:
    if not value:
        return None
    prefix = "Bearer "
    if value.startswith(prefix):
        return value[len(prefix) :].strip()
    return None


async def require_private_access(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
    csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER_NAME)] = None,
) -> None:
    if not settings.auth_enabled:
        request.state.auth_user = None
        request.state.auth_via_session = False
        return
    supplied = _extract_bearer(authorization)
    if supplied and settings.legacy_bearer_configured and hmac.compare_digest(supplied, settings.private_access_token):
        if request.method in _UNSAFE_METHODS:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="database user session required")
        request.state.auth_via_session = False
        request.state.auth_user = None
        return
    session_token = request.cookies.get(session_cookie_name(settings))
    user = AuthService().resolve_session(db, session_token)
    if user is not None:
        if request.method in _UNSAFE_METHODS:
            csrf_cookie = request.cookies.get(csrf_cookie_name(settings), "")
            if not csrf_token or not csrf_cookie or not hmac.compare_digest(csrf_token, csrf_cookie) or not AuthService().verify_csrf(db, session_token, csrf_token):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF 校验失败")
        request.state.auth_via_session = True
        request.state.auth_identifier = user.username
        request.state.auth_user = user
        # Auth resolution and CSRF verification are read-only, but SQLAlchemy
        # begins a transaction for them.  Some route services deliberately
        # require a clean caller session so they can own their short mutation
        # transaction.  Preserve the already-loaded identity without leaving
        # that read transaction open for the route.
        db.expunge(user)
        db.rollback()
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="缺少或无效的访问凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_current_user(request: Request) -> AuthUser:
    """Only a resolved database session can access portfolio-owned records."""
    user = getattr(request.state, "auth_user", None)
    if not isinstance(user, AuthUser):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="database user session required")
    return user


def require_admin(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> AuthUser | None:
    """Require an admin session when auth is enabled; preserve offline single-user mode."""

    if not settings.auth_enabled:
        return None

    user = require_current_user(request)
    if user.status != "active" or user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="administrator access required")
    return user


def require_enrolled_admin(request: Request) -> AuthUser:
    """Lifecycle controls are never available while account auth is disabled."""

    user = require_current_user(request)
    if user.status != "active" or user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="administrator access required")
    return user


def optional_current_user(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> AuthUser | None:
    if not settings.auth_enabled:
        return None
    return require_current_user(request)

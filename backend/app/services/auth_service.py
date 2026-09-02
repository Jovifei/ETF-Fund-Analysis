from __future__ import annotations

import hashlib
import secrets
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from pwdlib import PasswordHash
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.models import AuthBootstrapGuard, AuthSession, AuthUser
from app.models.entities import validate_argon2id_password_hash

_password_hasher = PasswordHash.recommended()
_dummy_password_hash = _password_hasher.hash("not-a-real-login-password")
_DEFAULT_SESSION_TTL = timedelta(hours=8)


class BootstrapAdminExistsError(RuntimeError):
    pass


class BootstrapAdminBusyError(BootstrapAdminExistsError):
    """A concurrent bootstrap transaction owns the database guard; retry safely."""


class UserLifecycleError(RuntimeError):
    """A closed-enrollment account lifecycle request cannot be applied."""


class UserNotFoundError(UserLifecycleError):
    pass


class LastActiveAdminError(UserLifecycleError):
    pass


@dataclass(frozen=True, repr=False)
class IssuedAuthSession:
    session_id: int
    expires_at: datetime
    session_token: str = field(repr=False)
    csrf_token: str = field(repr=False)


def normalize_identifier(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    if not normalized:
        raise ValueError("identifier must not be empty")
    return normalized


def _hash_opaque(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AuthService:
    """Database-backed password and session primitives for closed enrollment."""

    def hash_password(self, password: str) -> str:
        if not isinstance(password, str) or not password:
            raise ValueError("password must not be empty")
        return validate_argon2id_password_hash(_password_hasher.hash(password))

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            return bool(_password_hasher.verify(password, validate_argon2id_password_hash(password_hash)))
        except Exception:
            return False

    def create_user(
        self,
        db: Session,
        *,
        username: str,
        password: str,
        email: str | None = None,
        role: str = "member",
    ) -> AuthUser:
        if role not in {"admin", "member"}:
            raise ValueError("role must be admin or member")
        user = AuthUser(
            username=normalize_identifier(username),
            email=normalize_identifier(email) if email else None,
            password_hash=self.hash_password(password),
            role=role,
            status="active",
        )
        db.add(user)
        db.flush()
        return user

    def list_users(self, db: Session) -> list[AuthUser]:
        return list(db.scalars(select(AuthUser).order_by(AuthUser.username)))

    def disable_user(self, db: Session, user_id: int) -> AuthUser:
        # The active-admin count and status transition must share the same
        # database serialization boundary.  PostgreSQL locks this singleton
        # row; SQLite takes its write lock through _acquire_bootstrap_guard.
        self._acquire_bootstrap_guard(db)
        user = self._get_user(db, user_id)
        if user.status == "disabled":
            return user
        if user.role == "admin":
            active_admins = int(
                db.scalar(
                    select(func.count()).select_from(AuthUser).where(
                        AuthUser.role == "admin", AuthUser.status == "active"
                    )
                )
                or 0
            )
            if active_admins <= 1:
                raise LastActiveAdminError("the last active admin cannot be disabled")
        user.status = "disabled"
        self.revoke_user_sessions(db, user.id)
        db.flush()
        return user

    def reactivate_user(self, db: Session, user_id: int) -> AuthUser:
        user = self._get_user(db, user_id)
        user.status = "active"
        # Disabled sessions deliberately remain revoked.  Re-activation requires
        # a fresh password login, preventing an old browser from coming alive.
        db.flush()
        return user

    def reset_user_password(self, db: Session, user_id: int, *, password: str) -> AuthUser:
        user = self._get_user(db, user_id)
        user.password_hash = self.hash_password(password)
        self.revoke_user_sessions(db, user.id)
        db.flush()
        return user

    @staticmethod
    def _get_user(db: Session, user_id: int) -> AuthUser:
        user = db.get(AuthUser, user_id)
        if user is None:
            raise UserNotFoundError("account not found")
        return user

    def bootstrap_first_admin(
        self, db: Session, *, username: str, password: str, email: str | None = None
    ) -> AuthUser:
        try:
            self._acquire_bootstrap_guard(db)
            if db.scalar(select(AuthUser.id).limit(1)) is not None:
                raise BootstrapAdminExistsError("an account already exists")
            return self.create_user(db, username=username, password=password, email=email, role="admin")
        except OperationalError as exc:
            db.rollback()
            raise BootstrapAdminBusyError("bootstrap transaction could not acquire the database guard") from exc

    def _acquire_bootstrap_guard(self, db: Session) -> AuthBootstrapGuard:
        """Lock the singleton row before any first-account existence check."""

        guard = db.scalar(select(AuthBootstrapGuard).where(AuthBootstrapGuard.id == 1).with_for_update())
        if guard is None:
            try:
                with db.begin_nested():
                    db.add(AuthBootstrapGuard(id=1))
                    db.flush()
            except IntegrityError:
                # A concurrent initializer won. Re-read it under the same DB boundary.
                pass
            guard = db.scalar(select(AuthBootstrapGuard).where(AuthBootstrapGuard.id == 1).with_for_update())
        if guard is None:
            raise BootstrapAdminBusyError("bootstrap guard is unavailable")
        if db.get_bind().dialect.name == "sqlite":
            # SQLite ignores FOR UPDATE; this write acquires the database write lock
            # before the user existence check and serializes competing bootstraps.
            db.execute(
                update(AuthBootstrapGuard)
                .where(AuthBootstrapGuard.id == 1)
                .values(updated_at=func.now())
            )
        return guard

    def authenticate(self, db: Session, *, identifier: str, password: str, now: datetime | None = None) -> AuthUser | None:
        normalized = normalize_identifier(identifier)
        user = db.scalar(
            select(AuthUser).where(or_(AuthUser.username == normalized, AuthUser.email == normalized))
        )
        expected_hash = user.password_hash if user is not None else _dummy_password_hash
        verified = self.verify_password(password, expected_hash)
        if user is None or user.status != "active" or not verified:
            return None
        user.last_login_at = _utc_now(now)
        return user

    def create_session(
        self,
        db: Session,
        user: AuthUser,
        *,
        now: datetime | None = None,
        ttl: timedelta = _DEFAULT_SESSION_TTL,
        user_agent: str | None = None,
        client_ip: str | None = None,
    ) -> IssuedAuthSession:
        if user.id is None or user.status != "active":
            raise ValueError("an active persisted user is required")
        created_at = _utc_now(now)
        if ttl <= timedelta(0):
            raise ValueError("session ttl must be positive")
        session_token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(32)
        session = AuthSession(
            session_hash=_hash_opaque(session_token),
            csrf_hash=_hash_opaque(csrf_token),
            user_id=user.id,
            created_at=created_at,
            expires_at=created_at + ttl,
            user_agent_hash=_hash_optional_metadata(user_agent),
            ip_hash=_hash_optional_metadata(client_ip),
        )
        db.add(session)
        db.flush()
        return IssuedAuthSession(
            session_id=session.id,
            expires_at=session.expires_at,
            session_token=session_token,
            csrf_token=csrf_token,
        )

    def resolve_session(
        self, db: Session, session_token: str | None, *, now: datetime | None = None
    ) -> AuthUser | None:
        if not session_token:
            return None
        session = db.scalar(select(AuthSession).where(AuthSession.session_hash == _hash_opaque(session_token)))
        if session is None or session.revoked_at is not None or _as_utc(session.expires_at) <= _utc_now(now):
            return None
        if session.user.status != "active":
            return None
        return session.user

    def session_is_current_for_user(
        self, db: Session, session_token: str | None, user_id: int | None, *, now: datetime | None = None
    ) -> bool:
        """Revalidate an opaque session against its original active user."""

        if not session_token or user_id is None:
            return False
        return bool(
            db.scalar(
                select(AuthSession.id)
                .join(AuthUser, AuthSession.user_id == AuthUser.id)
                .where(
                    AuthSession.session_hash == _hash_opaque(session_token),
                    AuthSession.user_id == user_id,
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > _utc_now(now),
                    AuthUser.status == "active",
                )
            )
        )

    def verify_csrf(self, db: Session, session_token: str | None, csrf_token: str | None) -> bool:
        if not session_token or not csrf_token:
            return False
        session = db.scalar(select(AuthSession).where(AuthSession.session_hash == _hash_opaque(session_token)))
        return bool(
            session is not None
            and session.revoked_at is None
            and _as_utc(session.expires_at) > _utc_now()
            and secrets.compare_digest(session.csrf_hash, _hash_opaque(csrf_token))
        )

    def revoke_session(self, db: Session, session_token: str | None, *, now: datetime | None = None) -> bool:
        if not session_token:
            return False
        session = db.scalar(select(AuthSession).where(AuthSession.session_hash == _hash_opaque(session_token)))
        if session is None or session.revoked_at is not None:
            return False
        session.revoked_at = _utc_now(now)
        return True

    def revoke_user_sessions(self, db: Session, user_id: int, *, now: datetime | None = None) -> int:
        result = db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=_utc_now(now))
        )
        return int(result.rowcount or 0)


def _utc_now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    return current if current.tzinfo is not None else current.replace(tzinfo=UTC)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _hash_optional_metadata(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if len(normalized) > 512:
        raise ValueError("session metadata exceeds its bound")
    return _hash_opaque(normalized)

"""Opt-in, standalone historical archive API. Not mounted by app.main.

Deployment, storage provisioning and credential issuance are separate approvals.
The upload signature proves the present submitter, never a historical timestamp.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from app.workspace.historical_archive import (
    HEX,
    MAX_EVIDENCE_BYTES,
    ArchivePolicy,
    ArchiveStore,
    strict_json,
)

BODY_READ_TIMEOUT_SECONDS = 10
PREFIX = "/api/history-archive"
DOMAIN = b"ETF-HISTORICAL-ARCHIVE-REQUEST-V1\x00ARCHIVE_ONLY\x00"
KEY = re.compile(r"[A-Za-z0-9_-]{1,32}")
NONCE = re.compile(r"[a-f0-9]{32}")


@dataclass(frozen=True)
class ArchiveCredential:
    key_id: str
    secret: str = field(repr=False)
    scopes: frozenset[str] = frozenset()


def _message(body: bytes, *, key_id: str, method: str, path: str, stamp: str, nonce: str) -> bytes:
    allowed = (method == "POST" and path in {PREFIX + "/objects", PREFIX + "/gaps"}) or (
        method == "GET" and re.fullmatch(re.escape(PREFIX) + r"/(receipts|objects)/[a-f0-9]{64}", path)
    )
    if not allowed:
        raise ValueError("unsigned archive path")
    return (DOMAIN + method.encode("ascii") + b"\x00" + path.encode("ascii") + b"\x00"
            + key_id.encode("ascii") + b"\x00" + stamp.encode("ascii") + b"\x00"
            + nonce.encode("ascii") + b"\x00" + hashlib.sha256(body).digest())


def _credential_valid(value: ArchiveCredential) -> bool:
    return (isinstance(value.key_id, str) and KEY.fullmatch(value.key_id) is not None
            and isinstance(value.secret, str) and len(value.secret) >= 32
            and bool(value.scopes) and value.scopes <= {"archive:submit", "archive:read"})


def signed_archive_headers(body: bytes, credential: ArchiveCredential, *, method: str, path: str,
                           now: datetime | None = None, nonce: str | None = None) -> dict[str, str]:
    now = now or datetime.now(UTC)
    nonce = nonce or secrets.token_hex(16)
    if not _credential_valid(credential) or now.tzinfo is None or not NONCE.fullmatch(nonce):
        raise ValueError("invalid archive signing credential")
    stamp = now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    message = _message(body, key_id=credential.key_id, method=method, path=path, stamp=stamp, nonce=nonce)
    signature = hmac.new(credential.secret.encode(), message, hashlib.sha256).hexdigest()
    return {"X-Archive-Key-Id": credential.key_id, "X-Archive-Timestamp": stamp,
            "X-Archive-Nonce": nonce, "X-Archive-Signature": signature}


def create_archive_app(*, enabled: bool = False, policy: ArchivePolicy | None = None,
                       credentials: tuple[ArchiveCredential, ...] = (),
                       clock: Callable[[], datetime] | None = None) -> FastAPI:
    """No automatic env lookup, default credentials, mounts or startup migrations."""
    app = FastAPI(title="Historical archive (review candidate)", docs_url=None,
                  redoc_url=None, openapi_url=None)
    if enabled is not True:
        return app
    if (policy is None or not credentials or any(not _credential_valid(key) for key in credentials)
            or len({key.key_id for key in credentials}) != len(credentials)):
        raise ValueError("explicit archive policy and credentials required")
    keys = {key.key_id: key for key in credentials}
    store = ArchiveStore(policy)
    clock = clock or (lambda: datetime.now(UTC))
    read_slots = threading.BoundedSemaphore(1)
    write_slots = threading.BoundedSemaphore(1)
    request_limit = 4 * ((policy.max_payload_bytes + 2) // 3) + MAX_EVIDENCE_BYTES + 2048

    @app.middleware("http")
    async def bounds(request: Request, call_next):
        slots = read_slots if request.method == "GET" else write_slots
        if not slots.acquire(blocking=False):
            return JSONResponse({"detail": "archive busy"}, status_code=503, headers={"Cache-Control": "no-store"})
        try:
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
        finally:
            slots.release()

    def failure(exc: Exception) -> HTTPException:
        # Never return supplied data, credentials, filesystem paths or raw SQL errors.
        if isinstance(exc, (sqlite3.Error, OSError)):
            return HTTPException(503, "archive storage unavailable; query receipt before retry")
        text = str(exc)
        if "capacity" in text:
            return HTTPException(503, "archive capacity unavailable")
        if "replay" in text or "evidence_conflict" in text:
            return HTTPException(409, "archive replay or evidence conflict")
        if "payload size" in text:
            return HTTPException(413, "archive payload too large")
        if "integrity failure" in text:
            return HTTPException(503, "archive integrity failure")
        return HTTPException(400, "invalid archive request")

    async def read_and_authorize(request: Request, scope: str):
        if request.url.query or request.headers.get("content-encoding", "identity") != "identity":
            raise HTTPException(400, "unsupported archive request encoding or query")
        key_id = request.headers.get("X-Archive-Key-Id", "")
        key = keys.get(key_id)
        stamp = request.headers.get("X-Archive-Timestamp", "")
        nonce = request.headers.get("X-Archive-Nonce", "")
        signature = request.headers.get("X-Archive-Signature", "")
        if key is None or not NONCE.fullmatch(nonce) or not HEX.fullmatch(signature):
            raise HTTPException(401, "archive authentication rejected")
        try:
            created = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            now = clock()
            if now.tzinfo is None or abs((now - created).total_seconds()) > 120:
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(401, "archive authentication rejected") from None
        body = bytearray()
        try:
            async with asyncio.timeout(BODY_READ_TIMEOUT_SECONDS):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > request_limit:
                        raise HTTPException(413, "archive request too large")
                    body.extend(chunk)
        except TimeoutError:
            raise HTTPException(408, "archive request read timeout") from None
        # A slow body must not retain an expired signature or backdate a receipt.
        now = clock()
        if now.tzinfo is None or abs((now - created).total_seconds()) > 120:
            raise HTTPException(401, "archive authentication rejected")
        raw = bytes(body)
        if request.method == "GET" and raw:
            raise HTTPException(400, "archive GET body rejected")
        try:
            message = _message(raw, key_id=key_id, method=request.method, path=request.url.path, stamp=stamp, nonce=nonce)
        except ValueError:
            raise HTTPException(401, "archive authentication rejected") from None
        expected = hmac.new(key.secret.encode(), message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(401, "archive authentication rejected")
        if scope not in key.scopes:
            raise HTTPException(403, "archive scope required")
        if request.method == "POST":
            try:
                await run_in_threadpool(store.reserve_nonce, key_id, nonce, expires=created.timestamp() + 241, now=now)
            except (ValueError, sqlite3.Error, OSError) as exc:
                raise failure(exc) from None
        # GET has no side effects and intentionally allows read replays within the
        # signed 120-second window. Receipt recovery must work when writes are full.
        return raw, key_id, now

    @app.post(PREFIX + "/objects")
    async def ingest(request: Request):
        body, key_id, now = await read_and_authorize(request, "archive:submit")
        try:
            envelope = strict_json(body)
            if (not isinstance(envelope, dict) or set(envelope) != {
                "contract", "original_sha256", "original_base64", "evidence"
            } or envelope["contract"] != "historical-archive-submit-v1"
                    or not isinstance(envelope["original_base64"], str)):
                raise ValueError("invalid envelope")
            raw = base64.b64decode(envelope["original_base64"], validate=True)
            receipt = await run_in_threadpool(store.ingest, raw, envelope["evidence"],
                                             original_sha256=envelope["original_sha256"], submitter_id=key_id, now=now)
        except (ValueError, TypeError, RecursionError, binascii.Error, sqlite3.Error, OSError) as exc:
            raise failure(exc) from None
        status = {"ARCHIVED": 200, "QUARANTINED": 202, "REJECTED": 422}[receipt["status"]]
        return JSONResponse(receipt, status_code=status)

    @app.post(PREFIX + "/gaps")
    async def gap(request: Request):
        body, key_id, now = await read_and_authorize(request, "archive:submit")
        try:
            envelope = strict_json(body)
            if (not isinstance(envelope, dict) or set(envelope) != {"contract", "reason", "evidence"}
                    or envelope["contract"] != "historical-archive-gap-v1"):
                raise ValueError("invalid gap envelope")
            return await run_in_threadpool(store.record_gap, envelope["evidence"], reason=envelope["reason"],
                                           submitter_id=key_id, now=now)
        except (ValueError, TypeError, RecursionError, sqlite3.Error, OSError) as exc:
            raise failure(exc) from None

    @app.get(PREFIX + "/receipts/{archive_id}")
    async def receipt(request: Request, archive_id: str):
        await read_and_authorize(request, "archive:read")
        try:
            return await run_in_threadpool(store.get_receipt, archive_id)
        except (ValueError, sqlite3.Error, OSError) as exc:
            raise failure(exc) from None

    @app.get(PREFIX + "/objects/{archive_id}")
    async def original(request: Request, archive_id: str):
        await read_and_authorize(request, "archive:read")
        try:
            raw = await run_in_threadpool(store.read_original, archive_id)
        except (ValueError, sqlite3.Error, OSError) as exc:
            raise failure(exc) from None
        if raw is None:
            raise HTTPException(404, "archived original unavailable")
        return Response(raw, media_type="application/octet-stream")

    return app

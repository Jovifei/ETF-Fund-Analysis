from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings


def _extract_bearer(value: str | None) -> str | None:
    if not value:
        return None
    prefix = "Bearer "
    if value.startswith(prefix):
        return value[len(prefix) :].strip()
    return None


async def require_private_access(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.auth_enabled:
        return
    supplied = _extract_bearer(authorization) or ""
    if not supplied or not hmac.compare_digest(supplied, settings.private_access_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少或无效的私有访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

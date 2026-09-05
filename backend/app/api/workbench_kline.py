from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import require_private_access
from app.db.session import get_db
from app.services.kline_stabilization_service import KlineStabilizationService

router = APIRouter(
    prefix="/api/workbench/kline",
    tags=["kline-stabilization-workbench"],
    dependencies=[Depends(require_private_access)],
)


@router.get("/summary")
def summary(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    payload = KlineStabilizationService(settings).summary(db)
    # PR-I：该兼容 API 已废弃——K线研判并入 /etf/{code} 详情台，宽度并入 /boards。
    payload["deprecated"] = True
    payload["successor"] = "/etf/{ts_code} + /boards"
    return payload

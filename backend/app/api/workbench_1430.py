from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import require_private_access
from app.db.session import get_db
from app.services.etf_1430_service import ETF1430WorkbenchService

router = APIRouter(
    prefix="/api/workbench/1430",
    tags=["etf-1430-workbench"],
    dependencies=[Depends(require_private_access)],
)


@router.get("/summary")
def summary(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    return ETF1430WorkbenchService(settings).summary(db)


@router.post("/generate")
def generate(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    result = ETF1430WorkbenchService(settings).generate_report(db)
    db.commit()
    return result


@router.get("/{ts_code}")
def detail(
    ts_code: str,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    result = ETF1430WorkbenchService(settings).detail(db, ts_code)
    if result is None:
        raise HTTPException(status_code=404, detail="未找到ETF/LOF标的")
    return result

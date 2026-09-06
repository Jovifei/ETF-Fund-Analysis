from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import optional_current_user, require_private_access
from app.db.session import get_db
from app.models import AuthUser
from app.workspace import read_model
from app.workspace.actions_api import router as actions_router
from app.workspace.bridge_api import router as device_router
from app.workspace.import_revisions import router as revision_router

private_router = APIRouter(prefix="/api", dependencies=[Depends(require_private_access)])
DB = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
User = Annotated[AuthUser | None, Depends(optional_current_user)]


@private_router.get("/search/instruments")
def search(db: DB, settings: Config, user: User, response: Response, q: str = Query(default="", max_length=64), limit: int = Query(default=20, ge=1, le=100)) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    return read_model.search_instruments(db, settings, q, limit, user.id if user else None)


@private_router.get("/workspace/overview")
def overview(db: DB, settings: Config, user: User, horizon: int = Query(default=1), offset: int = Query(default=0, ge=0, le=10000), limit: int = Query(default=100, ge=1, le=500), theme: str | None = Query(default=None, max_length=128)) -> dict:
    if horizon not in (1, 3, 5, 10):
        raise HTTPException(422, "horizon must be one of 1, 3, 5, 10")
    return read_model.overview(db, settings, horizon, offset, limit, theme)


@private_router.get("/workspace/instruments/{code}")
def detail(code: str, db: DB, settings: Config, user: User) -> dict:
    result = read_model.instrument_detail(db, settings, code.upper(), user.id if user else None)
    if result is None:
        raise HTTPException(404, "ETF/LOF 不在已同步目录中")
    return result


@private_router.get("/workspace/instruments/{code}/chart")
def chart(code: str, db: DB, settings: Config, user: User, interval: Literal["1d", "30m", "60m"] = "1d", limit: int = Query(default=260, ge=30, le=1500)) -> dict:
    result = read_model.chart_data(db, settings, code.upper(), interval, limit)
    if result is None:
        raise HTTPException(404, "ETF/LOF 不在已同步目录中")
    return result


@private_router.get("/workspace/sectors")
def sectors(db: DB, settings: Config, user: User) -> dict:
    return read_model.sector_overview(db, settings)


@private_router.get("/workspace/holdings")
def holdings(db: DB, settings: Config, user: User) -> dict:
    return read_model.holdings_view(db, settings, user.id if user else None)


@private_router.get("/workspace/portfolio-risk")
def portfolio_risk(db: DB, settings: Config, user: User) -> dict:
    return read_model.portfolio_risk(db, settings, user.id if user else None)


@private_router.get("/workspace/factors")
def factors(db: DB, settings: Config, user: User) -> dict:
    return read_model.factor_view(db, settings)


private_router.include_router(actions_router)
private_router.include_router(revision_router)
# Machine credentials never inherit the legacy browser authentication path.
router = APIRouter()
router.include_router(private_router)
router.include_router(device_router)

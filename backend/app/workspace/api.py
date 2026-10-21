from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import optional_current_user, require_admin, require_private_access
from app.db.session import get_db
from app.models import AuthUser, Instrument
from app.utils.horizons import DEFAULT_RESEARCH_HORIZONS
from app.workspace import read_model
from app.workspace.actions_api import router as actions_router
from app.workspace.bridge_api import router as device_router
from app.workspace.import_revisions import router as revision_router

private_router = APIRouter(prefix="/api", dependencies=[Depends(require_private_access)])
DB = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
User = Annotated[AuthUser | None, Depends(optional_current_user)]


def _instrument_missing_reason(db: Session, code: str) -> str:
    record = db.scalar(select(Instrument).where(Instrument.ts_code == code.upper()))
    return "instrument_not_in_catalog" if record is None else "unsupported_instrument_type"


@private_router.get("/search/instruments")
def search(db: DB, settings: Config, user: User, response: Response, q: str = Query(default="", max_length=64), limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0, le=10000), sort: Literal["relevance","scale","turnover"] = "relevance", min_scale: float = Query(default=0, ge=0, le=1e13), include_unknown: bool = True) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    return read_model.search_instruments(db, settings, q, limit, user.id if user else None, offset=offset, sort=sort, min_scale=min_scale, include_unknown=include_unknown)


def _local_reader(settings: Settings):
    from app.workspace.local_display_read import LocalDisplayReader, LocalDisplayStore
    store = LocalDisplayStore(settings.local_display_v2_store_root, max_bytes=settings.local_display_v2_max_bytes)
    return LocalDisplayReader(store, code_sha=settings.shadow_sync_code_sha, config_hash=settings.shadow_sync_config_hash)


@private_router.get("/workspace/overview")
def overview(db: DB, settings: Config, user: User, horizon: int = Query(default=1), offset: int = Query(default=0, ge=0, le=10000), limit: int = Query(default=100, ge=1, le=500), theme: str | None = Query(default=None, max_length=128), generation: str | None = Query(default=None)) -> dict:
    if horizon not in DEFAULT_RESEARCH_HORIZONS:
        raise HTTPException(422, "horizon must be one of 1, 3, 7, 20, 60")
    if settings.workspace_research_source == "local_bundle":
        return _local_reader(settings).read_overview(horizon, offset, limit, theme, generation=generation)
    return read_model.overview(db, settings, horizon, offset, limit, theme)


@private_router.get("/workspace/instruments/{code}")
def detail(code: str, db: DB, settings: Config, user: User, generation: str | None = Query(default=None)) -> dict:
    if settings.workspace_research_source == "local_bundle":
        res = _local_reader(settings).read_instrument_detail(code, user.id if user else None, generation=generation)
        if res is None:
            raise HTTPException(404, _instrument_missing_reason(db, code))
        return res
    result = read_model.instrument_detail(db, settings, code.upper(), user.id if user else None)
    if result is None:
        raise HTTPException(404, _instrument_missing_reason(db, code))
    return result


@private_router.get("/workspace/instruments/{code}/chan")
def chan_evidence(code: str, db: DB, response: Response, settings: Config, interval: Literal["D", "W", "M"] = "D") -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    if settings.workspace_research_source == "local_bundle":
        raise HTTPException(404, "chan_evidence_not_published_in_local_bundle")
    result = read_model.chan_evidence(db, code, interval)
    if result is None:
        raise HTTPException(404, _instrument_missing_reason(db, code))
    return result


@private_router.get("/workspace/instruments/{code}/chart")
def chart(code: str, db: DB, settings: Config, user: User, interval: str = "1d", limit: int = Query(default=260, ge=30, le=1500), as_of: Annotated[datetime | None, Query()] = None, generation: str | None = Query(default=None)) -> dict:
    if interval not in {"1d", "1w", "1mo", "30m", "60m"}:
        raise HTTPException(422, "unsupported_chart_interval")
    if as_of is not None and read_model.market_time(as_of) > read_model.market_time(datetime.now(read_model.SHANGHAI)):
        raise HTTPException(422, "as_of_in_future")
    if settings.workspace_research_source == "local_bundle":
        try:
            res = _local_reader(settings).read_chart_data(code, interval, limit, generation=generation, as_of=as_of)
            if res is None:
                raise HTTPException(404, _instrument_missing_reason(db, code))
            return res
        except ValueError as exc:
            if "generation_time_mismatch" in str(exc):
                raise HTTPException(409, "generation_time_mismatch") from None
            if "unsupported_chart_interval" in str(exc):
                raise HTTPException(422, "unsupported_chart_interval")
            raise
    result = read_model.chart_data(db, settings, code.upper(), interval, limit, as_of=as_of)
    if result is None:
        raise HTTPException(404, _instrument_missing_reason(db, code))
    if interval=="1d":
        from app.workspace.candle_periods import transform_chart
        result=transform_chart(result,interval,settings.load_strategy()["indicator"],limit,now=as_of)
    chan_interval = {"1d": "D", "1w": "W", "1mo": "M"}.get(interval)
    if chan_interval is not None:
        from app.workspace.chan_chart_overlay import annotate_chart_chan
        result = annotate_chart_chan(result, read_model.chan_evidence(db, code.upper(), chan_interval))
    return result


@private_router.get("/workspace/sectors")
def sectors(db: DB, settings: Config, user: User, generation: str | None = Query(default=None)) -> dict:
    if settings.workspace_research_source == "local_bundle":
        return _local_reader(settings).read_sectors(generation=generation)
    return read_model.sector_overview(db, settings)


@private_router.get("/workspace/holdings")
def holdings(db: DB, settings: Config, user: User) -> dict:
    return read_model.holdings_view(db, settings, user.id if user else None)


@private_router.get("/workspace/portfolio-risk")
def portfolio_risk(db: DB, settings: Config, user: User) -> dict:
    return read_model.portfolio_risk(db, settings, user.id if user else None)


@private_router.get("/workspace/factors")
def factors(db: DB, settings: Config, user: User) -> dict:
    if settings.workspace_research_source == "local_bundle":
        return {"available": False, "items": [], "reason": "factors_not_published_in_local_bundle", "actionable": False}
    return read_model.factor_view(db, settings)


private_router.include_router(actions_router)
private_router.include_router(revision_router)
from app.workspace.journal import router as journal_router  # noqa: E402

private_router.include_router(journal_router)
# Machine credentials never inherit the legacy browser authentication path.
router = APIRouter()


@router.get("/api/auth/capabilities")
def auth_capabilities(settings: Config, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return {"registration_enabled": bool(settings.auth_enabled and settings.registration_enabled and settings.registration_invite_code),
            "invite_required": True, "self_registration_role": "member"}


@private_router.get("/workspace/discovery")
def discovery_state(db: DB, user: User) -> dict:
    from app.workspace.discovery import state
    return state(db)


@private_router.post("/workspace/discovery/refresh", status_code=202)
def discovery_refresh(db: DB, admin: Annotated[AuthUser | None, Depends(require_admin)]) -> dict:
    from app.workspace.discovery import enqueue
    result = enqueue(db, admin.id if admin else None, manual=True)
    db.commit()
    return result


@private_router.get("/workspace/indexes")
def index_summaries(db: DB, settings: Config, user: User, generation: str | None = Query(default=None)) -> dict:
    if settings.workspace_research_source == "local_bundle":
        items = _local_reader(settings).read_market_context(generation=generation) or []
        return {"items": [row for row in items if row.get("context_kind") == "index"], "provider_called": False, "actionable": False}
    from sqlalchemy import select

    from app.models import MarketContextRegistry
    from app.workspace import index_history
    rows=db.scalars(select(MarketContextRegistry).where(MarketContextRegistry.context_kind=='index',MarketContextRegistry.enabled.is_(True))).all()
    items=[]
    for row in rows:
        value=index_history.read(db,settings,row.context_id,limit=1)
        if value and value['available']:
            items.append({'context_id':row.context_id,'label':row.label,'context_kind':'index',
                'observed_value':value['summary']['price'], 'today_pct_change':None if value['summary']['change_ratio'] is None else value['summary']['change_ratio']*100,
                'source_timestamp':value['source_as_of'],'source':value['bars'][-1].get('source'),
                'freshness':'historical','is_partial':value['summary']['is_partial'],'is_tradable_proxy':False})
    return {'items':items,'provider_called':False,'actionable':False}


@private_router.get("/workspace/indexes/{context_id}/chart")
def index_chart(context_id: str, db: DB, settings: Config, user: User,
                limit: int = Query(default=500, ge=30, le=1500), interval: Literal["1d","1w","1mo"]="1d"):
    if settings.workspace_research_source == "local_bundle":
        raise HTTPException(404, "index_chart_not_published_in_local_bundle")
    from app.workspace.index_history import read
    result = read(db, settings, context_id, 1500)
    if result is None:
        raise HTTPException(404, "index not registered")
    from app.workspace.candle_periods import transform_chart
    return transform_chart(result,interval,settings.load_strategy()["indicator"],limit)


@private_router.get("/workspace/storage")
def storage_status(db: DB, settings: Config, admin: Annotated[AuthUser | None, Depends(require_admin)]):
    from app.workspace.storage import status
    return status(db,settings)

@private_router.get("/workspace/catalog-preparation")
def history_preparation(db: DB, admin: Annotated[AuthUser | None, Depends(require_admin)], limit: int=Query(default=10,ge=1,le=30), minimum_scale: float=Query(default=0,ge=0,le=1e13), include_unknown: bool=True):
    from app.workspace.storage import prepare_plan
    return prepare_plan(db,limit=limit,minimum_scale=minimum_scale,include_unknown=include_unknown)

@private_router.get("/workspace/research-outlook")
def research_outlook(db: DB, settings: Config, user: User, code: str|None=Query(default=None,pattern=r"^\d{6}\.(SH|SZ|BJ)$")):
    if settings.workspace_research_source == "local_bundle":
        return {"items": {}, "horizons": [], "provider_called": False, "actionable": False,
                "reason": "outlook_not_published_in_local_bundle"}
    from sqlalchemy import select

    from app.models import Instrument
    from app.workspace.research_outlook import VERSION, read
    codes=[code] if code else list(db.scalars(select(Instrument.ts_code).where(Instrument.enabled.is_(True)).order_by(Instrument.ts_code).limit(200)))
    return {'items':read(db,codes),'model_version':VERSION,'horizons':[1,5,20],'provider_called':False,'actionable':False}


@private_router.get("/workspace/news-status")
def news_status(db: DB, settings: Config, user: User):
    from app.workspace.news_status import read
    return read(db, settings=settings)

from app.workspace.ai_api import members as member_router  # noqa: E402
from app.workspace.ai_api import router as ai_router  # noqa: E402

private_router.include_router(ai_router)
private_router.include_router(member_router)

@private_router.get("/workspace/market-context")
def context_read_view(db: DB, settings: Config, response: Response, user: User, generation: str | None = Query(default=None)) -> dict:
    from datetime import datetime

    from app.services.market_context_service import MarketContextService
    from app.workspace.display_freshness import context_display
    now = datetime.now(settings.timezone)
    response.headers["Cache-Control"] = "private, no-store"
    if settings.workspace_research_source == "local_bundle":
        mc_items = _local_reader(settings).read_market_context(generation=generation) or []
        result = [{**row, "display_time": context_display(
            row.get("observation"), now=now, context_kind=row["context_kind"], timezone=settings.timezone
        )} for row in mc_items]
        return {"latest_view": result, "as_of": now.isoformat(), "provider_called": False}
    rows = MarketContextService(provider=None, settings=settings).latest_view(db)
    result = [{**row, "display_time": context_display(
        row.get("observation"), now=now, context_kind=row["context_kind"], timezone=settings.timezone
    )} for row in rows]
    return {"latest_view": result, "as_of": now.isoformat(), "provider_called": False}



@private_router.get("/workspace/data-health")
def data_health(db: DB, settings: Config, response: Response,
                admin: Annotated[AuthUser | None, Depends(require_admin)]) -> dict:
    from app.workspace.data_health import read
    response.headers["Cache-Control"] = "private, no-store"
    return read(db, settings)


# Include after all decorators: FastAPI copies routes at include time.
router.include_router(private_router)
router.include_router(device_router)

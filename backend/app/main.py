from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import router as api_router
from app.api.workbench_1430 import router as workbench_1430_router
from app.api.workbench_kline import router as workbench_kline_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import init_db, session_scope
from app.services.holding_import_service import HoldingImportService
from app.services.runtime_service import RuntimeService
from app.workspace.api import router as workspace_router
from app.workspace.ui import WorkspaceMiddleware

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_schema:
        init_db()
    with session_scope() as db:
        RuntimeService(settings).ensure_defaults(db)
    try:
        with session_scope() as db:
            HoldingImportService(settings).cleanup_expired(db)
    except Exception:
        logger.warning("holding import cleanup unavailable; retrying later")
    logger.info(
        "starting %s version=%s env=%s provider=%s",
        settings.app_name,
        settings.app_version,
        settings.app_env,
        settings.market_provider,
    )
    try:
        yield
    finally:
        from app.services.demo_service import DemoService
        DemoService.close()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="私有 ETF/LOF 研究看板。技术指标与信号为确定性计算，AI 仅用于结构化研究解读。",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

# The security-header middleware below remains outermost, including Vue files.
app.add_middleware(WorkspaceMiddleware)


@app.middleware("http")
async def request_id(request: Request, call_next):
    request_id_value = request.headers.get("X-Request-ID", uuid4().hex)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id_value
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; form-action 'self'"
    )
    return response


app.include_router(api_router)
app.include_router(workbench_1430_router)
app.include_router(workbench_kline_router)
app.include_router(workspace_router)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "decision_board_workbuddy.html", media_type="text/html; charset=utf-8")


@app.get("/legacy", include_in_schema=False)
def legacy() -> RedirectResponse:
    return RedirectResponse("/research", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/decision/1430", include_in_schema=False)
def decision_1430() -> FileResponse:
    return FileResponse(STATIC_DIR / "etf_1430_workbench.html", media_type="text/html; charset=utf-8")


@app.get("/workbench/1430", include_in_schema=False)
def legacy_etf_1430_workbench() -> RedirectResponse:
    return RedirectResponse("/decision/1430", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/workbench/kline", include_in_schema=False)
def kline_stabilization() -> RedirectResponse:
    return RedirectResponse("/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/boards", include_in_schema=False)
def boards_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "boards.html", media_type="text/html; charset=utf-8")


def _research_shell() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html; charset=utf-8")


@app.get("/holdings", include_in_schema=False)
def holdings_entry() -> FileResponse:
    return _research_shell()


@app.get("/research", include_in_schema=False)
def research_entry() -> FileResponse:
    return _research_shell()


@app.get("/research/news", include_in_schema=False)
def research_news_entry() -> FileResponse:
    return _research_shell()


@app.get("/system", include_in_schema=False)
def system_entry() -> FileResponse:
    return _research_shell()


@app.get("/etf/{ts_code}", include_in_schema=False)
def etf_detail(ts_code: str) -> FileResponse:
    return FileResponse(STATIC_DIR / "etf_detail.html", media_type="text/html; charset=utf-8")


@app.get("/assets/index.html", include_in_schema=False)
def static_legacy_index() -> RedirectResponse:
    return RedirectResponse("/research", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/assets/etf_1430_workbench.html", include_in_schema=False)
def static_etf_1430_workbench() -> RedirectResponse:
    return RedirectResponse("/decision/1430", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/assets/kline_stabilization.html", include_in_schema=False)
def static_kline_stabilization() -> RedirectResponse:
    return RedirectResponse("/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

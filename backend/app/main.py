from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
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
    description="私有 ETF/LOF 研究看板。技术指标与信号为确定性计算，AI 仅用于结构化新闻解读。",
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


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "decision_board_workbuddy.html", media_type="text/html; charset=utf-8")


@app.get("/legacy", include_in_schema=False)
def legacy() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html; charset=utf-8")


@app.get("/workbench/1430", include_in_schema=False)
def etf_1430_workbench() -> FileResponse:
    return FileResponse(STATIC_DIR / "etf_1430_workbench.html", media_type="text/html; charset=utf-8")


@app.get("/workbench/kline", include_in_schema=False)
def kline_stabilization() -> FileResponse:
    return FileResponse(STATIC_DIR / "kline_stabilization.html", media_type="text/html; charset=utf-8")


@app.get("/etf/{ts_code}", include_in_schema=False)
def etf_detail(ts_code: str) -> FileResponse:
    # 全站唯一的 ETF 详情研判台：决策表 / 板块 / 持仓 / 14:30 工作台点击标的都进入这里。
    return FileResponse(STATIC_DIR / "etf_detail.html", media_type="text/html; charset=utf-8")


@app.get("/assets/index.html", include_in_schema=False)
def static_legacy_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html; charset=utf-8")


@app.get("/assets/etf_1430_workbench.html", include_in_schema=False)
def static_etf_1430_workbench() -> FileResponse:
    return FileResponse(STATIC_DIR / "etf_1430_workbench.html", media_type="text/html; charset=utf-8")


@app.get("/assets/kline_stabilization.html", include_in_schema=False)
def static_kline_stabilization() -> FileResponse:
    return FileResponse(STATIC_DIR / "kline_stabilization.html", media_type="text/html; charset=utf-8")


# Mount static resources after exact legacy-HTML redirects so old bookmarks cannot
# bypass the single user-facing ETF board while CSS/JS/assets remain available.
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

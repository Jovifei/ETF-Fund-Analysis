from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
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
APP_SHELL_ASSET = "/assets/app_shell.js?v=0.8.0-nav1"
APP_SHELL_TAG = f'<script src="{APP_SHELL_ASSET}" defer></script>'


def _page_response(filename: str) -> HTMLResponse:
    """Serve one static surface with the single shared navigation contract."""
    html = (STATIC_DIR / filename).read_text(encoding="utf-8")
    if APP_SHELL_ASSET not in html:
        if "</body>" not in html:
            raise RuntimeError(f"static HTML page is missing </body>: {filename}")
        html = html.replace("</body>", f"  {APP_SHELL_TAG}\n</body>", 1)
    return HTMLResponse(content=html, media_type="text/html")


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
def index() -> HTMLResponse:
    return _page_response("decision_board_workbuddy.html")


@app.get("/legacy", include_in_schema=False)
def legacy() -> HTMLResponse:
    return _page_response("index.html")


@app.get("/portfolio", include_in_schema=False)
def portfolio() -> RedirectResponse:
    return RedirectResponse("/legacy#holdings", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/research", include_in_schema=False)
def research() -> RedirectResponse:
    return RedirectResponse("/legacy#signals", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/workbench/1430", include_in_schema=False)
def etf_1430_workbench() -> HTMLResponse:
    return _page_response("etf_1430_workbench.html")


@app.get("/workbench/kline", include_in_schema=False)
def kline_stabilization() -> RedirectResponse:
    # PR-I：K线研判页下线——K线/支撑压力由 /etf/{code} 详情台承接，
    # 行业/概念/全市场宽度三列由 /boards 承接；旧地址 307 保留一个版本。
    return RedirectResponse("/boards", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/boards", include_in_schema=False)
def boards_page() -> HTMLResponse:
    return _page_response("boards.html")


@app.get("/etf/{ts_code}", include_in_schema=False)
def etf_detail(ts_code: str) -> HTMLResponse:
    # 全站唯一的 ETF 详情研判台：决策表 / 板块 / 持仓 / 14:30 工作台点击标的都进入这里。
    return _page_response("etf_detail.html")


@app.get("/assets/index.html", include_in_schema=False)
def static_legacy_index() -> HTMLResponse:
    return _page_response("index.html")


@app.get("/assets/etf_1430_workbench.html", include_in_schema=False)
def static_etf_1430_workbench() -> HTMLResponse:
    return _page_response("etf_1430_workbench.html")


@app.get("/assets/kline_stabilization.html", include_in_schema=False)
def static_kline_stabilization() -> RedirectResponse:
    return RedirectResponse("/boards", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


# Mount static resources after exact legacy-HTML redirects so old bookmarks cannot
# bypass the single user-facing ETF board while CSS/JS/assets remain available.
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

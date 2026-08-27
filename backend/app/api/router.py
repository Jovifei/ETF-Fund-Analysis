from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.schemas import HoldingUpsert, RuntimeUpdate, TaskRequest
from app.core.config import Settings, get_settings
from app.core.security import require_private_access
from app.db.session import SessionLocal, get_db
from app.models import EventLog, ReportArtifact
from app.services.dashboard_service import DashboardService
from app.services.holding_service import HoldingNotFoundError, HoldingService
from app.services.report_service import ReportService
from app.services.runtime_service import RuntimeService
from app.services.task_service import TaskBusyError, TaskService, UnknownTaskError

router = APIRouter(prefix="/api")
private_router = APIRouter(dependencies=[Depends(require_private_access)])


@router.get("/health")
def health(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "provider": settings.market_provider,
        "auth_enabled": settings.auth_enabled,
    }


@private_router.get("/bootstrap")
def bootstrap(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    return DashboardService(settings).bootstrap(db)


@private_router.get("/instruments")
def instruments(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[dict]:
    return DashboardService(settings).instrument_rows(db)


@private_router.get("/instruments/{ts_code}/bars")
def bars(
    ts_code: str,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = Query(default=260, ge=10, le=1500),
) -> list[dict]:
    result = DashboardService(settings).bars(db, ts_code, limit)
    if not result:
        raise HTTPException(status_code=404, detail="未找到标的或历史 K 线")
    return result


@private_router.get("/news")
def news(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = Query(default=30, ge=1, le=200),
) -> list[dict]:
    return DashboardService(settings).recent_news(db, limit)


@private_router.get("/holdings")
def holdings(db: Annotated[Session, Depends(get_db)]) -> list[dict]:
    return HoldingService().list(db)


@private_router.put("/holdings/{ts_code}")
def upsert_holding(
    ts_code: str,
    payload: HoldingUpsert,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    if payload.ts_code != ts_code.upper():
        raise HTTPException(status_code=400, detail="路径代码与请求体 ts_code 不一致")
    try:
        HoldingService().upsert(
            db,
            ts_code=payload.ts_code,
            shares=payload.shares,
            cost_price=payload.cost_price,
            target_weight=payload.target_weight,
            notes=payload.notes,
        )
        db.commit()
    except HoldingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok", "holding": HoldingService().list(db)}


@private_router.delete("/holdings/{ts_code}")
def delete_holding(ts_code: str, db: Annotated[Session, Depends(get_db)]) -> dict:
    try:
        deleted = HoldingService().delete(db, ts_code.upper())
        db.commit()
    except HoldingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok", "deleted": deleted}


@private_router.get("/settings")
def runtime_settings(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    service = RuntimeService(settings)
    result = service.get_all(db)
    db.commit()
    return result


@private_router.put("/settings")
def update_runtime_settings(
    payload: RuntimeUpdate,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    result = RuntimeService(settings).update(db, payload.compact())
    db.commit()
    return result


@private_router.get("/tasks")
def task_history(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = Query(default=30, ge=1, le=200),
) -> list[dict]:
    return DashboardService(settings).task_runs(db, limit)


@private_router.post("/tasks/{task_name}")
def run_task(
    task_name: str,
    payload: TaskRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    try:
        result = TaskService(settings).run(db, task_name, **payload.compact())
        db.commit()
        return result
    except UnknownTaskError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TaskBusyError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        db.commit()  # persist failed TaskRun/provider audit before returning error
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


@private_router.post("/reports")
def generate_report(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    result = ReportService(settings).generate(db)
    db.commit()
    return result


@private_router.get("/reports")
def list_reports(
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=30, ge=1, le=200),
) -> list[dict]:
    rows = db.scalars(
        select(ReportArtifact).order_by(ReportArtifact.created_at.desc()).limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "type": row.report_type,
            "as_of_time": row.as_of_time,
            "filename": Path(row.file_path).name,
            "content_hash": row.content_hash,
            "metadata": row.metadata_json,
            "url": f"/api/reports/{Path(row.file_path).name}",
        }
        for row in rows
    ]


@private_router.get("/reports/{filename}")
def download_report(
    filename: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    safe_name = Path(filename).name
    allowed = safe_name.endswith(".html") or safe_name.endswith(".json")
    if safe_name != filename or not allowed:
        raise HTTPException(status_code=400, detail="非法报告文件名")
    path = settings.reports_dir / safe_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="报告不存在")
    media_type = "text/html; charset=utf-8" if safe_name.endswith(".html") else "application/json"
    return FileResponse(path, media_type=media_type, filename=safe_name)


@private_router.get("/events")
async def events(
    after_id: int = Query(default=0, ge=0),
) -> StreamingResponse:
    async def stream():
        cursor = after_id
        yield "retry: 3000\n\n"
        while True:
            with SessionLocal() as db:
                rows = db.scalars(
                    select(EventLog).where(EventLog.id > cursor).order_by(EventLog.id).limit(100)
                ).all()
                for row in rows:
                    cursor = row.id
                    payload = json.dumps(row.payload_json, ensure_ascii=False, default=str)
                    yield f"id: {row.id}\nevent: {row.event_type}\ndata: {payload}\n\n"
            yield ": keepalive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


router.include_router(private_router)

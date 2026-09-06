from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import optional_current_user, require_admin
from app.db.session import get_db
from app.models import AuthUser, Instrument, QuoteSnapshot, UserWatchlistEntry
from app.services.holding_import_service import HoldingImportError, HoldingImportService
from app.workspace import bridge_api, data_jobs, imports, jobs, read_model
from app.workspace.config import workspace_settings
from app.workspace.models import WorkspaceBridgeDevice, WorkspaceDataJob, WorkspaceImportBatch, WorkspacePreference, WorkspaceResearchJob
from app.workspace.protocol import DataRequest, DeviceRequest, Preferences, ResearchRequest, ResearchResult, ReviewRequest, canonical_bytes, content_hash


def translate_errors():
    try:
        yield
    except jobs.WorkspaceError as exc:
        raise HTTPException(exc.status, exc.code) from None


router = APIRouter(prefix="/workspace", dependencies=[Depends(translate_errors)])
DB = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
User = Annotated[AuthUser | None, Depends(optional_current_user)]
Admin = Annotated[AuthUser | None, Depends(require_admin)]


@router.get("/status")
def status(db: DB, settings: Config, user: User):
    cfg = workspace_settings()
    heartbeat = db.get(WorkspacePreference, "system:workspace-worker")
    strategy = settings.load_strategy()
    return {"app_version": settings.app_version, "workspace_version": "0.9.0-rc.1", "strategy_version": strategy.get("version"), "indicator_version": strategy.get("indicator_version"), "forecast_version": strategy.get("forecast_version"), "market_provider": settings.market_provider, "ui_enabled": cfg.ui_enabled, "bridge_enabled": cfg.bridge_enabled, "daily_review_enabled": cfg.daily_review_enabled, "worker": heartbeat.settings_json if heartbeat else None, "catalog_count": db.scalar(select(func.count()).select_from(Instrument).where(Instrument.kind.in_(("ETF", "LOF")))), "tracked_count": db.scalar(select(func.count()).select_from(Instrument).where(Instrument.enabled.is_(True))), "historical_1430_backtest": "not_qualified", "api_key_configuration": "disabled_pending_secure_secret_store", "automatic_orders": False}


@router.get("/watchlist")
def watchlist(db: DB, settings: Config, user: User):
    pairs = db.execute(select(UserWatchlistEntry, Instrument).join(Instrument, UserWatchlistEntry.instrument_id == Instrument.id).where(UserWatchlistEntry.user_id == (user.id if user else None)).order_by(UserWatchlistEntry.id.desc()).limit(500)).all()
    quotes = read_model.latest_rows(db, QuoteSnapshot, [inst.id for _, inst in pairs], QuoteSnapshot.quote_time.desc())
    return {"items": [{"id": entry.id, "ts_code": inst.ts_code, "name": inst.name, "kind": inst.kind, "theme": inst.theme_l1, "note": entry.note, "enabled": inst.enabled, "quote": read_model.quote_view(quotes.get(inst.id), settings)} for entry, inst in pairs]}


@router.get("/preferences")
def preferences(db: DB, user: User):
    row = db.get(WorkspacePreference, jobs.owner_scope(user.id if user else None))
    return Preferences.model_validate(row.settings_json if row else {}).model_dump()


@router.put("/preferences")
def update_preferences(payload: Preferences, db: DB, user: User):
    user_id = user.id if user else None
    scope = jobs.owner_scope(user_id)
    row = db.get(WorkspacePreference, scope)
    if row is None:
        row = WorkspacePreference(owner_scope=scope, user_id=user_id)
        db.add(row)
    row.settings_json = payload.model_dump()
    db.commit()
    return row.settings_json


@router.post("/research-jobs", status_code=202)
def create_research(payload: ResearchRequest, db: DB, settings: Config, user: User):
    row, created = jobs.enqueue(db, settings, payload, user.id if user else None)
    db.commit()
    return {"job": jobs.job_view(row), "created": created, "model_called": False}


@router.get("/research-jobs")
def list_research(db: DB, user: User, kind: Literal["etf", "daily"] | None = None, code: str | None = Query(default=None, max_length=32), limit: int = Query(default=50, ge=1, le=200)):
    query = select(WorkspaceResearchJob).where(WorkspaceResearchJob.owner_scope == jobs.owner_scope(user.id if user else None))
    if kind:
        query = query.where(WorkspaceResearchJob.kind == kind)
    if code:
        query = query.where(WorkspaceResearchJob.ts_code == code.upper())
    return {"items": [jobs.job_view(row) for row in db.scalars(query.order_by(WorkspaceResearchJob.created_at.desc()).limit(limit))]}


@router.get("/research-jobs/{job_id}")
def get_research(job_id: str, db: DB, user: User):
    return jobs.job_view(jobs.owned_job(db, job_id, jobs.owner_scope(user.id if user else None)), detail=True)


@router.get("/research-jobs/{job_id}/export")
def export_research(job_id: str, db: DB, user: User):
    row = jobs.owned_job(db, job_id, jobs.owner_scope(user.id if user else None))
    payload = {"job_id": row.job_id, "input_hash": row.input_hash, "bundle": row.bundle_json}
    return Response(canonical_bytes(payload), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="evidence-{row.job_id}.json"', "Cache-Control": "no-store"})


@router.post("/research-jobs/{job_id}/result")
def import_research(job_id: str, payload: ResearchResult, db: DB, user: User):
    row = jobs.owned_job(db, job_id, jobs.owner_scope(user.id if user else None), lock=True)
    jobs.accept_result(db, row, payload)
    db.commit()
    return jobs.job_view(row, detail=True)


@router.post("/research-jobs/{job_id}/review/{decision}")
def review_research(job_id: str, decision: Literal["accepted", "rejected"], payload: ReviewRequest, db: DB, user: User):
    row = jobs.owned_job(db, job_id, jobs.owner_scope(user.id if user else None), lock=True)
    jobs.review(db, row, payload.result_hash, decision, payload.note)
    db.commit()
    return jobs.job_view(row, detail=True)


@router.post("/research-jobs/{job_id}/cancel")
def cancel_research(job_id: str, db: DB, user: User):
    row = jobs.owned_job(db, job_id, jobs.owner_scope(user.id if user else None), lock=True)
    if row.status not in {"queued", "running", "cancelled"}:
        raise jobs.WorkspaceError(409, "research_cannot_cancel_terminal_job")
    row.status = "cancelled"
    db.commit()
    return jobs.job_view(row)


@router.post("/research-jobs/{job_id}/retry")
def retry_research(job_id: str, db: DB, user: User):
    row = jobs.owned_job(db, job_id, jobs.owner_scope(user.id if user else None), lock=True)
    jobs.retry(db, row)
    db.commit()
    return jobs.job_view(row)


@router.get("/devices")
def devices(db: DB, user: User):
    rows = db.scalars(select(WorkspaceBridgeDevice).where(WorkspaceBridgeDevice.owner_scope == jobs.owner_scope(user.id if user else None)).order_by(WorkspaceBridgeDevice.created_at.desc()).limit(20))
    return {"items": [bridge_api.device_view(row) for row in rows]}


@router.post("/devices/pairing")
def pairing(payload: DeviceRequest, db: DB, user: User):
    if not workspace_settings().bridge_enabled:
        raise jobs.WorkspaceError(503, "local_bridge_disabled")
    result = bridge_api.new_pairing(db, payload.label, user.id if user else None)
    db.commit()
    return result


@router.delete("/devices/{device_id}")
def revoke(device_id: str, db: DB, user: User):
    row = db.scalar(select(WorkspaceBridgeDevice).where(WorkspaceBridgeDevice.device_id == device_id, WorkspaceBridgeDevice.owner_scope == jobs.owner_scope(user.id if user else None)).with_for_update())
    if row is None:
        raise jobs.WorkspaceError(404, "device_not_found")
    row.status, row.pairing_hash = "revoked", None
    db.execute(update(WorkspaceResearchJob).where(WorkspaceResearchJob.lease_device_id == device_id, WorkspaceResearchJob.status == "running").values(status="failed", failure_reason="device_revoked"))
    db.commit()
    return {"status": "revoked"}


@router.get("/imports")
def list_imports(db: DB, user: User):
    rows = db.scalars(select(WorkspaceImportBatch).where(WorkspaceImportBatch.owner_scope == jobs.owner_scope(user.id if user else None)).order_by(WorkspaceImportBatch.created_at.desc()).limit(20))
    return {"items": [imports.view(row) for row in rows]}


@router.post("/imports/preview")
async def preview_file(db: DB, user: User, file: UploadFile = File(...)):
    try:
        data = await file.read(workspace_settings().import_max_bytes + 1)
        row = imports.preview(db, data, Path(file.filename or "").suffix.lower(), user.id if user else None)
        db.commit()
        return imports.view(row)
    finally:
        await file.close()


@router.post("/imports/preview-rows")
def preview_rows(payload: imports.ManualPreview, db: DB, user: User):
    candidates = [row.model_dump() for row in payload.candidates]
    row = imports.preview_rows(db, candidates, content_hash(candidates), "manual", user.id if user else None)
    db.commit()
    return imports.view(row)


@router.post("/imports/from-ocr/{session_id}")
def preview_ocr(session_id: str, db: DB, settings: Config, user: User):
    user_id = user.id if user else None
    try:
        original = HoldingImportService(settings).get(db, session_id, user_id=user_id)
    except HoldingImportError:
        raise HTTPException(404, "ocr_session_unavailable") from None
    if original.status not in {"ready", "editing"} or jobs.utc(original.expires_at) < datetime.now(UTC):
        raise HTTPException(409, "ocr_session_not_ready")
    candidates = [{"row_index": index + 1, "ts_code": entry.selected_code or entry.ts_code or "", "shares": str(entry.shares) if entry.shares is not None else "", "cost_price": str(entry.cost_price) if entry.cost_price is not None else "", "selected": entry.match_status == "matched"} for index, entry in enumerate(original.candidates)]
    if not candidates:
        raise HTTPException(422, "ocr_no_candidates_use_manual_input")
    row = imports.preview_rows(db, candidates, content_hash({"ocr_session": session_id, "candidates": candidates}), "ocr_preview", user_id)
    db.commit()
    return imports.view(row)


@router.get("/imports/{batch_id}")
def get_import(batch_id: str, db: DB, user: User):
    return imports.view(imports.owned_batch(db, batch_id, jobs.owner_scope(user.id if user else None)))


@router.patch("/imports/{batch_id}")
def edit_import(batch_id: str, payload: imports.ImportEdit, db: DB, user: User):
    row = imports.owned_batch(db, batch_id, jobs.owner_scope(user.id if user else None))
    imports.edit(db, row, payload)
    db.commit()
    return imports.view(row)


@router.post("/imports/{batch_id}/confirm")
def confirm_import(batch_id: str, payload: imports.ImportConfirm, db: DB, user: User):
    row = imports.owned_batch(db, batch_id, jobs.owner_scope(user.id if user else None))
    imports.confirm(db, row, payload.expected_hash)
    db.commit()
    return imports.view(row)


@router.post("/imports/{batch_id}/undo")
def undo_import(batch_id: str, db: DB, user: User):
    row = imports.owned_batch(db, batch_id, jobs.owner_scope(user.id if user else None))
    imports.undo(db, row)
    db.commit()
    return imports.view(row)


@router.post("/imports/{batch_id}/cancel")
def cancel_import(batch_id: str, db: DB, user: User):
    row = imports.owned_batch(db, batch_id, jobs.owner_scope(user.id if user else None))
    if row.status not in {"preview", "cancelled"}:
        raise HTTPException(409, "import_cannot_cancel_confirmed_batch")
    row.status = "cancelled"
    db.commit()
    return imports.view(row)


@router.get("/data-jobs")
def list_data_jobs(db: DB, user: User):
    query = select(WorkspaceDataJob)
    if user is not None and user.role != "admin":
        query = query.where(WorkspaceDataJob.owner_scope == jobs.owner_scope(user.id))
    return {"items": [data_jobs.view(row) for row in db.scalars(query.order_by(WorkspaceDataJob.created_at.desc()).limit(30))]}


@router.post("/data-jobs", status_code=202)
def enqueue_data(payload: DataRequest, db: DB, admin: Admin):
    row, created = data_jobs.enqueue(db, payload, admin.id if admin else None)
    db.commit()
    return {"job": data_jobs.view(row), "created": created, "provider_called": False}


@router.post("/onboard", status_code=202)
def onboard(payload: DataRequest, db: DB, user: User):
    if payload.task != "onboard" or not 1 <= len(payload.codes) <= 3:
        raise HTTPException(422, "onboarding_accepts_one_to_three_explicit_etf_codes")
    row, created = data_jobs.enqueue(db, payload, user.id if user else None)
    db.commit()
    return {"job": data_jobs.view(row), "created": created, "provider_called": False}


@router.get("/factor-diagnostics")
def factor_diagnostics(db: DB, user: User):
    row = db.scalar(select(WorkspaceDataJob).where(WorkspaceDataJob.status.in_(("succeeded", "partial")), WorkspaceDataJob.request_json["task"].as_string() == "factors").order_by(WorkspaceDataJob.finished_at.desc()).limit(1))
    return {"report": (row.result_json or {}).get("factor_report") if row else None, "actionable": False}

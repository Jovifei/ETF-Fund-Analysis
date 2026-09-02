from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import AuthUser, ReportArtifact
from app.services.dashboard_service import DashboardService
from app.services.event_service import emit_event
from app.utils.hashing import stable_hash


class ReportService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        template_dir = Path(__file__).resolve().parents[1] / "templates"
        self.environment = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self.dashboard = DashboardService(self.settings)

    @staticmethod
    def _include_operational_details(db: Session, user_id: int | None) -> bool:
        """Keep global diagnostics out of private member-owned report snapshots."""
        if user_id is None:
            return True
        owner = db.get(AuthUser, user_id)
        return owner is not None and owner.role == "admin" and owner.status == "active"

    def generate(self, db: Session, run_id: str | None = None, *, user_id: int | None = None) -> dict:
        run_id = run_id or uuid4().hex
        now = datetime.now(self.settings.timezone)
        payload = self.dashboard.bootstrap(
            db,
            user_id=user_id,
            include_operational_details=self._include_operational_details(db, user_id),
        )
        template = self.environment.get_template("report.html.j2")
        content_hash = stable_hash(payload)
        filename = f"fund_report_{now:%Y%m%d_%H%M%S_%f}_{content_hash[:10]}_{uuid4().hex[:8]}.html"
        self.settings.reports_dir.mkdir(parents=True, exist_ok=True)
        # Scheduler/bootstrap may emit a market-only diagnostic report.  It is
        # deliberately outside the private artifact registry and cannot be
        # listed or downloaded through the user report API.
        report_dir = self.settings.reports_dir / (f"user-{user_id}" if user_id is not None else "system")
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / filename
        html = template.render(
            app_name=self.settings.app_name,
            generated_at=now,
            summary=payload["summary"],
            instruments=payload["instruments"],
            holdings=payload["holdings"],
            news=payload["news"],
            market_context=payload.get("market_context") or [],
            content_hash=content_hash,
        )
        path.write_text(html, encoding="utf-8")
        db.add(
            ReportArtifact(
                user_id=user_id,
                report_type="dashboard",
                as_of_time=now,
                file_path=str(path),
                content_hash=content_hash,
                metadata_json={
                    "scope": "private" if user_id is not None else "system",
                    "run_id": run_id,
                    "filename": filename,
                    "instrument_count": len(payload["instruments"]),
                    "state_counts": payload["summary"].get("state_counts", {}),
                },
            )
        )
        db.flush()
        if user_id is not None:
            emit_event(db, "report.generated", {"run_id": run_id, "filename": filename, "user_id": user_id})
        return {
            "run_id": run_id,
            "filename": filename,
            "path": str(path),
            "url": f"/api/reports/{filename}",
            "content_hash": content_hash,
        }

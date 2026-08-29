from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import ReportArtifact
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

    def generate(self, db: Session, run_id: str | None = None) -> dict:
        run_id = run_id or uuid4().hex
        now = datetime.now(self.settings.timezone)
        payload = self.dashboard.bootstrap(db)
        template = self.environment.get_template("report.html.j2")
        content_hash = stable_hash(payload)
        filename = f"fund_report_{now:%Y%m%d_%H%M%S}_{content_hash[:10]}.html"
        self.settings.reports_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.reports_dir / filename
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
                report_type="dashboard",
                as_of_time=now,
                file_path=str(path),
                content_hash=content_hash,
                metadata_json={
                    "run_id": run_id,
                    "filename": filename,
                    "instrument_count": len(payload["instruments"]),
                    "state_counts": payload["summary"].get("state_counts", {}),
                },
            )
        )
        db.flush()
        emit_event(db, "report.generated", {"run_id": run_id, "filename": filename})
        return {
            "run_id": run_id,
            "filename": filename,
            "path": str(path),
            "url": f"/api/reports/{filename}",
            "content_hash": content_hash,
        }

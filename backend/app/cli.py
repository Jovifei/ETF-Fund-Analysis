from __future__ import annotations

import json
from typing import Optional

import typer

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import init_db, session_scope
from app.scheduler import tick
from app.services.dashboard_service import DashboardService
from app.services.holding_service import HoldingService
from app.services.task_service import TaskService

app = typer.Typer(no_args_is_help=True, help="中国 ETF/LOF 私有决策看板管理命令")


@app.callback()
def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.auto_create_schema:
        init_db()


@app.command("run-task")
def run_task(
    task_name: str,
    lookback_days: int = typer.Option(900, min=30, max=5000),
    since_hours: int = typer.Option(72, min=1, max=720),
) -> None:
    """Run a deterministic pipeline task in the foreground."""
    service = TaskService()
    try:
        with session_scope() as db:
            result = service.run(
                db,
                task_name,
                lookback_days=lookback_days,
                since_hours=since_hours,
            )
    finally:
        service.close()
    typer.echo(json.dumps(result, ensure_ascii=False, default=str, indent=2))


@app.command("bootstrap")
def bootstrap(
    lookback_days: int = typer.Option(900, min=180, max=5000),
) -> None:
    """Build instruments, bars, indicators, forecasts, quotes, news, signals and an HTML report."""
    service = TaskService()
    try:
        with session_scope() as db:
            result = service.run(db, "bootstrap", lookback_days=lookback_days, report=True)
    finally:
        service.close()
    typer.echo(json.dumps(result, ensure_ascii=False, default=str, indent=2))


@app.command("scheduler-tick")
def scheduler_tick() -> None:
    typer.echo(json.dumps(tick(), ensure_ascii=False, default=str, indent=2))


@app.command("holding-set")
def holding_set(
    ts_code: str,
    shares: float = typer.Option(..., min=0),
    cost_price: float = typer.Option(..., min=0),
    target_weight: Optional[float] = typer.Option(None, min=0, max=1),
    notes: Optional[str] = None,
) -> None:
    with session_scope() as db:
        HoldingService().upsert(
            db,
            ts_code=ts_code.upper(),
            shares=shares,
            cost_price=cost_price,
            target_weight=target_weight,
            notes=notes,
        )
        result = HoldingService().list(db)
    typer.echo(json.dumps(result, ensure_ascii=False, default=str, indent=2))


@app.command("holding-delete")
def holding_delete(ts_code: str) -> None:
    with session_scope() as db:
        deleted = HoldingService().delete(db, ts_code.upper())
    typer.echo("deleted" if deleted else "not found")


@app.command("snapshot")
def snapshot() -> None:
    with session_scope() as db:
        result = DashboardService().bootstrap(db)
    typer.echo(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    app()

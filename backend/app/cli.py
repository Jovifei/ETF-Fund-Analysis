from __future__ import annotations

import json

import typer
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import init_db, session_scope
from app.models import AuthUser, Holding, HoldingImportSession, ReportArtifact
from app.scheduler import tick
from app.services.auth_service import (
    AuthService,
    BootstrapAdminExistsError,
    LastActiveAdminError,
    UserNotFoundError,
    normalize_identifier,
)
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


@app.command("auth-bootstrap-admin")
def auth_bootstrap_admin() -> None:
    """Create the first local admin through hidden prompts; never echo credentials."""
    username = typer.prompt("Admin username").strip()
    email = typer.prompt("Admin email (optional)", default="").strip() or None
    password = typer.prompt("Admin password", hide_input=True, confirmation_prompt=True)
    try:
        with session_scope() as db:
            AuthService().bootstrap_first_admin(db, username=username, email=email, password=password)
    except (BootstrapAdminExistsError, ValueError):
        typer.echo("admin bootstrap rejected")
        raise typer.Exit(code=1) from None
    typer.echo("admin bootstrap completed")


def _find_auth_user(db, username: str) -> AuthUser:
    user = db.scalar(select(AuthUser).where(AuthUser.username == normalize_identifier(username)))
    if user is None:
        raise UserNotFoundError("account not found")
    return user


def _holding_owner_id(db, *, auth_enabled: bool, username: str | None) -> int | None:
    """Select the legacy system owner offline, or one explicit active user online."""
    if not auth_enabled:
        return None
    user = (
        db.scalar(
            select(AuthUser).where(
                AuthUser.username == normalize_identifier(username or ""),
                AuthUser.status == "active",
            )
        )
        if username
        else None
    )
    if user is None:
        typer.echo("holding owner rejected")
        raise typer.Exit(code=1)
    return user.id


@app.command("auth-list-users")
def auth_list_users() -> None:
    """List closed-enrollment accounts without password/session material."""
    with session_scope() as db:
        users = AuthService().list_users(db)
        result = [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "status": user.status,
                "created_at": user.created_at,
                "last_login_at": user.last_login_at,
            }
            for user in users
        ]
    typer.echo(json.dumps(result, ensure_ascii=False, default=str, indent=2))


@app.command("auth-create-user")
def auth_create_user(
    username: str = typer.Option(..., "--username"),
    email: str | None = typer.Option(None, "--email"),
    role: str = typer.Option("member", "--role"),
) -> None:
    """Create an account from a hidden password prompt; there is no public signup."""
    password = typer.prompt("User password", hide_input=True, confirmation_prompt=True)
    try:
        with session_scope() as db:
            user = AuthService().create_user(
                db, username=username, email=email, password=password, role=role.casefold()
            )
            result = {"id": user.id, "username": user.username, "role": user.role, "status": user.status}
    except ValueError:
        typer.echo("account creation rejected")
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(result, ensure_ascii=False))


@app.command("auth-disable-user")
def auth_disable_user(username: str = typer.Option(..., "--username")) -> None:
    """Disable an account and revoke every live session."""
    try:
        with session_scope() as db:
            user = AuthService().disable_user(db, _find_auth_user(db, username).id)
            result = {"id": user.id, "username": user.username, "status": user.status}
    except UserNotFoundError:
        typer.echo("account not found")
        raise typer.Exit(code=1) from None
    except LastActiveAdminError:
        typer.echo("the last active admin cannot be disabled")
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(result, ensure_ascii=False))


@app.command("auth-reactivate-user")
def auth_reactivate_user(username: str = typer.Option(..., "--username")) -> None:
    """Reactivate an account; old sessions remain revoked."""
    try:
        with session_scope() as db:
            user = AuthService().reactivate_user(db, _find_auth_user(db, username).id)
            result = {"id": user.id, "username": user.username, "status": user.status}
    except UserNotFoundError:
        typer.echo("account not found")
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(result, ensure_ascii=False))


@app.command("auth-reset-password")
def auth_reset_password(username: str = typer.Option(..., "--username")) -> None:
    """Reset a password from a hidden prompt and revoke every live session."""
    password = typer.prompt("New password", hide_input=True, confirmation_prompt=True)
    try:
        with session_scope() as db:
            user = AuthService().reset_user_password(db, _find_auth_user(db, username).id, password=password)
            result = {"id": user.id, "username": user.username, "status": user.status}
    except UserNotFoundError:
        typer.echo("account not found")
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(result, ensure_ascii=False))


@app.command("auth-backfill-legacy-holdings")
def auth_backfill_legacy_holdings(
    username: str = typer.Option(..., "--username"),
    apply: bool = typer.Option(False, "--apply"),
) -> None:
    """Assign NULL-owner portfolio records to one active admin, idempotently."""
    with session_scope() as db:
        user = db.scalar(select(AuthUser).where(AuthUser.username == normalize_identifier(username)))
        if user is None or user.role != "admin" or user.status != "active":
            typer.echo("portfolio owner backfill rejected")
            raise typer.Exit(code=1)
        counts = {
            "holdings": int(db.scalar(select(func.count()).select_from(Holding).where(Holding.user_id.is_(None))) or 0),
            "holding_import_sessions": int(db.scalar(select(func.count()).select_from(HoldingImportSession).where(HoldingImportSession.user_id.is_(None))) or 0),
            "private_report_artifacts": int(
                db.scalar(
                    select(func.count()).select_from(ReportArtifact).where(
                        ReportArtifact.user_id.is_(None),
                        ReportArtifact.metadata_json["scope"].as_string() == "private",
                    )
                )
                or 0
            ),
        }
        if apply:
            db.execute(update(Holding).where(Holding.user_id.is_(None)).values(user_id=user.id))
            db.execute(update(HoldingImportSession).where(HoldingImportSession.user_id.is_(None)).values(user_id=user.id))
            db.execute(
                update(ReportArtifact)
                .where(ReportArtifact.user_id.is_(None), ReportArtifact.metadata_json["scope"].as_string() == "private")
                .values(user_id=user.id)
            )
    typer.echo(json.dumps(counts, ensure_ascii=False))


@app.command("holding-set")
def holding_set(
    ts_code: str,
    username: str | None = typer.Option(None, "--username"),
    shares: float = typer.Option(..., min=0),
    cost_price: float = typer.Option(..., min=0),
    target_weight: float | None = typer.Option(None, min=0, max=1),
    notes: str | None = None,
) -> None:
    settings = get_settings()
    with session_scope() as db:
        user_id = _holding_owner_id(db, auth_enabled=settings.auth_enabled, username=username)
        HoldingService().upsert(
            db,
            user_id=user_id,
            ts_code=ts_code.upper(),
            shares=shares,
            cost_price=cost_price,
            target_weight=target_weight,
            notes=notes,
        )
        result = HoldingService().list(db, user_id=user_id)
    typer.echo(json.dumps(result, ensure_ascii=False, default=str, indent=2))


@app.command("holding-delete")
def holding_delete(ts_code: str, username: str | None = typer.Option(None, "--username")) -> None:
    settings = get_settings()
    with session_scope() as db:
        user_id = _holding_owner_id(db, auth_enabled=settings.auth_enabled, username=username)
        deleted = HoldingService().delete(db, ts_code.upper(), user_id=user_id)
    typer.echo("deleted" if deleted else "not found")


@app.command("snapshot")
def snapshot() -> None:
    with session_scope() as db:
        result = DashboardService().bootstrap(db)
    typer.echo(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    app()

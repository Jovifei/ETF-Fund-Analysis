"""Local deterministic compute and export for local-display-v2 contract."""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import Instrument, MarketContextSnapshot, SectorSnapshot
from app.services.decision_board_service import DecisionBoardService
from app.utils.hashing import stable_hash
from app.workspace.candle_periods import transform_chart
from app.workspace.read_model import chart_data, instrument_detail, overview
from app.workspace.shadow_bundle import digest, make_bundle, timestamp
from app.workspace.shadow_projection import project_chart

CONTRACT_VERSION = "local-display-v2"

ROW_FIELDS_V2 = {
    "ts_code",
    "name",
    "kind",
    "grade",
    "grade_reason",
    "freshness",
    "data_status",
    "price",
    "price_basis",
    "theme_l1",
    "theme_l2",
    "research_only",
    "actionable",
    "forecasts",
    "indicators",
    "returns",
    "return_1d",
    "return_5d",
    "volume",
    "ma",
    "macd",
    "kdj",
    "rsi",
    "td",
    "sector",
    "chan",
    "quote",
    "support_resistance",
}

BAR_FIELDS = {"date", "open", "high", "low", "close", "volume", "amount", "source"}


def local_settings(
    root: Path | str,
    database: Path | str,
    profile: str = "live",
    market_provider: str | None = None,
) -> Settings:
    original_root = Path(root)
    original_database = Path(database)
    if original_root.is_symlink() or original_database.is_symlink():
        raise ValueError("symlink database rejected")
    root_resolved = original_root.resolve()
    db_resolved = original_database.resolve()

    marker_name = ".local-live" if profile == "live" else ".shadow-local"
    if not (root_resolved / marker_name).is_file():
        raise ValueError(f"local ownership marker required: {marker_name}")
    if db_resolved.name != "research.sqlite3":
        raise ValueError("dedicated existing local SQLite database required")
    if (
        root_resolved == root_resolved.parent
        or root_resolved not in db_resolved.parents
        or db_resolved.suffix != ".sqlite3"
        or not db_resolved.exists()
    ):
        raise ValueError("dedicated existing local SQLite database required")

    provider = market_provider or ("akshare" if profile == "live" else "mock")
    if profile == "live" and provider == "mock":
        raise ValueError("live profile rejects mock provider")

    os.environ["WORKSPACE_BRIDGE_ENABLED"] = "false"
    os.environ["WORKSPACE_DAILY_REVIEW_ENABLED"] = "false"

    return Settings(
        _env_file=None,
        app_env="test",
        market_provider=provider,
        allow_mock_fallback=False,
        auto_create_schema=False,
        database_url=f"sqlite:///{db_resolved.as_posix()}",
        auth_enabled=False,
        llm_enabled=False,
        analysis_enabled=False,
        ocr_mode="disabled",
    )


def validate_provider_admission(market_provider: str, profile: str = "live") -> dict[str, Any]:
    if profile == "live" and market_provider == "mock":
        raise ValueError("mock provider not permitted in live profile")

    # Safe admission contract
    admitted = market_provider in {"akshare", "tushare", "composite", "public_composite"}
    token_present = bool(os.environ.get("TUSHARE_TOKEN"))

    return {
        "provider": market_provider,
        "profile": profile,
        "admitted": admitted,
        "license_status": "personal_research_only",
        "quota_status": "metered" if market_provider == "tushare" else "rate_limited",
        "tushare_token_configured": token_present,
        "source_timestamp_quality": "verified_exchange_session",
        "adjustment_policy": "qfq",
        "unit_policy": "volume_hands_amount_yuan",
        "actionable": False,
        "research_only": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def doctor_check(root: Path | str, database: Path | str, profile: str = "live") -> dict[str, Any]:
    r = Path(root)
    d = Path(database)
    root_exists = r.exists() and r.is_dir()
    marker_name = ".local-live" if profile == "live" else ".shadow-local"
    marker_exists = (r / marker_name).is_file()
    db_exists = d.exists() and d.is_file()

    disk_free_gb = 0.0
    if root_exists:
        try:
            total, used, free = shutil.disk_usage(r)
            disk_free_gb = round(free / (1024**3), 2)
        except OSError:
            pass

    provider = "akshare" if profile == "live" else "mock"
    prov_adm = {}
    try:
        prov_adm = validate_provider_admission(provider, profile=profile)
    except Exception as exc:
        prov_adm = {"error": str(exc), "admitted": False}

    return {
        "profile": profile,
        "root_path": str(r),
        "root_exists": root_exists,
        "marker_exists": marker_exists,
        "database_path": str(d),
        "database_exists": db_exists,
        "disk_free_gb": disk_free_gb,
        "disk_sufficient": disk_free_gb >= 2.0,
        "provider_status": prov_adm,
        "contract_version": CONTRACT_VERSION,
    }


def compute_local(settings: Settings, universe: list[str] | None = None) -> list[dict[str, Any]]:
    if settings.market_provider == "mock" and settings.app_env == "local_research":
        raise ValueError("live profile rejects mock provider")

    from app.services.settlement import settled_session
    from app.services.task_service import TaskService

    engine = create_engine(settings.database_url)
    service = TaskService(settings)
    results = []
    try:
        task_names = [
            "refresh_market_context",
            "refresh_bars",
            "refresh_quotes",
            "refresh_sector_snapshots",
            "refresh_indicators",
            "refresh_forecasts",
            "refresh_signals",
            "refresh_decision_board",
        ]

        for task in task_names:
            with Session(engine) as db, db.begin():
                kwargs: dict[str, Any] = {}
                if task == "refresh_bars":
                    kwargs["lookback_days"] = 420
                if universe:
                    kwargs["codes"] = universe
                result = service.run(db, task, **kwargs)
                result = {**result, "task_name": task}
                results.append(result)
                if result.get("status") not in {"succeeded", "partial"}:
                    break
    finally:
        service.close()
        engine.dispose()
    return results


def export_local_v2(
    settings: Settings,
    *,
    sequence: int,
    code_sha: str,
    universe: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as db, db.begin():
            db.connection().exec_driver_sql("BEGIN")
            original = DecisionBoardService(settings).read_latest(db) or {}
            generated = timestamp(original.get("generated_at")) or now

            # 1. Overview part
            view = overview(db, settings, limit=1000)
            rows = []
            for row in view.get("rows", []):
                if universe and row.get("ts_code") not in universe:
                    continue
                row_clean = {k: v for k, v in row.items() if k in ROW_FIELDS_V2}
                row_clean["research_only"] = True
                row_clean["actionable"] = False
                rows.append(row_clean)

            target_trade_date = original.get("target_trade_date") or view.get("target_trade_date") or generated.strftime("%Y-%m-%d")
            overview_part = {
                "rows": rows,
                "snapshot_id": view.get("snapshot_id"),
                "generated_at": view.get("generated_at", generated.isoformat()),
                "target_trade_date": target_trade_date,
                "contains_mock": view.get("contains_mock", False),
                "sector_timing": original.get("sector_timing", {}),
                "actionable": False,
                "research_only": True,
            }

            # 2. Detail & Chart parts
            detail_parts: dict[str, Any] = {}
            chart_parts: dict[str, Any] = {}
            selected_codes = universe or [r["ts_code"] for r in rows[:100]]

            indicator_config = settings.load_strategy().get("indicator", {})
            for code in selected_codes:
                # Detail (Fix-2: provide complete consumer contract for Detail.vue)
                det = instrument_detail(db, settings, code, user_id=None)
                read_as_of_val = (det.get("read_as_of") if det else None) or generated.isoformat()
                if det:
                    detail_parts[code] = {
                        "instrument": det.get("instrument"),
                        "decision": det.get("decision"),
                        "snapshot_id": det.get("snapshot_id"),
                        "decision_time": det.get("decision_time"),
                        "quote": det.get("quote"),
                        "availability": det.get("availability"),
                        "availability_contract_version": det.get("availability_contract_version"),
                        "decision_explanation": det.get("decision_explanation"),
                        "snapshot_issues": det.get("snapshot_issues"),
                        "read_as_of": read_as_of_val,
                        "daily_as_of": det.get("daily_as_of"),
                        "target_trade_date": det.get("target_trade_date"),
                        "history_issue": det.get("history_issue"),
                        "indicator_basis": det.get("indicator_basis"),
                        "indicator_input_hash": det.get("indicator_input_hash"),
                        "chart_series_id": det.get("chart_series_id"),
                        "indicator_values": det.get("indicator_values") or {},
                        "indicator_version": det.get("indicator_version"),
                        "indicator_as_of": det.get("indicator_as_of"),
                        "forecasts": det.get("forecasts") or {},
                        "support_resistance": det.get("support_resistance"),
                        "forecast_scenario": det.get("forecast_scenario"),
                        "holding": None,  # Public bundle strictly isolates private user holdings
                        "actionable": False,
                        "research_only": True,
                    }

                # Chart (1d primary, max 250 bars; ensure as_of matches read_as_of for Detail.vue query match)
                c_data = chart_data(db, settings, code, "1d", 250, as_of=generated) or {}
                if c_data:
                    transformed = transform_chart(c_data, "1d", indicator_config, limit=250, now=generated)
                    projected = project_chart(transformed)
                    projected["as_of"] = read_as_of_val
                    chart_parts[code] = projected

            # 3. Sectors part
            sector_snaps = []
            for s in db.scalars(select(SectorSnapshot).order_by(SectorSnapshot.fetched_at.desc()).limit(100)).all():
                sector_snaps.append({
                    "sector_name": s.sector_name,
                    "board_type": s.board_type,
                    "trade_date": s.trade_date.isoformat() if s.trade_date else None,
                    "pct_change": s.pct_change,
                    "up_count": s.up_count,
                    "down_count": s.down_count,
                    "flat_count": s.flat_count,
                    "total_count": s.total_count,
                })
            sectors_part = {"sectors": sector_snaps}

            # 4. Market context part
            market_context_items = []
            try:
                from app.services.market_context_service import MarketContextService
                mc_rows = MarketContextService(provider=None, settings=settings).latest_view(db)
                for row in mc_rows:
                    r_clean = dict(row)
                    if isinstance(r_clean.get("source_timestamp"), datetime):
                        r_clean["source_timestamp"] = r_clean["source_timestamp"].isoformat()
                    if isinstance(r_clean.get("fetched_at"), datetime):
                        r_clean["fetched_at"] = r_clean["fetched_at"].isoformat()
                    obs = r_clean.get("observation")
                    if isinstance(obs, dict):
                        obs_clean = dict(obs)
                        if isinstance(obs_clean.get("source_timestamp"), datetime):
                            obs_clean["source_timestamp"] = obs_clean["source_timestamp"].isoformat()
                        if isinstance(obs_clean.get("fetched_at"), datetime):
                            obs_clean["fetched_at"] = obs_clean["fetched_at"].isoformat()
                        obs_clean["actionable"] = False
                        r_clean["observation"] = obs_clean
                    r_clean["actionable"] = False
                    market_context_items.append(r_clean)
            except Exception:
                market_context_items = []
            market_context_part = {"items": market_context_items}

            # Construct parts dictionary
            parts = {
                "overview": overview_part,
                "details": detail_parts,
                "charts": chart_parts,
                "sectors": sectors_part,
                "market_context": market_context_part,
            }


            # Parts hashes
            parts_hashes = {k: digest(v) for k, v in parts.items()}

            config_hash = stable_hash(settings.load_strategy())
            manifest = {
                "contract_version": CONTRACT_VERSION,
                "code_sha": code_sha,
                "config_hash": config_hash,
                "sequence": sequence,
                "generated_at": generated.isoformat(),
                "expires_at": (generated + timedelta(hours=2)).isoformat(),
                "actionable": False,
                "data_origin": "local_research",
                "universe": list(selected_codes),
                "parts_hashes": parts_hashes,
            }

            return {
                "manifest": manifest,
                "parts": parts,
            }
    finally:
        engine.dispose()

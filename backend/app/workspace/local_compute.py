"""Local deterministic compute and export for local-display-v2 contract."""
from __future__ import annotations

import os
import json
import re
from math import isfinite
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
from app.workspace.shadow_bundle import canonical, digest, make_bundle, timestamp
from app.workspace.shadow_projection import levels, project_chart, studies

CONTRACT_VERSION = "local-display-v2"
ADMISSION_POLICY_VERSION = "private-research-execution-v1"
EXPORT_PROJECTION_VERSION = "local-display-projection-v1"
EXPORT_MAX_BYTES = 16 * 1024 * 1024
OPTIONAL_TASK_PARTS = {"refresh_market_context": "market_context", "refresh_sector_snapshots": "sectors"}

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
    "entry_exit_ref",
    "theme_relative_strength",
}

BAR_FIELDS = {"date", "open", "high", "low", "close", "volume", "amount", "source"}


def _display_level(value):
    if type(value) in (int, float):
        if not isfinite(value):
            raise ValueError("non-finite display support level")
        return value
    projected = levels(value)
    if projected is not None:
        projected.update({key: value[key] for key in ("zone_low", "zone_high") if key in value})
    return projected


def _display_sr(value):
    if value is None:
        return None
    def study_level(item):
        item = _display_level(item)
        if type(item) in (int, float):
            return {"price": item}
        return item
    normalized = {**value, "levels": [study_level(item) for item in value.get("levels", [])]}
    for key in ("nearest_support", "nearest_resistance"):
        normalized[key] = study_level(value.get(key))
    projected = studies(normalized)
    projected["levels"] = [_display_level(item) for item in value.get("levels", [])]
    for key in ("nearest_support", "nearest_resistance"):
        projected[key] = _display_level(value.get(key))
    metadata = ("source_as_of_date", "snapshot_as_of_date", "as_of_date", "computed_at", "computed_by",
                "version", "indicator_version", "input_hash", "config_hash", "interval", "price_basis",
                "price_basis_id", "source", "evidence_time", "source_time", "snapshot_id", "method_version",
                "revision_id", "snapshot_source", "generated_at")
    projected.update({key: value[key] for key in metadata if key in value})
    return projected


def _display_row(row, *, history_source=None):
    if row is None:
        return None
    projected = {key: value for key, value in row.items() if key in ROW_FIELDS_V2}
    projected.update(research_only=True, actionable=False)
    projected["support_resistance"] = _display_sr(row.get("support_resistance"))
    history = (history_source or row).get("history") or []
    confirmed = [item for item in history if isinstance(item, dict)
                 and not any(item.get(flag) for flag in ("is_forecast", "is_provisional", "not_actual", "is_partial"))]
    projected["history"] = [{key: value for key, value in confirmed[-1].items()
                             if key in BAR_FIELDS | {"is_forecast", "is_provisional", "adjust"}}] if confirmed else []
    return projected


def _checked_export(bundle):
    if len(canonical(bundle)) > EXPORT_MAX_BYTES:
        raise ValueError("producer export budget exceeded (canonical 16 MiB); no scope or bar truncation applied")
    return bundle


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
    if any((root_resolved / child).is_symlink() for child in (marker_name, "outbox", "receipts", "config")):
        raise ValueError("symlink local output/config path rejected")
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
        workspace_research_source="database",
        scheduler_enabled=False,
    )


def load_local_config(root: Path, config: Path | None = None) -> dict:
    path = config or root / "config" / "live.json"
    if not path.is_file() or path.is_symlink():
        raise ValueError("local config file required")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise ValueError("invalid local config JSON") from None
    universe = value.get("universe") if isinstance(value, dict) else None
    if (not isinstance(universe, list) or not universe
            or any(not isinstance(code, str) or not re.fullmatch(r"\d{6}\.(SH|SZ)", code) for code in universe)
            or len(set(universe)) != len(universe)):
        raise ValueError("config requires a nonempty unique ETF universe")
    return value


def validate_provider_admission(
    market_provider: str, profile: str = "live", *, evidence: dict | None = None,
    purpose: str = "export", now: datetime | None = None, private_research: bool = False,
) -> dict[str, Any]:
    if profile == "live" and market_provider == "mock":
        raise ValueError("mock provider not permitted in live profile")

    if purpose not in {"compute", "export"}:
        raise ValueError("unknown admission purpose")
    now = now or datetime.now(timezone.utc)
    evidence = evidence if isinstance(evidence, dict) else {}
    issues = []
    def explicitly_restricted(value):
        if isinstance(value, dict):
            return any((key in {"status", "license_status"} and isinstance(item, str)
                        and item.strip().upper() in {"DENIED", "REVOKED", "EXPIRED"})
                       or explicitly_restricted(item) for key, item in value.items())
        if isinstance(value, list):
            return any(explicitly_restricted(item) for item in value)
        return False
    restricted = explicitly_restricted(evidence)
    if evidence.get("schema") != "provider-admission-evidence-v1" or evidence.get("provider") != market_provider:
        issues.append("provider_evidence_missing_or_mismatched")
    rows = evidence.get("interfaces") or []
    rows = rows if isinstance(rows, list) else []
    by_name = {r.get("name"): r for r in rows if isinstance(r, dict)}
    if len(by_name) != len(rows):
        issues.append("invalid_or_duplicate_interfaces")
    for name in ("daily_bars", "quotes", "sector_snapshots", "market_context"):
        row = by_name.get(name, {})
        try:
            expiry = timestamp(row.get("valid_until"))
        except ValueError:
            expiry = None
        if expiry is None or expiry <= now:
            issues.append(f"{name}:evidence_expired_or_missing")
        if expiry is not None and expiry <= now:
            restricted = True
        for permission in (("acquire", "store", "display") if purpose == "export" else ("acquire", "store")):
            item = row.get(permission) or {}
            if (not isinstance(item, dict) or item.get("status") != "VERIFIED"
                    or item.get("evidence_type") != "upstream_terms_or_license"
                    or not isinstance(item.get("evidence_ref"), str) or not item["evidence_ref"].strip()
                    or item["evidence_ref"].lower().startswith("owner-approval:")):
                issues.append(f"{name}:{permission}_UNKNOWN")
        if purpose == "export":
            units = row.get("units") or {}
            adjustment = row.get("adjustment_basis") or {}
            source_time = row.get("source_timestamp_quality") or {}
            if not (isinstance(units, dict) and units.get("volume") == "shares"
                    and units.get("amount") == "CNY" and units.get("return") == "fraction"
                    and units.get("evidence_ref")):
                issues.append(f"{name}:units_UNKNOWN")
            if not (isinstance(adjustment, dict) and adjustment.get("value") in {"raw", "qfq"}
                    and adjustment.get("evidence_ref")):
                issues.append(f"{name}:adjustment_UNKNOWN")
            if not (isinstance(source_time, dict) and source_time.get("status") == "VERIFIED"
                    and source_time.get("evidence_ref")):
                issues.append(f"{name}:source_time_UNKNOWN")
    admitted = not issues and market_provider != "mock" and not restricted and not private_research
    owner_scope = (private_research is True and profile == "live"
                   and market_provider in {"public_composite", "akshare"} and not restricted)
    return {
        "provider": market_provider,
        "profile": profile,
        "admitted": admitted,
        "operation_permitted": admitted or owner_scope,
        "usage_scope": "owner_private_research" if owner_scope else "documented_provider_use",
        "admission_policy_version": ADMISSION_POLICY_VERSION,
        "source_qualification": "UNKNOWN",
        "restrictions_present": restricted,
        "license_status": "evidence_verified" if admitted else "UNKNOWN",
        "source_timestamp_quality": "evidence_verified" if admitted and purpose == "export" else "UNKNOWN",
        "purpose": purpose,
        "issues": issues,
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


def compute_local(settings: Settings, universe: list[str] | None = None, *, admission: dict | None = None,
                  private_research: bool = False) -> list[dict[str, Any]]:
    if settings.market_provider == "mock" and settings.app_env == "local_research":
        raise ValueError("live profile rejects mock provider")

    if settings.market_provider != "mock" and not validate_provider_admission(
        settings.market_provider, evidence=admission, purpose="compute", private_research=private_research
    )["operation_permitted"]:
        raise ValueError("provider acquisition/storage admission UNKNOWN")
    from app.services.task_service import TaskService

    if private_research:
        settings = settings.model_copy(update={"tushare_token": "", "ftshare_enabled": False})
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
            required = task not in OPTIONAL_TASK_PARTS
            try:
                with Session(engine) as db, db.begin():
                    kwargs: dict[str, Any] = {}
                    if task == "refresh_bars":
                        kwargs["lookback_days"] = 420
                    if universe:
                        kwargs["codes"] = universe
                    result = service.run(db, task, **kwargs)
            except Exception as exc:
                if required:
                    raise
                result = {"status": "unavailable", "error_type": type(exc).__name__}
            result = {**result, "task_name": task, "required": required}
            if not required and result.get("status") != "succeeded":
                result["availability"] = "unavailable"
            results.append(result)
            if required and result.get("status") != "succeeded":
                break
    finally:
        service.close()
        engine.dispose()
    return results


from contextlib import contextmanager


@contextmanager
def local_session(settings: Settings):
    """Short-lived session on the owned local research DB only."""
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as db:
            yield db
    finally:
        engine.dispose()


def compute_board_only(settings: Settings, universe: list[str] | None = None) -> list[dict[str, Any]]:
    """Local refresh-then-sync target path: rebuild only the decision board from
    stored local rows (no market collection), so a READ_MODEL change can be
    published without any cloud-side compute."""
    from app.services.task_service import TaskService

    if getattr(settings, "workspace_research_source", "database") != "database":
        raise ValueError("local refresh requires the local database research source")
    engine = create_engine(settings.database_url)
    service = TaskService(settings)
    try:
        with Session(engine) as db, db.begin():
            kwargs: dict[str, Any] = {"codes": universe} if universe else {}
            result = service.run(db, "refresh_decision_board", **kwargs)
            return [{**result, "task_name": "refresh_decision_board"}]
    finally:
        service.close()
        engine.dispose()


def export_local_v2(
    settings: Settings,
    *,
    sequence: int,
    code_sha: str,
    universe: list[str] | None = None,
    now: datetime | None = None,
    admission: dict | None = None,
    private_research: bool = False,
    unavailable_parts: list[str] | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if settings.market_provider != "mock" and not validate_provider_admission(
        settings.market_provider, evidence=admission, now=now, private_research=private_research
    )["operation_permitted"]:
        raise ValueError("provider display/quality admission UNKNOWN")
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as db, db.begin():
            db.connection().exec_driver_sql("BEGIN")
            original = DecisionBoardService(settings).read_latest(db) or {}
            generated = timestamp(original.get("generated_at")) or now

            # 1. Overview part
            view = overview(db, settings, limit=1000)
            original_rows = {row["ts_code"]: row for row in original.get("rows", [])
                             if isinstance(row, dict) and row.get("ts_code")}
            rows = []
            for row in view.get("rows", []):
                if universe and row.get("ts_code") not in universe:
                    continue
                row_clean = _display_row(row, history_source=original_rows.get(row.get("ts_code")))
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
            chart_periods: dict[str, Any] = {}
            selected_codes = universe or [r["ts_code"] for r in rows[:100]]

            indicator_config = settings.load_strategy().get("indicator", {})
            for code in selected_codes:
                # Detail (Fix-2: provide complete consumer contract for Detail.vue)
                det = instrument_detail(db, settings, code, user_id=None, as_of=generated)
                read_as_of_val = generated.isoformat()

                if det:
                    detail_parts[code] = {

                        "instrument": det.get("instrument"),
                        "decision": _display_row(det.get("decision")),
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
                        "support_resistance": _display_sr(det.get("support_resistance")),
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
                    chart_periods[code] = {}
                    for period in ("1w", "1mo"):
                        periodic = project_chart(transform_chart(c_data, period, indicator_config, limit=250, now=generated))
                        periodic["as_of"] = read_as_of_val
                        periodic["interval"] = period
                        periodic["unsupported_intervals"] = ["5m", "15m"]
                        chart_periods[code][period] = periodic

            # 3. Sectors part
            unavailable = set(unavailable_parts or ())
            sector_snaps = []
            try:
                with db.begin_nested():
                    sector_rows = [] if "sectors" in unavailable else db.scalars(
                        select(SectorSnapshot).order_by(SectorSnapshot.fetched_at.desc()).limit(100)).all()
            except Exception:
                sector_rows = []
                unavailable.add("sectors")
            for s in sector_rows:
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

            if universe and (set(selected_codes) != {r["ts_code"] for r in rows}
                    or set(detail_parts) != set(selected_codes) or set(chart_parts) != set(selected_codes)
                    or any(not chart_parts[code].get("bars") for code in selected_codes)):
                raise ValueError("required universe display coverage incomplete")

            # 4. Market context part
            market_context_items = []
            try:
                from app.services.market_context_service import MarketContextService
                with db.begin_nested():
                    mc_rows = [] if "market_context" in unavailable else MarketContextService(provider=None, settings=settings).latest_view(db)
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
                unavailable.add("market_context")
            market_context_part = {"items": market_context_items}
            if "sectors" in unavailable:
                sectors_part = {"sectors": [], "availability": "unavailable", "reason": "optional_refresh_failed"}
            if "market_context" in unavailable:
                market_context_part = {"items": [], "availability": "unavailable", "reason": "optional_refresh_failed"}

            # Construct parts dictionary
            parts = {
                "overview": overview_part,
                "details": detail_parts,
                "charts": chart_parts,
                "sectors": sectors_part,
                "market_context": market_context_part,
                "chart_periods": chart_periods,
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
                "research_only": True,
                "universe": list(selected_codes),
                "parts_hashes": parts_hashes,
                "usage_scope": "owner_private_research" if private_research else "documented_provider_use",
                "source_qualification": "UNKNOWN",
                "license_status": "UNKNOWN",
                "calibration_status": "not_calibrated",
                "admission_policy_version": ADMISSION_POLICY_VERSION,
                "export_projection_version": EXPORT_PROJECTION_VERSION,
            }

            if private_research:
                def unqualified_copy(value):
                    if isinstance(value, dict):
                        return {key: "not_calibrated" if key == "calibration_status" else unqualified_copy(item)
                                for key, item in value.items()}
                    if isinstance(value, list):
                        return [unqualified_copy(item) for item in value]
                    return value
                parts = unqualified_copy(parts)
                manifest["parts_hashes"] = {key: digest(value) for key, value in parts.items()}
            return _checked_export({
                "manifest": manifest,
                "parts": parts,
            })
    finally:
        engine.dispose()

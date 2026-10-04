"""校准候选档案服务：从 validate_forecasts 报告生成候选 Profile。

治理边界（AGENTS.md / ROADMAP_V070）：
* 本服务只创建 status=candidate 的 CalibrationProfile；
* 批准（approved）只能由人工通过显式 API/CLI 调用发生，且要求：
  model_version / feature_schema_version / config_hash 与当前 strategy 一致、
  样本数与覆盖率门槛达标、Holdout 未显著失效、留下批准人记录；
* 无论候选多少、状态如何，本服务绝不修改 ForecastSnapshot.calibration_status；
  calibrated 状态的提升是另一个人工治理流程，不在本任务内。
"""
from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import CalibrationProfile, ReportArtifact
from app.services.event_service import emit_event
from app.utils.hashing import stable_hash
from app.utils.reproducibility import current_git_commit

logger = logging.getLogger(__name__)

# 门槛默认值（strategy["forecast"]["calibration_gates"] 可覆盖；有意不改
# config/strategy.json，以免改变已落库快照的 config_hash 语义）。
DEFAULT_GATES: dict[str, Any] = {
    "minimum_instruments": 5,
    "minimum_total_samples": 200,
    "minimum_directional_accuracy": 0.50,
    "maximum_brier_score": 0.30,
    "minimum_interval_80_coverage": 0.70,
    "maximum_quantile_crossing_rate": 0.10,
    "maximum_touch_brier": 0.35,
}

ALLOWED_TRANSITIONS = {
    "candidate": {"approved", "rejected"},
    "approved": set(),
    "rejected": set(),
}


class CalibrationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.strategy = self.settings.load_strategy()
        gates = self.strategy.get("forecast", {}).get("calibration_gates")
        self.gates = dict(DEFAULT_GATES, **gates) if isinstance(gates, dict) else dict(DEFAULT_GATES)

    # ------------------------------------------------------------------ create

    def create_candidate(self, db: Session, run_id: str | None = None) -> dict[str, Any]:
        """从最新 forecast_validation 报告生成候选 Profile（幂等：同一验证哈希只建一条）。"""
        run_id = run_id or uuid.uuid4().hex
        artifact = db.scalars(
            select(ReportArtifact)
            .where(ReportArtifact.report_type == "forecast_validation")
            .order_by(ReportArtifact.as_of_time.desc(), ReportArtifact.id.desc())
            .limit(1)
        ).first()
        if artifact is None:
            return {
                "run_id": run_id,
                "status": "skipped",
                "reason": "no forecast_validation report found; run validate_forecasts first",
            }

        existing = db.scalars(
            select(CalibrationProfile).where(
                CalibrationProfile.validation_content_hash == artifact.content_hash
            )
        ).first()
        if existing is not None:
            return {
                "run_id": run_id,
                "status": "duplicate",
                "profile_id": existing.id,
                "reason": "candidate already exists for this validation content hash",
            }

        try:
            payload = _artifact_payload(artifact)
        except (OSError, ValueError, TypeError) as exc:
            return {
                "run_id": run_id,
                "status": "skipped",
                "reason": f"validation report unreadable: {type(exc).__name__}",
            }

        model_version = str(payload.get("model_version") or "")
        feature_schema_version = str(payload.get("feature_schema_version") or "")
        config_hash = str(payload.get("config_hash") or "")
        summary = self._summarize(payload)
        summary["validation_content_hash_matches"] = stable_hash(payload) == artifact.content_hash
        gate_results = self._evaluate_gates(summary)

        profile = CalibrationProfile(
            status="candidate",
            model_version=model_version,
            feature_schema_version=feature_schema_version,
            config_hash=config_hash,
            validation_run_id=str(payload.get("run_id") or ""),
            validation_content_hash=artifact.content_hash,
            instrument_count=int(summary.get("instrument_count") or 0),
            sample_count=int(summary.get("total_samples") or 0),
            gate_results=gate_results,
            summary_metrics=summary,
        )
        db.add(profile)
        db.flush()
        emit_event(
            db,
            "forecast.calibration.candidate_created",
            {"run_id": run_id, "profile_id": profile.id},
        )
        logger.info("calibration candidate created: profile=%s validation=%s", profile.id, artifact.content_hash[:10])
        return {
            "run_id": run_id,
            "status": "candidate_created",
            "profile_id": profile.id,
            "gates_passed": gate_results["all_passed"],
            "gate_results": gate_results,
            "summary": summary,
        }

    # ----------------------------------------------------------------- approve

    def decide(self, db: Session, profile_id: int, decision: str, approved_by: str) -> dict[str, Any]:
        """人工批准/拒绝。批准前核对版本一致性与门槛；拒绝只记录。"""
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be 'approved' or 'rejected'")
        if not approved_by or not approved_by.strip():
            raise ValueError("approved_by is required for the audit trail")

        profile = db.get(CalibrationProfile, profile_id)
        if profile is None:
            raise LookupError(f"calibration profile {profile_id} not found")
        if decision not in ALLOWED_TRANSITIONS.get(profile.status, set()):
            raise ValueError(f"transition {profile.status} -> {decision} is not allowed")

        if decision == "rejected":
            profile.status = "rejected"
            profile.approved_by = approved_by.strip()
            profile.approved_at = datetime.now(self.settings.timezone)
            db.flush()
            return {"profile_id": profile_id, "status": "rejected"}

        # 批准前的核对单
        checks = self._approval_checks(db, profile)
        if not checks["all_passed"]:
            raise ValueError(
                "approval blocked by failed checks: "
                + ", ".join(name for name, ok in checks["items"].items() if not ok)
            )
        profile.status = "approved"
        profile.approved_by = approved_by.strip()
        profile.approved_at = datetime.now(self.settings.timezone)
        db.flush()
        emit_event(
            db,
            "forecast.calibration.approved",
            {"profile_id": profile.id, "approved_by": profile.approved_by},
        )
        return {"profile_id": profile_id, "status": "approved", "checks": checks}

    def list_profiles(self, db: Session) -> list[dict[str, Any]]:
        rows = db.scalars(
            select(CalibrationProfile).order_by(CalibrationProfile.id.desc())
        ).all()
        return [
            {
                "id": row.id,
                "status": row.status,
                "model_version": row.model_version,
                "feature_schema_version": row.feature_schema_version,
                "config_hash": row.config_hash,
                "validation_run_id": row.validation_run_id,
                "instrument_count": row.instrument_count,
                "sample_count": row.sample_count,
                "gate_results": row.gate_results,
                "approved_by": row.approved_by,
                "approved_at": row.approved_at.isoformat() if row.approved_at else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]

    # ------------------------------------------------------------------ internals

    def _summarize(self, payload: dict[str, Any]) -> dict[str, Any]:
        instruments = payload.get("instruments") or []
        ok_rows = [item for item in instruments if isinstance(item, dict) and item.get("status") == "ok"]
        total_samples = 0
        directionals: list[float] = []
        briers: list[float] = []
        coverages: list[float] = []
        crossings: list[float] = []
        touch_briers: list[float] = []
        per_horizon: dict[str, dict[str, list[float]]] = {}
        horizons_present: set[str] = set()
        nonfinite_metric_count = 0

        def finite_metric(value: Any) -> float | None:
            nonlocal nonfinite_metric_count
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            number = float(value)
            if not math.isfinite(number):
                nonfinite_metric_count += 1
                return None
            return number

        for row in ok_rows:
            for horizon, metrics in (row.get("horizons") or {}).items():
                if not isinstance(metrics, dict):
                    continue
                horizons_present.add(str(horizon))
                samples = int(metrics.get("sample_count") or 0)
                total_samples += max(0, samples)
                bucket = per_horizon.setdefault(str(horizon), {})
                for key, store in (
                    ("directional_accuracy", directionals),
                    ("brier_score", briers),
                    ("interval_80_coverage", coverages),
                    ("quantile_crossing_rate", crossings),
                ):
                    number = finite_metric(metrics.get(key))
                    if number is not None:
                        store.append(number)
                        bucket.setdefault(key, []).append(number)
                for key in ("support_touch_brier", "resistance_touch_brier"):
                    number = finite_metric(metrics.get(key))
                    if number is not None:
                        touch_briers.append(number)

        def mean(values: list[float]) -> float | None:
            return round(sum(values) / len(values), 4) if values else None

        contract = payload.get("input_contract") if isinstance(payload.get("input_contract"), dict) else {}
        summary: dict[str, Any] = {
            "instrument_count": len(ok_rows),
            "total_samples": total_samples,
            "mean_directional_accuracy": mean(directionals),
            "mean_brier_score": mean(briers),
            "mean_interval_80_coverage": mean(coverages),
            "mean_quantile_crossing_rate": mean(crossings),
            "mean_touch_brier": mean(touch_briers),
            "per_horizon": {
                horizon: {
                    "mean_directional_accuracy": mean(vals.get("directional_accuracy", [])),
                    "mean_interval_80_coverage": mean(vals.get("interval_80_coverage", [])),
                }
                for horizon, vals in sorted(per_horizon.items())
            },
            "horizons_present": sorted(horizons_present),
            "horizon_contract": [str(value) for value in (payload.get("horizon_contract") or [])],
            "nonfinite_metric_count": nonfinite_metric_count,
            "independent_holdout": contract.get("independent_holdout") is True,
            "source": str(contract.get("source") or ""),
            "pit_qualified": contract.get("pit_qualified") is True,
            "report_config_hash": str(payload.get("config_hash") or ""),
            "report_git_commit_sha": str(payload.get("git_commit_sha") or ""),
            "input_lineage_hash": str(payload.get("input_lineage_hash") or ""),
        }
        return summary

    def _evaluate_gates(self, summary: dict[str, Any]) -> dict[str, Any]:
        def gate(name: str, actual: Any, minimum: float | None = None, maximum: float | None = None) -> dict:
            if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not math.isfinite(float(actual)):
                return {"name": name, "passed": False, "actual": actual,
                        "threshold": f"min={minimum} max={maximum}", "reason": "metric missing or non-finite"}
            number = float(actual)
            passed = True
            if minimum is not None and number < minimum:
                passed = False
            if maximum is not None and number > maximum:
                passed = False
            return {"name": name, "passed": passed, "actual": number,
                    "threshold": f"min={minimum} max={maximum}"}

        expected_horizons = {str(int(value)) for value in self.strategy["forecast"].get("horizons", (1, 3, 5, 10))}
        actual_horizons = set(summary.get("horizons_present") or [])
        items = {
            "instrument_count": gate("instrument_count", summary.get("instrument_count"),
                                     minimum=self.gates["minimum_instruments"])["passed"],
            "total_samples": gate("total_samples", summary.get("total_samples"),
                                  minimum=self.gates["minimum_total_samples"])["passed"],
            "directional_accuracy": gate("mean_directional_accuracy",
                                         summary.get("mean_directional_accuracy"),
                                         minimum=self.gates["minimum_directional_accuracy"])["passed"],
            "brier_score": gate("mean_brier_score", summary.get("mean_brier_score"),
                                maximum=self.gates["maximum_brier_score"])["passed"],
            "interval_80_coverage": gate("mean_interval_80_coverage",
                                         summary.get("mean_interval_80_coverage"),
                                         minimum=self.gates["minimum_interval_80_coverage"])["passed"],
            "quantile_crossing_rate": gate("mean_quantile_crossing_rate",
                                           summary.get("mean_quantile_crossing_rate"),
                                           maximum=self.gates["maximum_quantile_crossing_rate"])["passed"],
            "touch_brier": gate("mean_touch_brier", summary.get("mean_touch_brier"),
                                maximum=self.gates["maximum_touch_brier"])["passed"],
            "finite_metrics": summary.get("nonfinite_metric_count") == 0,
            "all_formal_horizons": actual_horizons == expected_horizons
                and set(summary.get("horizon_contract") or []) == expected_horizons,
            "independent_holdout": summary.get("independent_holdout") is True,
            "source_non_mock": bool(summary.get("source")) and str(summary.get("source")).lower() != "mock",
            "pit_qualified": summary.get("pit_qualified") is True,
            "report_config_hash_present": bool(summary.get("report_config_hash")),
            "report_git_commit_present": bool(summary.get("report_git_commit_sha")),
            "input_lineage_hash_present": bool(summary.get("input_lineage_hash")),
            "validation_content_hash_matches": summary.get("validation_content_hash_matches") is True,
        }
        return {"all_passed": all(items.values()), "items": items}

    def _approval_checks(self, db: Session, profile: CalibrationProfile) -> dict[str, Any]:
        artifact = db.scalars(
            select(ReportArtifact).where(ReportArtifact.content_hash == profile.validation_content_hash)
        ).first()
        if artifact is None:
            return {"all_passed": False, "items": {"validation_artifact_present": False}}
        try:
            payload = _artifact_payload(artifact)
        except (OSError, ValueError, TypeError):
            return {"all_passed": False, "items": {"validation_artifact_readable": False}}

        summary = self._summarize(payload)
        content_matches = stable_hash(payload) == artifact.content_hash == profile.validation_content_hash
        summary["validation_content_hash_matches"] = content_matches
        recomputed_gates = self._evaluate_gates(summary)
        current_model = self.strategy["forecast_version"]
        current_schema = self.strategy.get("feature_schema_version", "")
        current_config_hash = stable_hash(self.strategy)
        report_model = str(payload.get("model_version") or "")
        report_schema = str(payload.get("feature_schema_version") or "")
        report_config = str(payload.get("config_hash") or "")
        report_git = str(payload.get("git_commit_sha") or "")
        items = {
            "validation_artifact_present": True,
            "validation_content_hash_matches": content_matches,
            "model_version_matches_report": profile.model_version == report_model,
            "model_version_matches_current": profile.model_version == current_model,
            "feature_schema_matches_report": profile.feature_schema_version == report_schema,
            "feature_schema_matches_current": profile.feature_schema_version == current_schema,
            "config_hash_matches_report": profile.config_hash == report_config,
            "config_hash_matches_current": profile.config_hash == current_config_hash,
            "report_git_commit_matches_current": bool(report_git) and report_git == current_git_commit(),
            "gates_recomputed": bool(recomputed_gates.get("all_passed")),
            "stored_gates_match_recomputed": stable_hash(profile.gate_results or {}) == stable_hash(recomputed_gates),
            "sample_count_matches_report": profile.sample_count == int(summary.get("total_samples") or 0),
            "sample_count_sufficient": profile.sample_count >= self.gates["minimum_total_samples"],
        }
        return {"all_passed": all(items.values()), "items": items}

def _artifact_payload(artifact: ReportArtifact) -> dict[str, Any]:
    text = (
        artifact.file_path_content
        if hasattr(artifact, "file_path_content")
        else _read_report(artifact.file_path)
    )
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("validation report must be a JSON object")
    return payload


def _read_report(file_path: str) -> str:
    with open(file_path, encoding="utf-8") as handle:
        return handle.read()

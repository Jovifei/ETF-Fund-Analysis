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

import logging
import math
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import CalibrationProfile, ReportArtifact
from app.services.event_service import emit_event
from app.services.report_artifact_contract import (
    latest_system_report,
    read_system_json_report,
)
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

# A validation report cannot make itself calibration-eligible by declaring
# holdout/PIT booleans. A future validator must be independently audited and
# explicitly allowlisted here in source before any approval can pass.
CALIBRATION_ELIGIBLE_VALIDATION_CONTRACTS: frozenset[str] = frozenset()

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
        artifact = latest_system_report(db, "forecast_validation")
        if artifact is None:
            return {
                "run_id": run_id,
                "status": "skipped",
                "reason": "no forecast_validation report found; run validate_forecasts first",
            }

        try:
            payload = read_system_json_report(
                artifact, self.settings, expected_type="forecast_validation"
            )
        except (OSError, ValueError, TypeError) as exc:
            return {
                "run_id": run_id,
                "status": "skipped",
                "reason": f"validation report unreadable: {type(exc).__name__}",
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
        global_values: dict[str, list[float]] = {
            "directional_accuracy": [],
            "brier_score": [],
            "interval_80_coverage": [],
            "quantile_crossing_rate": [],
            "touch_brier": [],
        }
        horizon_rows: dict[str, dict[str, Any]] = {}
        invalid_metric_count = 0

        def probability_metric(value: Any) -> float | None:
            nonlocal invalid_metric_count
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                invalid_metric_count += 1
                return None
            number = float(value)
            if not math.isfinite(number) or number < 0.0 or number > 1.0:
                invalid_metric_count += 1
                return None
            return number

        for row in ok_rows:
            horizons = row.get("horizons") if isinstance(row.get("horizons"), dict) else {}
            for horizon, metrics in horizons.items():
                if not isinstance(metrics, dict):
                    invalid_metric_count += 1
                    continue
                key = str(horizon)
                bucket = horizon_rows.setdefault(key, {
                    "instrument_count": 0,
                    "sample_count": 0,
                    "invalid_metric_count": 0,
                    "values": {
                        "directional_accuracy": [],
                        "brier_score": [],
                        "interval_80_coverage": [],
                        "quantile_crossing_rate": [],
                        "touch_brier": [],
                    },
                })
                sample_value = metrics.get("sample_count")
                if isinstance(sample_value, bool) or not isinstance(sample_value, int) or sample_value < 0:
                    bucket["invalid_metric_count"] += 1
                    invalid_metric_count += 1
                    samples = 0
                else:
                    samples = sample_value
                bucket["sample_count"] += samples
                total_samples += samples

                row_valid = samples > 0
                for metric in ("directional_accuracy", "brier_score", "interval_80_coverage", "quantile_crossing_rate"):
                    before = invalid_metric_count
                    number = probability_metric(metrics.get(metric))
                    if invalid_metric_count != before:
                        bucket["invalid_metric_count"] += 1
                        row_valid = False
                    elif number is not None:
                        bucket["values"][metric].append(number)
                        global_values[metric].append(number)

                touch_values: list[float] = []
                for metric in ("support_touch_brier", "resistance_touch_brier"):
                    before = invalid_metric_count
                    number = probability_metric(metrics.get(metric))
                    if invalid_metric_count != before:
                        bucket["invalid_metric_count"] += 1
                        row_valid = False
                    elif number is not None:
                        touch_values.append(number)
                        global_values["touch_brier"].append(number)
                if touch_values:
                    bucket["values"]["touch_brier"].extend(touch_values)
                else:
                    row_valid = False
                if row_valid:
                    bucket["instrument_count"] += 1

        def mean(values: list[float]) -> float | None:
            return round(sum(values) / len(values), 4) if values else None

        per_horizon: dict[str, dict[str, Any]] = {}
        for horizon, bucket in sorted(horizon_rows.items(), key=lambda item: int(item[0]) if item[0].isdigit() else 10**9):
            values = bucket["values"]
            per_horizon[horizon] = {
                "instrument_count": bucket["instrument_count"],
                "sample_count": bucket["sample_count"],
                "invalid_metric_count": bucket["invalid_metric_count"],
                "mean_directional_accuracy": mean(values["directional_accuracy"]),
                "mean_brier_score": mean(values["brier_score"]),
                "mean_interval_80_coverage": mean(values["interval_80_coverage"]),
                "mean_quantile_crossing_rate": mean(values["quantile_crossing_rate"]),
                "mean_touch_brier": mean(values["touch_brier"]),
            }

        contract = payload.get("input_contract") if isinstance(payload.get("input_contract"), dict) else {}
        validation_contract_version = str(payload.get("validation_contract_version") or "")
        source = str(contract.get("source") or "").strip().lower()
        lineage = str(payload.get("input_lineage_hash") or "").strip().lower()
        summary: dict[str, Any] = {
            "instrument_count": len(ok_rows),
            "total_samples": total_samples,
            "mean_directional_accuracy": mean(global_values["directional_accuracy"]),
            "mean_brier_score": mean(global_values["brier_score"]),
            "mean_interval_80_coverage": mean(global_values["interval_80_coverage"]),
            "mean_quantile_crossing_rate": mean(global_values["quantile_crossing_rate"]),
            "mean_touch_brier": mean(global_values["touch_brier"]),
            "per_horizon": per_horizon,
            "horizons_present": sorted(per_horizon),
            "horizon_contract": [str(value) for value in (payload.get("horizon_contract") or [])],
            "invalid_metric_count": invalid_metric_count,
            "validation_contract_version": validation_contract_version,
            "validation_contract_eligible": validation_contract_version in CALIBRATION_ELIGIBLE_VALIDATION_CONTRACTS,
            "declared_independent_holdout": contract.get("independent_holdout") is True,
            "declared_pit_qualified": contract.get("pit_qualified") is True,
            "declared_calibration_eligible": contract.get("calibration_eligible") is True,
            "source": source,
            "source_non_synthetic": bool(source) and not any(
                marker in source for marker in ("mock", "fixture", "demo", "test", "synthetic")
            ),
            "report_config_hash": str(payload.get("config_hash") or ""),
            "report_git_commit_sha": str(payload.get("git_commit_sha") or ""),
            "input_lineage_hash": lineage,
            "input_lineage_digest_valid": bool(re.fullmatch(r"[0-9a-f]{64}", lineage)),
        }
        return summary

    def _evaluate_gates(self, summary: dict[str, Any]) -> dict[str, Any]:
        def gate(actual: Any, minimum: float | None = None, maximum: float | None = None) -> bool:
            if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not math.isfinite(float(actual)):
                return False
            number = float(actual)
            if minimum is not None and number < minimum:
                return False
            if maximum is not None and number > maximum:
                return False
            return True

        expected_horizons = {str(int(value)) for value in self.strategy["forecast"].get("horizons", (1, 3, 5, 10))}
        actual_horizons = set(summary.get("per_horizon") or {})
        horizon_count = max(1, len(expected_horizons))
        minimum_per_horizon = max(1, math.ceil(self.gates["minimum_total_samples"] / horizon_count))
        horizon_gates: dict[str, dict[str, Any]] = {}
        for horizon in sorted(expected_horizons, key=int):
            item = (summary.get("per_horizon") or {}).get(horizon) or {}
            checks = {
                "instrument_count": gate(item.get("instrument_count"), minimum=self.gates["minimum_instruments"]),
                "sample_count": gate(item.get("sample_count"), minimum=minimum_per_horizon),
                "metrics_valid": item.get("invalid_metric_count") == 0,
                "directional_accuracy": gate(item.get("mean_directional_accuracy"),
                                             minimum=self.gates["minimum_directional_accuracy"], maximum=1.0),
                "brier_score": gate(item.get("mean_brier_score"), minimum=0.0,
                                    maximum=self.gates["maximum_brier_score"]),
                "interval_80_coverage": gate(item.get("mean_interval_80_coverage"),
                                             minimum=self.gates["minimum_interval_80_coverage"], maximum=1.0),
                "quantile_crossing_rate": gate(item.get("mean_quantile_crossing_rate"), minimum=0.0,
                                               maximum=self.gates["maximum_quantile_crossing_rate"]),
                "touch_brier": gate(item.get("mean_touch_brier"), minimum=0.0,
                                    maximum=self.gates["maximum_touch_brier"]),
            }
            horizon_gates[horizon] = {"all_passed": all(checks.values()), "items": checks, "summary": item}

        items = {
            "instrument_count": gate(summary.get("instrument_count"), minimum=self.gates["minimum_instruments"]),
            "total_samples": gate(summary.get("total_samples"), minimum=self.gates["minimum_total_samples"]),
            "aggregate_directional_accuracy": gate(summary.get("mean_directional_accuracy"),
                                                   minimum=self.gates["minimum_directional_accuracy"], maximum=1.0),
            "aggregate_brier_score": gate(summary.get("mean_brier_score"), minimum=0.0,
                                          maximum=self.gates["maximum_brier_score"]),
            "aggregate_interval_80_coverage": gate(summary.get("mean_interval_80_coverage"),
                                                   minimum=self.gates["minimum_interval_80_coverage"], maximum=1.0),
            "aggregate_quantile_crossing_rate": gate(summary.get("mean_quantile_crossing_rate"), minimum=0.0,
                                                     maximum=self.gates["maximum_quantile_crossing_rate"]),
            "aggregate_touch_brier": gate(summary.get("mean_touch_brier"), minimum=0.0,
                                          maximum=self.gates["maximum_touch_brier"]),
            "metrics_valid": summary.get("invalid_metric_count") == 0,
            "all_formal_horizons": actual_horizons == expected_horizons
                and set(summary.get("horizon_contract") or []) == expected_horizons,
            "per_horizon_gates": all(item["all_passed"] for item in horizon_gates.values()),
            "validation_contract_eligible": summary.get("validation_contract_eligible") is True,
            "independent_holdout_verified": (
                summary.get("validation_contract_eligible") is True
                and summary.get("declared_independent_holdout") is True
            ),
            "pit_qualified_verified": (
                summary.get("validation_contract_eligible") is True
                and summary.get("declared_pit_qualified") is True
            ),
            "source_non_synthetic": summary.get("source_non_synthetic") is True,
            "input_lineage_digest_valid": summary.get("input_lineage_digest_valid") is True,
            "report_config_hash_present": bool(summary.get("report_config_hash")),
            "report_git_commit_present": bool(summary.get("report_git_commit_sha")),
            "validation_content_hash_matches": summary.get("validation_content_hash_matches") is True,
        }
        return {"all_passed": all(items.values()), "items": items, "horizons": horizon_gates}

    def _approval_checks(self, db: Session, profile: CalibrationProfile) -> dict[str, Any]:
        artifact = db.scalars(
            select(ReportArtifact).where(
                ReportArtifact.content_hash == profile.validation_content_hash,
                ReportArtifact.report_type == "forecast_validation",
                ReportArtifact.user_id.is_(None),
            )
        ).first()
        if artifact is None:
            return {"all_passed": False, "items": {"validation_artifact_present": False}}
        try:
            payload = read_system_json_report(
                artifact, self.settings, expected_type="forecast_validation"
            )
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

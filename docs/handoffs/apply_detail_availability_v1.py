from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}: {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    read_model = ROOT / "backend/app/workspace/read_model.py"
    types = ROOT / "frontend/src/lib/types.ts"
    detail = ROOT / "frontend/src/views/Detail.vue"

    replace_once(
        read_model,
        "from app.workspace.config import workspace_settings\n",
        "from app.workspace.config import workspace_settings\nfrom app.workspace.detail_availability import build_detail_availability\n",
    )

    replace_once(
        read_model,
        '"availability": availability, "decision_explanation": decision_explanation,\n',
        '"availability": build_detail_availability(availability, support_resistance=(None if issue else SupportResistanceService(settings).latest(db, inst.id)), chart=display_chart), "availability_contract_version": "detail-availability-v1", "decision_explanation": decision_explanation,\n',
    )

    replace_once(
        types,
        "export interface DetailAvailability { instrument: ModuleAvailability; price: ModuleAvailability; history: ModuleAvailability; price_basis: ModuleAvailability; indicators: ModuleAvailability; volume: ModuleAvailability; forecasts: ModuleAvailability; decision: ModuleAvailability }",
        "export interface DetailAvailability { instrument: ModuleAvailability; price: ModuleAvailability; history: ModuleAvailability; price_basis: ModuleAvailability; indicators: ModuleAvailability; volume: ModuleAvailability; forecasts: ModuleAvailability; decision: ModuleAvailability; support_resistance: ModuleAvailability }\nexport type DetailAvailabilityContractVersion = \"detail-availability-v1\"",
    )

    replace_once(
        types,
        "availability?: DetailAvailability; snapshot_id:",
        "availability?: DetailAvailability; availability_contract_version?: DetailAvailabilityContractVersion; snapshot_id:",
    )

    replace_once(
        detail,
        "import IndicatorReadings from '../components/IndicatorReadings.vue'",
        "import IndicatorReadings from '../components/IndicatorReadings.vue'\nimport AvailabilityMatrix from '../components/AvailabilityMatrix.vue'",
    )

    replace_once(
        detail,
        "<div v-if=\"q.data.value.history_issue\" class=\"notice warning-notice\" role=\"status\">",
        "<AvailabilityMatrix v-if=\"q.data.value.availability\" :availability=\"q.data.value.availability\" />\n<div v-if=\"q.data.value.history_issue\" class=\"notice warning-notice\" role=\"status\">",
    )


if __name__ == "__main__":
    main()

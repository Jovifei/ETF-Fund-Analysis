from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

EXPECTED_SHA = {
    "backend/app/workspace/read_model.py": "b17240e12cf0e585d4a258de51f7f37772035378",
    "frontend/src/lib/types.ts": "0fa0b78ca78aca0c6608726287f401f17d91f267",
}


def candidate(path: Path, old: str, new: str):
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"preflight failed: {path} expected one match")
    return text.replace(old, new, 1)


def main():
    files = {
        "read_model": ROOT / "backend/app/workspace/read_model.py",
        "types": ROOT / "frontend/src/lib/types.ts",
        "detail": ROOT / "frontend/src/views/Detail.vue",
    }

    proposals = {}
    proposals[files["read_model"]] = candidate(
        files["read_model"],
        "from app.workspace.config import workspace_settings\n",
        "from app.workspace.config import workspace_settings\nfrom app.workspace.detail_availability import build_detail_availability\n",
    )
    proposals[files["types"]] = candidate(
        files["types"],
        "export interface DetailAvailability { instrument: ModuleAvailability; price: ModuleAvailability; history: ModuleAvailability; price_basis: ModuleAvailability; indicators: ModuleAvailability; volume: ModuleAvailability; forecasts: ModuleAvailability; decision: ModuleAvailability }",
        "export interface DetailAvailability { instrument: ModuleAvailability; price: ModuleAvailability; history: ModuleAvailability; price_basis: ModuleAvailability; indicators: ModuleAvailability; volume: ModuleAvailability; forecasts: ModuleAvailability; decision: ModuleAvailability; support_resistance: ModuleAvailability }\nexport type DetailAvailabilityContractVersion = \"detail-availability-v1\"",
    )
    proposals[files["types"]] = proposals[files["types"]].replace(
        "availability?: DetailAvailability; snapshot_id:",
        "availability?: DetailAvailability; availability_contract_version?: DetailAvailabilityContractVersion; snapshot_id:",
        1,
    )
    proposals[files["detail"]] = candidate(
        files["detail"],
        "import IndicatorReadings from '../components/IndicatorReadings.vue'",
        "import IndicatorReadings from '../components/IndicatorReadings.vue'\nimport AvailabilityMatrix from '../components/AvailabilityMatrix.vue'",
    )

    for path, text in proposals.items():
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

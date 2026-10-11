"""Store and compatibility reader for local-display-v2 bundles."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.workspace.local_display_contract import (
    CONTRACT_VERSION,
    compute_parts_hashes,
    validate_bundle_manifest,
    verify_bundle_integrity,
)
from app.workspace.shadow_bundle import digest


class LocalDisplayStore:
    def __init__(self, store_dir: Path | str):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.latest_link = self.store_dir / "latest.json"
        self.previous_link = self.store_dir / "previous.json"

    def publish(self, bundle: dict[str, Any]) -> dict[str, Any]:
        manifest_dict = bundle.get("manifest", {})
        manifest = validate_bundle_manifest(manifest_dict)
        if not verify_bundle_integrity(bundle):
            raise ValueError("bundle parts integrity verification failed")

        bundle_id = digest(manifest_dict)
        target_file = self.store_dir / f"bundle_{manifest.sequence}_{bundle_id[:16]}.json"

        # Check idempotence
        if target_file.exists():
            return {
                "bundle_id": bundle_id,
                "manifest_hash": digest(manifest_dict),
                "status": "already_accepted",
                "sequence": manifest.sequence,
                "received_at": datetime.now(timezone.utc).isoformat(),
            }

        # Write bundle file atomically via temp file
        temp_file = self.store_dir / f"temp_{manifest.sequence}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False)
        temp_file.replace(target_file)

        # Atomic rotation of previous and latest
        if self.latest_link.exists():
            try:
                # Read current latest path
                with open(self.latest_link, "r", encoding="utf-8") as f:
                    curr_latest = json.load(f)
                with open(self.previous_link, "w", encoding="utf-8") as f:
                    json.dump(curr_latest, f, ensure_ascii=False)
            except Exception:
                pass

        # Write pointer to latest
        with open(self.latest_link, "w", encoding="utf-8") as f:
            json.dump({
                "bundle_file": target_file.name,
                "bundle_id": bundle_id,
                "sequence": manifest.sequence,
                "generated_at": manifest.generated_at,
            }, f, ensure_ascii=False)

        # Bounded retention: remove old bundles keeping latest 3
        bundles = sorted(self.store_dir.glob("bundle_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in bundles[3:]:
            try:
                old.unlink()
            except OSError:
                pass

        return {
            "bundle_id": bundle_id,
            "manifest_hash": digest(manifest_dict),
            "status": "accepted",
            "sequence": manifest.sequence,
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

    def load_bundle(self, generation: str | None = None) -> dict[str, Any] | None:
        if generation:
            matches = list(self.store_dir.glob(f"bundle_*_{generation[:16]}.json"))
            if matches:
                with open(matches[0], "r", encoding="utf-8") as f:
                    return json.load(f)

        if not self.latest_link.exists():
            return None
        try:
            with open(self.latest_link, "r", encoding="utf-8") as f:
                ptr = json.load(f)
            bundle_file = self.store_dir / ptr["bundle_file"]
            if bundle_file.exists():
                with open(bundle_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            return None
        return None


class LocalDisplayReader:
    def __init__(self, store: LocalDisplayStore):
        self.store = store

    def read_overview(
        self,
        horizon: int = 1,
        offset: int = 0,
        limit: int = 100,
        theme: str | None = None,
        generation: str | None = None,
    ) -> dict[str, Any]:
        bundle = self.store.load_bundle(generation)
        if not bundle:
            return {
                "rows": [],
                "total": 0,
                "as_of": datetime.now(timezone.utc).isoformat(),
                "snapshot_id": None,
                "read_model_version": "local-display-v2",
                "contains_mock": False,
                "is_stale": True,
            }

        ov_part = bundle.get("parts", {}).get("overview", {})
        rows = list(ov_part.get("rows", []))
        if theme:
            rows = [r for r in rows if r.get("theme_l1") == theme or r.get("theme_l2") == theme]

        total = len(rows)
        sliced_rows = rows[offset : offset + limit]

        return {
            "rows": sliced_rows,
            "total": total,
            "as_of": ov_part.get("generated_at"),
            "snapshot_id": ov_part.get("snapshot_id"),
            "read_model_version": CONTRACT_VERSION,
            "contains_mock": ov_part.get("contains_mock", False),
            "sector_timing": ov_part.get("sector_timing", {}),
            "generation": bundle.get("manifest", {}).get("sequence"),
            "is_stale": False,
        }

    def read_instrument_detail(
        self,
        code: str,
        user_id: int | None = None,
        generation: str | None = None,
    ) -> dict[str, Any] | None:
        bundle = self.store.load_bundle(generation)
        if not bundle:
            return None

        details = bundle.get("parts", {}).get("details", {})
        detail = details.get(code.upper())
        if not detail:
            return None

        return {
            **detail,
            "generation": bundle.get("manifest", {}).get("sequence"),
            "read_model_version": CONTRACT_VERSION,
        }

    def read_chart_data(
        self,
        code: str,
        interval: str = "1d",
        limit: int = 250,
        generation: str | None = None,
    ) -> dict[str, Any] | None:
        if interval not in {"1d", "1w", "1mo"}:
            raise ValueError("unsupported_chart_interval")

        bundle = self.store.load_bundle(generation)
        if not bundle:
            return None

        charts = bundle.get("parts", {}).get("charts", {})
        chart = charts.get(code.upper())
        if not chart:
            return None

        # Return bars up to limit
        bars = chart.get("bars", [])
        if len(bars) > limit:
            bars = bars[-limit:]

        return {
            **chart,
            "bars": bars,
            "generation": bundle.get("manifest", {}).get("sequence"),
            "read_model_version": CONTRACT_VERSION,
        }

    def read_sectors(self, generation: str | None = None) -> dict[str, Any]:
        bundle = self.store.load_bundle(generation)
        if not bundle:
            return {"sectors": [], "available": False}
        sectors_part = bundle.get("parts", {}).get("sectors", {})
        return {
            "sectors": sectors_part.get("sectors", []),
            "available": True,
            "generation": bundle.get("manifest", {}).get("sequence"),
        }

"""Store and compatibility reader for local-display-v2 bundles."""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.workspace.candle_periods import transform_chart
from app.workspace.local_display_contract import (
    CONTRACT_VERSION,
    MAX_BUNDLE_BYTES,
    _parse_iso,
    validate_bundle_manifest,
    verify_bundle_integrity,
)
from app.workspace.local_schedule import LocalRunLock
from app.workspace.shadow_bundle import digest

GEN_SEQ_RE = re.compile(r"^[0-9]+$")
GEN_HASH_RE = re.compile(r"^[0-9a-fA-F]{16,64}$")


class LocalDisplayStore:
    def __init__(self, store_dir: Path | str):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.latest_link = self.store_dir / "latest.json"
        self.previous_link = self.store_dir / "previous.json"
        self.lock_file = self.store_dir / ".publish.lock"

    def publish(self, bundle: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        manifest_dict = bundle.get("manifest", {})
        manifest = validate_bundle_manifest(manifest_dict)
        if not verify_bundle_integrity(bundle, now=now):
            raise ValueError("bundle parts integrity verification failed or bundle expired")

        bundle_id = digest(manifest_dict)
        target_file = self.store_dir / f"bundle_{manifest.sequence}_{bundle_id[:16]}.json"

        # Acquire publication lock to ensure concurrency safety and prevent inverted latest overwrite
        lock = LocalRunLock(self.lock_file)
        if not lock.acquire():
            # Retry briefly
            import time
            for _ in range(20):
                time.sleep(0.05)
                if lock.acquire():
                    break
            else:
                raise RuntimeError("publish lock contention timeout")

        try:
            # Check existing sequence strictly: sequence must be greater than current latest
            current_seq = None
            if self.latest_link.exists():
                try:
                    with open(self.latest_link, "r", encoding="utf-8") as f:
                        ptr = json.load(f)
                    current_seq = ptr.get("sequence")
                except Exception:
                    current_seq = None

            if current_seq is not None:
                if manifest.sequence < current_seq:
                    raise ValueError(
                        f"bundle sequence {manifest.sequence} is older than current sequence {current_seq}"
                    )
                if manifest.sequence == current_seq:
                    if target_file.exists():
                        return {
                            "bundle_id": bundle_id,
                            "manifest_hash": digest(manifest_dict),
                            "status": "already_accepted",
                            "sequence": manifest.sequence,
                            "received_at": datetime.now(timezone.utc).isoformat(),
                        }
                    raise ValueError(
                        f"bundle sequence {manifest.sequence} already matches current sequence {current_seq}"
                    )

            # Atomic write of bundle file using unique temp file
            temp_file = self.store_dir / f"temp_{manifest.sequence}_{uuid.uuid4().hex[:8]}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(bundle, f, ensure_ascii=False)
            temp_file.replace(target_file)

            # Determine files to protect from cleanup
            protected_files = {target_file.name}

            # Atomic rotation of previous and latest
            if self.latest_link.exists():
                try:
                    with open(self.latest_link, "r", encoding="utf-8") as f:
                        curr_latest = json.load(f)
                    if curr_latest.get("bundle_file"):
                        protected_files.add(curr_latest["bundle_file"])
                    temp_prev = self.store_dir / f"prev_{uuid.uuid4().hex[:8]}.tmp"
                    with open(temp_prev, "w", encoding="utf-8") as f:
                        json.dump(curr_latest, f, ensure_ascii=False)
                    temp_prev.replace(self.previous_link)
                except Exception:
                    pass

            # Atomic write of latest pointer
            latest_ptr = {
                "bundle_file": target_file.name,
                "bundle_id": bundle_id,
                "sequence": manifest.sequence,
                "generated_at": manifest.generated_at,
                "expires_at": manifest.expires_at,
            }
            temp_latest = self.store_dir / f"latest_{uuid.uuid4().hex[:8]}.tmp"
            with open(temp_latest, "w", encoding="utf-8") as f:
                json.dump(latest_ptr, f, ensure_ascii=False)
            temp_latest.replace(self.latest_link)

            # Enforce storage budget (MAX_BUNDLE_BYTES) and prune old bundles
            self._enforce_budget(protected_files=protected_files)

            return {
                "bundle_id": bundle_id,
                "manifest_hash": digest(manifest_dict),
                "status": "accepted",
                "sequence": manifest.sequence,
                "received_at": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            lock.release()

    def _enforce_budget(self, protected_files: set[str]) -> None:
        # Also clean up any lingering stale tmp files
        for tmp in self.store_dir.glob("*.tmp"):
            try:
                tmp.unlink()
            except OSError:
                pass

        all_bundles = sorted(self.store_dir.glob("bundle_*.json"), key=lambda p: p.stat().st_mtime)
        total_bytes = sum(b.stat().st_size for b in all_bundles)
        
        for b in list(all_bundles):
            if len(all_bundles) <= 2 or (total_bytes <= MAX_BUNDLE_BYTES and len(all_bundles) <= 5):
                break
            if b.name in protected_files:
                continue
            try:
                b_size = b.stat().st_size
                b.unlink()
                total_bytes -= b_size
                all_bundles.remove(b)
            except OSError:
                pass

    def load_bundle(self, generation: str | int | None = None) -> dict[str, Any] | None:
        if generation is not None:
            gen_str = str(generation).strip()
            # Strictly validate generation string format: only integer or hex hash, NO WILDCARDS
            if GEN_SEQ_RE.match(gen_str):
                # Match bundle_{gen_str}_*.json strictly without glob wildcards
                for f in self.store_dir.glob("bundle_*.json"):
                    parts = f.stem.split("_")
                    if len(parts) >= 3 and parts[1] == gen_str:
                        try:
                            with open(f, "r", encoding="utf-8") as fp:
                                return json.load(fp)
                        except Exception:
                            return None
            elif GEN_HASH_RE.match(gen_str):
                prefix = gen_str[:16].lower()
                for f in self.store_dir.glob("bundle_*.json"):
                    parts = f.stem.split("_")
                    if len(parts) >= 3 and parts[2].lower().startswith(prefix):
                        try:
                            with open(f, "r", encoding="utf-8") as fp:
                                return json.load(fp)
                        except Exception:
                            return None
            # If generation was explicitly requested but not matched, NEVER fallback to latest
            return None

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
        generation: str | int | None = None,
    ) -> dict[str, Any]:
        bundle = self.store.load_bundle(generation)
        if not bundle:
            return {
                "rows": [],
                "total": 0,
                "as_of": datetime.now(timezone.utc).isoformat(),
                "snapshot_id": None,
                "read_model_version": CONTRACT_VERSION,
                "contains_mock": False,
                "is_stale": True,
            }

        manifest = bundle.get("manifest", {})
        expires_at_str = manifest.get("expires_at")
        is_stale = False
        if expires_at_str:
            try:
                exp_dt = _parse_iso(expires_at_str)
                is_stale = datetime.now(timezone.utc) > exp_dt
            except Exception:
                is_stale = True
        else:
            is_stale = True

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
            "generation": manifest.get("sequence"),
            "is_stale": is_stale,
        }

    def read_instrument_detail(
        self,
        code: str,
        user_id: int | None = None,
        generation: str | int | None = None,
    ) -> dict[str, Any] | None:
        bundle = self.store.load_bundle(generation)
        if not bundle:
            return None

        details = bundle.get("parts", {}).get("details", {})
        detail = details.get(code.upper())
        if not detail:
            return None

        # Clean detail of any private holding/avg_cost info before return
        clean_detail = {k: v for k, v in detail.items() if k not in {"avg_cost", "trades", "account_id"}}
        return {
            **clean_detail,
            "generation": bundle.get("manifest", {}).get("sequence"),
            "read_model_version": CONTRACT_VERSION,
        }

    def read_chart_data(
        self,
        code: str,
        interval: str = "1d",
        limit: int = 250,
        generation: str | int | None = None,
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

        chart_copy = dict(chart)
        # If user requests 1w or 1mo, perform aggregation on the daily bars
        if interval != "1d":
            try:
                aggregated = transform_chart(chart_copy, period=interval, config={}, limit=limit)
                if not aggregated or not aggregated.get("bars"):
                    raise ValueError("chart_period_aggregation_failed")
                return {
                    **aggregated,
                    "interval": interval,
                    "generation": bundle.get("manifest", {}).get("sequence"),
                    "read_model_version": CONTRACT_VERSION,
                }
            except Exception:
                # Never disguise daily bars as weekly/monthly; return None on failure
                return None

        bars = chart_copy.get("bars", [])
        if len(bars) > limit:
            bars = bars[-limit:]

        return {
            **chart_copy,
            "interval": interval,
            "bars": bars,
            "generation": bundle.get("manifest", {}).get("sequence"),
            "read_model_version": CONTRACT_VERSION,
        }

    def read_sectors(self, generation: str | int | None = None) -> dict[str, Any]:
        bundle = self.store.load_bundle(generation)
        if not bundle:
            return {"sectors": [], "available": False}
        sectors_part = bundle.get("parts", {}).get("sectors", {})
        return {
            "sectors": sectors_part.get("sectors", []),
            "available": True,
            "generation": bundle.get("manifest", {}).get("sequence"),
        }

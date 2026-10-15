"""Store and compatibility reader for local-display-v2 bundles."""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.workspace.local_display_contract import (
    CONTRACT_VERSION,
    MAX_BUNDLE_BYTES,
    _parse_iso,
    validate_bundle_manifest,
    verify_bundle_integrity,
)

from app.workspace.local_schedule import LocalRunLock
from app.workspace.shadow_bundle import digest, canonical

GEN_SEQ_RE = re.compile(r"^[0-9]+$")
GEN_HASH_RE = re.compile(r"^[0-9a-fA-F]{16,64}$")


class LocalDisplayStore:
    """Immutable v2 generations with validation on every read and bounded publication."""
    FILE_RE = re.compile(r"bundle_([1-9][0-9]*)_([0-9a-f]{16})\.json")

    def __init__(self, store_dir: Path | str, *, max_bytes: int | None = None, domain=None):
        self.store_dir = Path(store_dir)
        if self.store_dir.is_symlink():
            raise ValueError("symlink store rejected")
        self.max_bytes = MAX_BUNDLE_BYTES if max_bytes is None else max_bytes
        if type(self.max_bytes) is not int or self.max_bytes <= 0:
            raise ValueError("invalid store budget")
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.latest_link = self.store_dir / "latest.json"
        self.previous_link = self.store_dir / "previous.json"
        self.lock_file = self.store_dir / ".publish.lock"
        from app.workspace.sync_domain import SyncDomain
        self._own_domain = domain is None
        self.domain = domain or SyncDomain(self.store_dir, max_bytes=self.max_bytes)

    def _load_file(self, path: Path, *, expected_id: str | None = None) -> dict[str, Any] | None:
        match = self.FILE_RE.fullmatch(path.name)
        if not match or path.parent != self.store_dir or path.is_symlink():
            return None
        try:
            if path.stat().st_size > self.max_bytes:
                return None
            value = json.loads(path.read_bytes())
            if not verify_bundle_integrity(value):
                return None
            manifest = value["manifest"]
            identity = digest(manifest)
            if str(manifest["sequence"]) != match[1] or identity[:16] != match[2]:
                return None
            if expected_id is not None and identity != expected_id:
                return None
            return value
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            return None

    def _load_pointer(self, path: Path) -> dict[str, Any] | None:
        try:
            if path.is_symlink() or path.stat().st_size > 65536:
                return None
            pointer = json.loads(path.read_bytes())
            if not isinstance(pointer, dict):
                return None
            name = pointer.get("bundle_file")
            identity = pointer.get("bundle_id")
            if not isinstance(name, str) or not self.FILE_RE.fullmatch(name):
                return None
            if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity):
                return None
            value = self._load_file(self.store_dir / name, expected_id=identity)
            if value is None:
                return None
            manifest = value["manifest"]
            if any(pointer.get(key) != manifest[key] for key in ("sequence", "generated_at", "expires_at")):
                return None
            return pointer
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def _atomic(self, path: Path, data: bytes) -> None:
        if self.domain is not None:
            self.domain.reserve(len(data))
        temp = self.store_dir / f".pending-{uuid.uuid4().hex}"
        try:
            with temp.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def _budget_plan(self, target: Path, size: int, current: dict | None) -> list[Path]:
        files = [p for p in self.store_dir.glob("bundle_*.json") if self.FILE_RE.fullmatch(p.name)]
        if any(p.is_symlink() for p in files):
            raise ValueError("symlink generation rejected")
        files.sort(key=lambda p: (p.stat().st_mtime_ns, p.name))
        used = sum(p.stat().st_size for p in files)
        if size > self.max_bytes or used > self.max_bytes:
            raise ValueError("store capacity exceeded")
        protected = {target.name}
        if current is not None:
            protected.add(current["bundle_file"])
        total = used + (0 if target.exists() else size)
        count = len(files) + (0 if target.exists() else 1)
        evict = []
        for path in files:
            if total <= self.max_bytes and count <= 5:
                break
            if path.name in protected:
                continue
            total -= path.stat().st_size
            count -= 1
            evict.append(path)
        if total > self.max_bytes:
            raise ValueError("store capacity exceeded")
        return evict

    @staticmethod
    def _receipt(manifest: dict, identity: str, status: str) -> dict[str, Any]:
        return {"bundle_id": identity, "manifest_hash": identity, "status": status,
                "sequence": manifest["sequence"], "received_at": datetime.now(timezone.utc).isoformat()}

    def publish(self, bundle: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        if self._own_domain:
            self.domain.max_bytes = self.max_bytes
        with self.domain.locked():
            return self._publish(bundle, now=now)

    def _publish(self, bundle: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        if not isinstance(bundle, dict):
            raise ValueError("invalid bundle")
        manifest = validate_bundle_manifest(bundle.get("manifest", {}))
        if not verify_bundle_integrity(bundle):
            raise ValueError("bundle parts integrity verification failed")
        manifest_dict = bundle["manifest"]
        identity = digest(manifest_dict)
        data = canonical(bundle)
        target = self.store_dir / f"bundle_{manifest.sequence}_{identity[:16]}.json"
        lock = LocalRunLock(self.lock_file)
        if not lock.acquire(reclaim_stale=False):
            import time
            for _ in range(20):
                time.sleep(0.05)
                if lock.acquire(reclaim_stale=False):
                    break
            else:
                raise ValueError("publish lock contention timeout")
        try:
            if any(path.is_symlink() for path in (target, self.latest_link, self.previous_link)):
                raise ValueError("symlink publication path rejected")
            current = self._load_pointer(self.latest_link) if self.latest_link.exists() else None
            if self.latest_link.exists() and current is None:
                raise ValueError("invalid latest generation pointer")
            if current is not None:
                if manifest.sequence < current["sequence"]:
                    raise ValueError("bundle sequence older than current sequence")
                if manifest.sequence == current["sequence"]:
                    if identity == current["bundle_id"]:
                        return self._receipt(manifest_dict, identity, "already_accepted")
                    raise ValueError("bundle sequence already accepted with different identity")
            # A same-identity retry above is only a receipt lookup. Every new activation
            # uses receiver time; stored expired generations remain readable as STALE.
            activation_time = now or datetime.now(timezone.utc)
            if not verify_bundle_integrity(bundle, now=activation_time):
                raise ValueError("bundle expired or generated in future")
            if target.exists() and target.read_bytes() != data:
                raise ValueError("immutable bundle collision")
            evict = self._budget_plan(target, len(data), current)
            # Preflight completes before any generation/pointer mutation. Keep rollback bytes bounded
            # by the already-validated total store budget if a subsequent filesystem operation fails.
            backups = {p: p.read_bytes() for p in evict}
            old_latest = self.latest_link.read_bytes() if self.latest_link.exists() else None
            old_previous = self.previous_link.read_bytes() if self.previous_link.exists() else None
            created = not target.exists()
            pointer = {"bundle_file": target.name, "bundle_id": identity, "sequence": manifest.sequence,
                       "generated_at": manifest.generated_at, "expires_at": manifest.expires_at}
            self.domain.reserve((len(data) if created else 0) + len(canonical(pointer))
                                + (len(canonical(current)) if current else 0))
            try:
                if created:
                    self._atomic(target, data)
                if current is not None:
                    self._atomic(self.previous_link, canonical(current))
                self._atomic(self.latest_link, canonical(pointer))
                for path in evict:
                    path.unlink()
            except OSError:
                for path, payload in backups.items():
                    if not path.exists():
                        self._atomic(path, payload)
                for path, payload in ((self.previous_link, old_previous), (self.latest_link, old_latest)):
                    if payload is None:
                        path.unlink(missing_ok=True)
                    elif not path.exists() or path.read_bytes() != payload:
                        self._atomic(path, payload)
                if created:
                    target.unlink(missing_ok=True)
                raise
            return self._receipt(manifest_dict, identity, "accepted")
        finally:
            lock.release()

    def load_bundle(self, generation: str | int | None = None) -> dict[str, Any] | None:
        if generation is None:
            pointer = self._load_pointer(self.latest_link)
            return self._load_file(self.store_dir / pointer["bundle_file"], expected_id=pointer["bundle_id"]) if pointer else None
        text = str(generation).strip()
        if not GEN_SEQ_RE.fullmatch(text) and not GEN_HASH_RE.fullmatch(text):
            return None
        explicit_sequence = type(generation) is int
        full_id = not explicit_sequence and len(text) == 64 and GEN_HASH_RE.fullmatch(text)
        matches = []
        for path in self.store_dir.glob("bundle_*.json"):
            value = self._load_file(path)
            if value is None:
                continue
            manifest = value["manifest"]
            identity = digest(manifest)
            if full_id:
                matched = identity == text.lower()
            elif explicit_sequence:
                matched = str(manifest["sequence"]) == text
            else:
                matched = (bool(GEN_SEQ_RE.fullmatch(text)) and str(manifest["sequence"]) == text) or (bool(GEN_HASH_RE.fullmatch(text)) and identity.startswith(text.lower()))
            if matched:
                matches.append(value)
        # Sequence and short hash aliases must be unambiguous. No fallback to latest.
        return matches[0] if len(matches) == 1 else None


class LocalDisplayReader:
    def __init__(self, store: LocalDisplayStore, *, code_sha: str | None = None, config_hash: str | None = None):
        self.store = store
        self.code_sha, self.config_hash = code_sha, config_hash

    def load_bundle(self, generation):
        bundle = self.store.load_bundle(generation)
        if bundle is not None and self.code_sha is not None:
            manifest = bundle.get("manifest", {})
            matched = (manifest.get("code_sha") == self.code_sha and manifest.get("config_hash") == self.config_hash
                       and bool(self.code_sha) and bool(self.config_hash))
            if not matched:
                if generation is None:
                    return None
                bundle = {**bundle, "historical_identity": True}
        return bundle

    def read_overview(
        self,
        horizon: int = 1,
        offset: int = 0,
        limit: int = 100,
        theme: str | None = None,
        generation: str | int | None = None,
    ) -> dict[str, Any]:
        if horizon not in (1, 3, 5, 10):
            raise ValueError("unsupported horizon")
        bundle = self.load_bundle(generation)
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
                is_stale = bool(bundle.get("historical_identity")) or datetime.now(timezone.utc) >= exp_dt
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
            "generated_at": manifest.get("generated_at"),
            "offset": offset,
            "limit": limit,
            "themes": sorted({str(row["theme_l1"]) for row in rows if row.get("theme_l1")}),
            "snapshot_id": ov_part.get("snapshot_id"),
            "read_model_version": CONTRACT_VERSION,
            "contains_mock": ov_part.get("contains_mock", False),
            "sector_timing": ov_part.get("sector_timing", {}),
            "generation": manifest.get("sequence"),
            "is_stale": is_stale,
        }

    def read_decision_board(
        self,
        horizon: int = 1,
        snapshot_id: str | None = None,
        generation: str | int | None = None,
    ) -> dict[str, Any] | None:
        if horizon not in (1, 3, 5, 10):
            raise ValueError("unsupported horizon")
        bundle = self.load_bundle(generation)
        if not bundle:
            return None

        manifest = bundle.get("manifest", {})
        expires_at_str = manifest.get("expires_at")
        is_stale = False
        if expires_at_str:
            try:
                exp_dt = _parse_iso(expires_at_str)
                is_stale = bool(bundle.get("historical_identity")) or datetime.now(timezone.utc) >= exp_dt
            except Exception:
                is_stale = True
        else:
            is_stale = True

        ov_part = bundle.get("parts", {}).get("overview", {})
        if snapshot_id is not None and str(ov_part.get("snapshot_id")) != snapshot_id:
            return None
        captured_horizon = ov_part.get("horizon", 1)
        rows = [{**row, "forecast": (row.get("forecasts") or {}).get(str(horizon)),
                 "grade": row.get("grade", "数据异常") if horizon == captured_horizon else "数据异常",
                 "grade_reason": row.get("grade_reason") if horizon == captured_horizon else "selected_horizon_grade_not_published"}
                for row in ov_part.get("rows", [])]
        generated_at = ov_part.get("generated_at") or manifest.get("generated_at")
        trade_date = ov_part.get("target_trade_date")
        if not trade_date and generated_at:
            trade_date = generated_at[:10]

        counts: dict[str, int] = {}
        for r in rows:
            g = r.get("grade", "数据异常")
            counts[g] = counts.get(g, 0) + 1

        return {
            "snapshot_id": ov_part.get("snapshot_id") or str(manifest.get("sequence")),
            "generated_at": generated_at,
            "target_trade_date": trade_date,
            "generation": manifest.get("sequence"),
            "selected_horizon": horizon,
            "decision_horizon": captured_horizon,
            "horizons": [1, 3, 5, 10],
            "as_of": generated_at,
            "freshness": "stale" if is_stale else "fresh",
            "data_status": {"freshness": "stale" if is_stale else "fresh"},
            "source_status": {"freshness": "stale" if is_stale else "fresh", "actionable": False},
            "read_model_version": CONTRACT_VERSION,
            "current_board_read_contract": "local-display-v2",
            "read_contract": "historical_identity" if bundle.get("historical_identity") else "version_matched",
            "counts": counts,
            "rows": rows,
            "sector_timing": ov_part.get("sector_timing", {}),
            "research_only": True,
            "actionable": False,
            "automatic_orders": False,
        }

    def read_instrument_detail(
        self,
        code: str,
        user_id: int | None = None,
        generation: str | int | None = None,
    ) -> dict[str, Any] | None:
        bundle = self.load_bundle(generation)
        if not bundle:
            return None

        details = bundle.get("parts", {}).get("details", {})
        detail = details.get(code.upper())
        if not detail:
            return None

        # Clean detail of any private holding/avg_cost info before return
        clean_detail = {k: v for k, v in detail.items() if k not in {"avg_cost", "trades", "account_id"}}
        stale = bool(bundle.get("historical_identity")) or datetime.now(timezone.utc) >= _parse_iso(bundle["manifest"]["expires_at"])
        if stale and isinstance(clean_detail.get("quote"), dict):
            clean_detail["quote"] = {**clean_detail["quote"], "status": "stale"}
        return {
            **clean_detail,
            "generation": bundle.get("manifest", {}).get("sequence"),
            "is_stale": stale,
            "read_model_version": CONTRACT_VERSION,
        }

    def read_chart_data(
        self,
        code: str,
        interval: str = "1d",
        limit: int = 250,
        generation: str | int | None = None,
        as_of: str | datetime | None = None,
    ) -> dict[str, Any] | None:
        if interval not in {"1d", "1w", "1mo"}:
            raise ValueError("unsupported_chart_interval")

        bundle = self.load_bundle(generation)
        if not bundle:
            return None

        charts = bundle.get("parts", {}).get("charts", {})
        chart = charts.get(code.upper())
        if not chart:
            return None

        chart_copy = dict(chart)
        captured_at = bundle.get("manifest", {}).get("generated_at")
        if as_of is not None and _parse_iso(str(as_of)) != _parse_iso(captured_at):
            raise ValueError("generation_time_mismatch")
        # Aggregation belongs to the producer; absent periods are explicitly unavailable.
        if interval != "1d":
            chart_copy = bundle.get("parts", {}).get("chart_periods", {}).get(code.upper(), {}).get(interval)
            if not isinstance(chart_copy, dict):
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
        bundle = self.load_bundle(generation)
        if not bundle:
            return {"sectors": [], "available": False}
        sectors_part = bundle.get("parts", {}).get("sectors", {})
        return {
            "sectors": sectors_part.get("sectors", []),
            "boards": [{**row, "sector_pct_change": row.get("pct_change")} for row in sectors_part.get("sectors", [])],
            "available": True,
            "generation": bundle.get("manifest", {}).get("sequence"),
        }

    def read_market_context(self, generation: str | int | None = None) -> list[dict[str, Any]] | None:
        bundle = self.load_bundle(generation)
        if not bundle:
            return None
        part = bundle.get("parts", {}).get("market_context")
        if not part or not isinstance(part.get("items"), list) or not part["items"]:
            return None
        return list(part["items"])

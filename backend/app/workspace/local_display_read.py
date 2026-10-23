"""Store and compatibility reader for local-display-v2 bundles."""
from __future__ import annotations

from app.utils.horizons import DEFAULT_RESEARCH_HORIZONS
import json
import os
import re
import threading
import uuid
from collections import OrderedDict
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
ACCEPTANCE_HISTORY_VERSION = "local-acceptance-v1"
ACCEPTANCE_HISTORY_LIMIT = 256
CONSUMER_VERSION = "local-display-consumer-v1"

# Process-wide cache of validated, immutable bundle files.  A bundle is ~16 MB
# of JSON and ~70 MB once parsed; the overview page fires 5-8 reads at once,
# and parsing each one twice (pointer check + load) per request drove the API
# to ~600 MB and a host OOM kill on 2026-10-22.  Files are written once via
# os.replace, so (device, inode, size, mtime_ns, ctime_ns) identifies their content.
# Parsing is serialised under one lock so concurrent misses cost one parse.
# Cached values are shared and must be treated as read-only by callers.
def _cache_entries_from_env() -> int:
    try:
        return max(0, min(8, int(os.environ.get("LOCAL_DISPLAY_V2_CACHE_ENTRIES", "2"))))
    except ValueError:
        return 2


_BUNDLE_CACHE_MAX = _cache_entries_from_env()
_BUNDLE_CACHE: "OrderedDict[tuple, dict[str, Any]]" = OrderedDict()
_BUNDLE_CACHE_LOCK = threading.Lock()


def clear_bundle_cache() -> None:
    with _BUNDLE_CACHE_LOCK:
        _BUNDLE_CACHE.clear()



class LocalDisplayStore:
    """Immutable v2 generations with validation on every read and bounded publication."""
    FILE_RE = re.compile(r"bundle_([1-9][0-9]*)_([0-9a-f]{16})\.json")

    def __init__(self, store_dir: Path | str, *, max_bytes: int | None = None, domain=None, max_generations: int = 20):
        self.store_dir = Path(store_dir)
        if self.store_dir.is_symlink():
            raise ValueError("symlink store rejected")
        self.max_bytes = MAX_BUNDLE_BYTES if max_bytes is None else max_bytes
        if type(self.max_bytes) is not int or self.max_bytes <= 0:
            raise ValueError("invalid store budget")
        if type(max_generations) is not int or max_generations < 2 or max_generations > 100:
            raise ValueError("invalid max_generations")
        self.max_generations = max_generations
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
            st = path.stat()
            if st.st_size > self.max_bytes:
                return None
            key = (str(path), st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
            with _BUNDLE_CACHE_LOCK:
                cached = _BUNDLE_CACHE.get(key) if _BUNDLE_CACHE_MAX else None
                if cached is not None:
                    _BUNDLE_CACHE.move_to_end(key)
                    value, identity = cached
                else:
                    raw = path.read_bytes()
                    after = path.stat()
                    if path.is_symlink() or (after.st_dev, after.st_ino, after.st_size,
                                            after.st_mtime_ns, after.st_ctime_ns) != key[1:]:
                        return None
                    value = json.loads(raw)
                    if not verify_bundle_integrity(value):
                        return None
                    manifest = value["manifest"]
                    identity = digest(manifest)
                    if str(manifest["sequence"]) != match[1] or identity[:16] != match[2]:
                        return None
                    if _BUNDLE_CACHE_MAX:
                        for stale in [k for k in _BUNDLE_CACHE if k[0] == key[0]]:
                            del _BUNDLE_CACHE[stale]
                        _BUNDLE_CACHE[key] = (value, identity)
                        while len(_BUNDLE_CACHE) > _BUNDLE_CACHE_MAX:
                            _BUNDLE_CACHE.popitem(last=False)
            if expected_id is not None and identity != expected_id:
                return None
            return value
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            return None

    @staticmethod
    def _acceptance_history(pointer: dict[str, Any]) -> list[dict[str, Any]]:
        """Proof is committed atomically with latest, never inferred from old files.

        Legacy pointers prove only their own identity. The bounded history is
        NOT a permanent audit archive: a pruned identity cannot be restored.
        """
        own = {"sequence": pointer["sequence"], "bundle_id": pointer["bundle_id"]}
        if type(own["sequence"]) is not int or own["sequence"] <= 0:
            raise ValueError("invalid acceptance sequence")
        if "acceptance_history_version" not in pointer and "accepted" not in pointer:
            return [own]
        if pointer.get("acceptance_history_version") != ACCEPTANCE_HISTORY_VERSION:
            raise ValueError("invalid acceptance history version")
        records = pointer.get("accepted")
        if not isinstance(records, list) or not 1 <= len(records) <= ACCEPTANCE_HISTORY_LIMIT:
            raise ValueError("invalid acceptance history")
        last = 0
        for record in records:
            if (not isinstance(record, dict) or set(record) != {"sequence", "bundle_id"}
                    or type(record["sequence"]) is not int or record["sequence"] <= last
                    or not isinstance(record["bundle_id"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", record["bundle_id"])):
                raise ValueError("invalid acceptance identity")
            last = record["sequence"]
        if records[-1] != own:
            raise ValueError("acceptance history does not match pointer")
        return records

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
            self._acceptance_history(pointer)
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

    def _budget_plan(self, target: Path, size: int, current: dict | None, extra: int) -> list[Path]:
        files = [p for p in self.store_dir.glob("bundle_*.json") if self.FILE_RE.fullmatch(p.name)]
        if any(p.is_symlink() for p in files):
            raise ValueError("symlink generation rejected")
        previous = self._load_pointer(self.previous_link) if self.previous_link.exists() else None
        if self.previous_link.exists() and previous is None:
            raise ValueError("invalid previous generation pointer")
        protected = {target.name}
        for pointer in (current, previous):
            if pointer:
                protected.add(pointer["bundle_file"])
        cutoff = min((p["sequence"] for p in (current, previous) if p), default=0)
        # Only complete, validated cache generations older than BOTH rollback pointers
        # are reclaimable. Unknown files, orphan future candidates and evidence remain.
        reclaimable = []
        for path in files:
            if path.name in protected:
                continue
            value = self._load_file(path)
            if value is not None and value["manifest"]["sequence"] < cutoff:
                reclaimable.append(path)
        reclaimable.sort(key=lambda p: int(self.FILE_RE.fullmatch(p.name)[1]))
        total = self.domain.used_bytes() + self.domain.held_bytes + extra
        count = len(files) + (0 if target.exists() else 1)
        evict = []
        # Keep enough generations for a full trading day of slots (~12–20).
        max_keep = getattr(self, "max_generations", 20)
        for path in reclaimable:
            if total <= self.domain.max_bytes and count <= max_keep:
                break
            total -= path.stat().st_size
            count -= 1
            evict.append(path)
        if size > self.max_bytes or total > self.domain.max_bytes:
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
            history = self._acceptance_history(current) if current else []
            if current and "acceptance_history_version" not in current and self.previous_link.exists():
                # Upgrade only validated pointer evidence; orphan cache files prove nothing.
                previous = self._load_pointer(self.previous_link)
                if previous is None:
                    raise ValueError("invalid previous generation pointer")
                if previous["sequence"] < current["sequence"]:
                    history = [{"sequence": previous["sequence"], "bundle_id": previous["bundle_id"]}, *history]
            if current is not None:
                if manifest.sequence < current["sequence"]:
                    if {"sequence": manifest.sequence, "bundle_id": identity} not in history:
                        raise ValueError("historical identity was not accepted or proof was pruned")
                    # Only an exact receiver-accepted identity may be restored. Expiry
                    # does not revoke historical evidence; neither pointer is promoted.
                    if target.exists():
                        existing = self._load_file(target, expected_id=identity)
                        if existing is None or digest(existing["manifest"]) != identity:
                            raise ValueError("immutable bundle collision")
                        return self._receipt(manifest_dict, identity, "already_accepted")
                    if not verify_bundle_integrity(bundle):
                        raise ValueError("bundle parts integrity verification failed")
                    # Structural-only check: expiry is irrelevant for historical evidence.
                    extra = len(data)
                    evict = self._budget_plan(target, len(data), current, extra)
                    for path in evict:
                        path.unlink()
                    self.domain.reserve(extra)
                    try:
                        self._atomic(target, data)
                    except OSError:
                        target.unlink(missing_ok=True)
                        raise
                    return self._receipt(manifest_dict, identity, "already_accepted")
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
            old_latest = self.latest_link.read_bytes() if self.latest_link.exists() else None
            old_previous = self.previous_link.read_bytes() if self.previous_link.exists() else None
            created = not target.exists()
            accepted = [*history, {"sequence": manifest.sequence, "bundle_id": identity}]
            pointer = {"bundle_file": target.name, "bundle_id": identity, "sequence": manifest.sequence,
                       "generated_at": manifest.generated_at, "expires_at": manifest.expires_at,
                       "acceptance_history_version": ACCEPTANCE_HISTORY_VERSION,
                       "accepted": accepted[-ACCEPTANCE_HISTORY_LIMIT:]}
            pointer_data = canonical(pointer)
            if len(pointer_data) > 65536:
                raise ValueError("acceptance history exceeds pointer limit")
            extra = ((len(data) if created else 0) + len(pointer_data)
                     + (len(canonical(current)) if current else 0))
            evict = self._budget_plan(target, len(data), current, extra)
            # GC precedes the new temporary file: no transient budget overdraft.
            # On later publication failure only obsolete caches may be gone; the
            # pre-existing current/previous pair remains intact and recoverable.
            for path in evict:
                path.unlink()
            self.domain.reserve(extra)
            try:
                if created:
                    self._atomic(target, data)
                if current is not None:
                    self._atomic(self.previous_link, canonical(current))
                self._atomic(self.latest_link, pointer_data)
            except OSError:
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
        if len(text) > 64 or (not GEN_SEQ_RE.fullmatch(text) and not GEN_HASH_RE.fullmatch(text)):
            return None
        explicit_sequence = type(generation) is int
        full_id = not explicit_sequence and len(text) == 64 and GEN_HASH_RE.fullmatch(text)
        sequence_alias = bool(GEN_SEQ_RE.fullmatch(text)) and not full_id
        hash_alias = bool(GEN_HASH_RE.fullmatch(text)) and not explicit_sequence
        matches = []
        for path in self.store_dir.glob("bundle_*.json"):
            name = self.FILE_RE.fullmatch(path.name)
            # Filenames select candidates only. Content, full identity and
            # alias ambiguity still require verification.
            if name is None or not (
                (sequence_alias and name[1] == text)
                or (hash_alias and name[2] == text[:16].lower())
            ):
                continue
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
        if horizon not in DEFAULT_RESEARCH_HORIZONS:
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
                "research_source": "local_bundle",
                "consumer_contract_version": CONSUMER_VERSION,
                "reason": "local_display_generation_unavailable",
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
            "research_source": "local_bundle",
            "consumer_contract_version": CONSUMER_VERSION,
        }

    def read_decision_board(
        self,
        horizon: int = 1,
        snapshot_id: str | None = None,
        generation: str | int | None = None,
    ) -> dict[str, Any] | None:
        if horizon not in DEFAULT_RESEARCH_HORIZONS:
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
            "horizons": list(DEFAULT_RESEARCH_HORIZONS),
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
            "research_source": "local_bundle",
            "consumer_contract_version": CONSUMER_VERSION,
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

    @staticmethod
    def _panel_metadata(bundle: dict[str, Any] | None) -> dict[str, Any]:
        stale = True
        if bundle:
            try:
                stale = bool(bundle.get("historical_identity")) or datetime.now(timezone.utc) >= _parse_iso(bundle["manifest"]["expires_at"])
            except (ValueError, TypeError, KeyError):
                pass
        return {"generation": bundle["manifest"]["sequence"] if bundle else None,
                "research_source": "local_bundle", "consumer_contract_version": CONSUMER_VERSION,
                "is_stale": stale, "actionable": False}

    def read_sectors(self, generation: str | int | None = None) -> dict[str, Any]:
        bundle = self.load_bundle(generation)
        if not bundle:
            return {**self._panel_metadata(None), "sectors": [], "boards": [], "available": False,
                    "availability": "unavailable", "reason": "local_display_generation_unavailable"}
        part = bundle.get("parts", {}).get("sectors", {})
        rows = part.get("sectors", [])
        result = {
            **self._panel_metadata(bundle), "sectors": rows,
            "boards": [{**row, "sector_pct_change": row.get("pct_change"),
                        "source_as_of": row.get("source_as_of") or row.get("trade_date"),
                        "breadth": row.get("breadth") or {name: row.get(field) for name, field in
                            (("up", "up_count"), ("down", "down_count"), ("flat", "flat_count"), ("total", "total_count"))}}
                       for row in rows],
            "available": part.get("availability") != "unavailable" and bool(rows),
            "availability": part.get("availability", "available" if rows else "unavailable"),
        }
        for key in ("reason", "refreshed_at", "refreshed_in_slot", "source_as_of"):
            if key in part:
                result[key] = part[key]
        return result

    def read_market_context_view(self, generation: str | int | None = None) -> dict[str, Any]:
        """Status-bearing view; empty, failed and carried-forward are not equivalent."""
        bundle = self.load_bundle(generation)
        part = bundle.get("parts", {}).get("market_context", {}) if bundle else {}
        items = part.get("items", [])
        result = {**self._panel_metadata(bundle), "items": list(items),
                  "availability": part.get("availability", "available" if items else "unavailable")}
        for key in ("reason", "refreshed_at", "refreshed_in_slot", "source_as_of"):
            if key in part:
                result[key] = part[key]
        if not bundle:
            result["reason"] = "local_display_generation_unavailable"
        elif not items and "reason" not in result:
            result["reason"] = "market_context_not_published"
        return result

    def read_market_context(self, generation: str | int | None = None) -> list[dict[str, Any]] | None:
        # Legacy bootstrap/list callers retain their existing return contract.
        items = self.read_market_context_view(generation)["items"]
        return items or None

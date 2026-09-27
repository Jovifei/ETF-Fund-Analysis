from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from czsc import CZSC, Freq, RawBar


FIXTURE_SIZE = 300
MIN_PREFIX = 20
PRICE_BASIS_ID = "raw-synthetic-r4-v1"
SUFFIX_CUTOFFS = (80, 160, 240)


def make_rows(count: int = FIXTURE_SIZE, volume: float | None = 100.0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = datetime(2026, 1, 1)
    for index in range(count):
        phase = (index // 5) % 2
        close = 100.0 + (3.0 if phase == 0 else -3.0) + (index // 50) * 0.2
        open_price = close - 1.0 if phase == 0 else close + 1.0
        high = max(open_price, close) + 1.0
        low = min(open_price, close) - 1.0
        amount = None if volume is None else volume * close
        rows.append(
            {
                "index": index,
                "dt": start + timedelta(days=index),
                "open": open_price,
                "close": close,
                "high": high,
                "low": low,
                "volume": volume,
                "amount": amount,
            }
        )
    return rows


def bars_from_rows(rows: list[dict[str, Any]]) -> list[RawBar]:
    return [
        RawBar(
            "M1",
            row["dt"],
            Freq.D,
            row["open"],
            row["close"],
            row["high"],
            row["low"],
            row["volume"],
            row["amount"],
            row["index"],
        )
        for row in rows
    ]


def mutate_suffix(rows: list[dict[str, Any]], cutoff: int) -> list[dict[str, Any]]:
    mutated = [dict(row) for row in rows]
    for row in mutated:
        if row["index"] <= cutoff:
            continue
        row["open"] += 0.37
        row["close"] -= 0.61 if row["index"] % 2 else -0.43
        row["high"] = max(row["open"], row["close"]) + 2.0
        row["low"] = min(row["open"], row["close"]) - 2.0
    return mutated


def json_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def current_peak_rss_bytes() -> tuple[int | None, str | None]:
    """Read an OS-level peak working-set/RSS value without a new dependency."""
    if sys.platform == "win32":
        try:
            import ctypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("page_fault_count", ctypes.c_ulong),
                    ("peak_working_set_size", ctypes.c_size_t),
                    ("working_set_size", ctypes.c_size_t),
                    ("quota_peak_paged_pool_usage", ctypes.c_size_t),
                    ("quota_paged_pool_usage", ctypes.c_size_t),
                    ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
                    ("quota_non_paged_pool_usage", ctypes.c_size_t),
                    ("pagefile_usage", ctypes.c_size_t),
                    ("peak_pagefile_usage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            process = ctypes.windll.kernel32.GetCurrentProcess()
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(
                process, ctypes.byref(counters), counters.cb
            )
            if ok:
                return int(counters.peak_working_set_size), "windows_peak_working_set"
        except Exception:  # noqa: BLE001 - measurement must not affect the probe
            pass

    status_path = "/proc/self/status"
    try:
        for line in Path(status_path).read_text(encoding="utf-8").splitlines():
            if line.startswith("VmHWM:") or line.startswith("VmRSS:"):
                value = line.split()[1]
                return int(value) * 1024, f"linux_{line.split(':', 1)[0].lower()}"
    except Exception:  # noqa: BLE001 - measurement must not affect the probe
        pass
    return None, None


def value_or_none(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def source_index(dt: Any, index_by_dt: dict[str, int]) -> int | None:
    return index_by_dt.get(str(dt))


def candidate_state(item: Any) -> Any:
    for name in ("state", "status", "confirmed", "is_confirmed", "closed", "done"):
        if hasattr(item, name):
            value = getattr(item, name)
            if value is not None:
                return value_or_none(value)
    return None


def normalize_item(kind: str, item: Any, index_by_dt: dict[str, int]) -> dict[str, Any]:
    if kind == "fx":
        start_dt = getattr(item, "dt", None)
        end_dt = start_dt
        direction = None
        mark = value_or_none(getattr(item, "mark", None))
        geometry = {
            "high": value_or_none(getattr(item, "high", None)),
            "low": value_or_none(getattr(item, "low", None)),
        }
    elif kind == "bi":
        start_dt = getattr(item, "sdt", None)
        end_dt = getattr(item, "edt", None)
        direction = value_or_none(getattr(item, "direction", None))
        mark = None
        geometry = {
            "high": value_or_none(getattr(item, "high", None)),
            "low": value_or_none(getattr(item, "low", None)),
        }
    else:
        start_dt = getattr(item, "sdt", None)
        end_dt = getattr(item, "edt", None)
        direction = value_or_none(getattr(item, "direction", None))
        mark = None
        geometry = {
            "zg": value_or_none(getattr(item, "zg", None)),
            "zd": value_or_none(getattr(item, "zd", None)),
        }

    source_start = str(start_dt)
    source_end = str(end_dt)
    source_start_index = source_index(start_dt, index_by_dt)
    source_end_index = source_index(end_dt, index_by_dt)
    identity_payload = {
        "kind": kind,
        "direction": direction,
        "mark": mark,
        "source_start": source_start,
        "source_end": source_end,
        "price_basis_id": PRICE_BASIS_ID,
    }
    return {
        "kind": kind,
        "direction": direction,
        "mark": mark,
        "source_start": source_start,
        "source_end": source_end,
        "source_start_index": source_start_index,
        "source_end_index": source_end_index,
        "geometry": geometry,
        "engine_state": candidate_state(item),
        "stable_id_candidate": json_digest(identity_payload),
        "identity_payload": identity_payload,
    }


def snapshot(rows: list[dict[str, Any]]) -> dict[str, Any]:
    index_by_dt = {str(row["dt"]): row["index"] for row in rows}
    engine = CZSC(bars_from_rows(rows))
    structures = {
        "fx": [normalize_item("fx", item, index_by_dt) for item in engine.fx_list],
        "bi": [normalize_item("bi", item, index_by_dt) for item in engine.bi_list],
        "zs": [normalize_item("zs", item, index_by_dt) for item in engine.zs_list],
    }
    return {
        "status": "ok",
        "raw_bars": len(engine.bars_raw),
        "structures": structures,
        "counts": {kind: len(items) for kind, items in structures.items()},
    }


def safe_snapshot(rows: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        return snapshot(rows)
    except Exception as exc:  # noqa: BLE001 - the probe records malformed/short-input behavior
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def annotate_prefix_ledger(rows: list[dict[str, Any]]) -> dict[str, Any]:
    snapshots: dict[str, dict[str, Any]] = {}
    for end in range(MIN_PREFIX, len(rows) + 1):
        current = safe_snapshot(rows[:end])
        current["prefix_end_index"] = end - 1
        current["prefix_end_bar_id"] = f"{rows[end - 1]['dt'].isoformat()}#{rows[end - 1]['index']:04d}"
        snapshots[str(end)] = current

    all_prefixes = list(range(MIN_PREFIX, len(rows) + 1))
    for end in all_prefixes:
        current = snapshots[str(end)]
        if current.get("status") != "ok":
            continue
        previous = snapshots.get(str(end - 1), {})
        previous_by_id = {
            item["stable_id_candidate"]: item
            for values in previous.get("structures", {}).values()
            for item in values
        }
        for values in current["structures"].values():
            for item in values:
                identity = item["stable_id_candidate"]
                item["first_seen_prefix"] = next(
                    (
                        prefix
                        for prefix in all_prefixes
                        if prefix <= end and snapshots[str(prefix)].get("status") == "ok"
                        and any(candidate["stable_id_candidate"] == identity for candidate in snapshots[str(prefix)]["structures"][item["kind"]])
                    ),
                    end,
                )
                item["last_seen_prefix"] = end
                item["changed_since_previous_prefix"] = bool(
                    identity in previous_by_id
                    and previous_by_id[identity]["geometry"] != item["geometry"]
                )
                item["removed_since_previous_prefix"] = False

        previous_ids = set(previous_by_id)
        current_ids = {
            item["stable_id_candidate"]
            for values in current["structures"].values()
            for item in values
        }
        current["removed_since_previous_prefix"] = sorted(previous_ids - current_ids)

    return {
        "prefix_start": MIN_PREFIX,
        "prefix_end": len(rows),
        "snapshots": snapshots,
        "semantic_digest": json_digest(snapshots),
    }


def project_before_cutoff(snapshot_value: dict[str, Any], cutoff: int) -> dict[str, Any]:
    projected: dict[str, list[dict[str, Any]]] = {"fx": [], "bi": [], "zs": []}
    if snapshot_value.get("status") != "ok":
        return projected
    for kind, values in snapshot_value["structures"].items():
        projected[kind] = [
            item for item in values
            if item.get("source_end_index") is not None and item["source_end_index"] <= cutoff
        ]
    return projected


def compare_future_suffix(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for cutoff in SUFFIX_CUTOFFS:
        baseline = safe_snapshot(rows[:cutoff])
        normal_full = safe_snapshot(rows)
        mutated_full = safe_snapshot(mutate_suffix(rows, cutoff))
        baseline_projected = project_before_cutoff(baseline, cutoff - 1)
        normal_projected = project_before_cutoff(normal_full, cutoff - 1)
        mutated_projected = project_before_cutoff(mutated_full, cutoff - 1)

        def by_id(value: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
            return {
                item["stable_id_candidate"]: item
                for items in value.values()
                for item in items
            }

        base_ids = by_id(baseline_projected)
        normal_ids = by_id(normal_projected)
        mutated_ids = by_id(mutated_projected)

        def classify(other: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
            return {
                "unchanged": sorted(identity for identity in base_ids.keys() & other.keys() if base_ids[identity] == other[identity]),
                "changed": sorted(identity for identity in base_ids.keys() & other.keys() if base_ids[identity] != other[identity]),
                "removed": sorted(base_ids.keys() - other.keys()),
                "new": sorted(other.keys() - base_ids.keys()),
            }

        results.append(
            {
                "cutoff": cutoff,
                "normal_suffix": classify(normal_ids),
                "future_only_mutation": classify(mutated_ids),
                "baseline_digest": json_digest(baseline_projected),
                "normal_projected_digest": json_digest(normal_projected),
                "mutated_projected_digest": json_digest(mutated_projected),
            }
        )
    return results


def volume_probe(rows: list[dict[str, Any]]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for label, volume in (("positive", 100.0), ("true_zero", 0.0), ("unknown", None)):
        result = safe_snapshot(make_rows(len(rows), volume))
        results[label] = {
            "status": result.get("status"),
            "digest": json_digest(result) if result.get("status") == "ok" else None,
            "counts": result.get("counts"),
            "error_type": result.get("error_type"),
            "error": result.get("error"),
        }
    return results


def resource_probe(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cold_start = time.perf_counter_ns()
    cold = subprocess.run(
        [sys.executable, "-c", "import czsc; print(czsc.__version__ if hasattr(czsc, '__version__') else 'unknown')"],
        check=False,
        capture_output=True,
        text=True,
    )
    cold_ms = (time.perf_counter_ns() - cold_start) / 1_000_000
    warm_start = time.perf_counter_ns()
    full = safe_snapshot(rows)
    warm_ms = (time.perf_counter_ns() - warm_start) / 1_000_000
    rss_bytes, rss_method = current_peak_rss_bytes()
    return {
        "cold_import_ms": round(cold_ms, 3),
        "cold_import_exit_code": cold.returncode,
        "cold_import_output": cold.stdout.strip(),
        "warm_full_run_ms": round(warm_ms, 3),
        "warm_full_run_status": full.get("status"),
        "peak_rss_bytes_observed": rss_bytes,
        "peak_rss_method": rss_method,
    }


def main() -> None:
    rows = make_rows()
    ledger = annotate_prefix_ledger(rows)
    suffix = compare_future_suffix(rows)
    volumes = volume_probe(rows)
    resources = resource_probe(rows)
    environment = {
        "platform": platform.platform(),
        "sys_platform": sys.platform,
        "python": sys.version,
        "implementation_cache_tag": getattr(sys.implementation, "cache_tag", None),
        "python_executable": str(Path(sys.executable)),
    }
    semantic_payload = {
        "fixture_id": "r4c-m1-r4-causal-300-bars-v1",
        "price_basis_id": PRICE_BASIS_ID,
        "prefix_ledger": ledger,
        "future_suffix": suffix,
        "volume_probe": volumes,
    }
    output = {
        "schema": "r4c-m1-r4-causal-probe-v1",
        "engine": "czsc",
        "version": "1.0.1",
        "source_commit": "90372af035f01ed9f05070eadddd265b91c84d24",
        "environment": environment,
        "semantic_digest": json_digest(semantic_payload),
        "semantic": semantic_payload,
        "resource": resources,
        "causal_status": "NOT_ESTABLISHED",
        "stable_id_status": "CANDIDATE_VALIDATION_ONLY",
        "application_integration": "NOT_RUN",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()

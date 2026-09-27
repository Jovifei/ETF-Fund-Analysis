from __future__ import annotations

import json
import platform
import sys
import time
from collections import Counter, defaultdict
from typing import Any

from validate_r4c_m1_r4_causal import (
    FIXTURE_SIZE,
    MIN_PREFIX,
    PRICE_BASIS_ID,
    annotate_prefix_ledger,
    current_peak_rss_bytes,
    json_digest,
    make_rows,
    safe_snapshot,
)


SOURCE_COMMIT = "90372af035f01ed9f05070eadddd265b91c84d24"
DIALECT_ID = "r4c-observed-revision-v1"
RESOURCE_BUDGET = {
    "warm_300_ms_max": 250.0,
    "prefix_sweep_ms_max": 2000.0,
    "peak_rss_bytes_max": 384 * 1024 * 1024,
}


def observation_id(rows: list[dict[str, Any]], cutoff: int) -> str:
    input_payload = [
        {
            "index": row["index"],
            "dt": row["dt"].isoformat(),
            "open": row["open"],
            "close": row["close"],
            "high": row["high"],
            "low": row["low"],
            "volume": row["volume"],
            "amount": row["amount"],
        }
        for row in rows[:cutoff]
    ]
    return json_digest(
        {
            "instrument": "R4_SYNTHETIC",
            "interval": "D",
            "cutoff": cutoff,
            "input_hash": json_digest(input_payload),
            "price_basis_id": PRICE_BASIS_ID,
            "engine_id": "czsc",
            "engine_version": "1.0.1",
            "dialect_id": DIALECT_ID,
            "config_id": "default-czsc-r4",
        }
    )


def build_history(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ledger = annotate_prefix_ledger(rows)
    previous: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    collisions: defaultdict[str, set[str]] = defaultdict(set)
    transition_counts: Counter[str] = Counter()
    reappearances = 0

    for cutoff in range(MIN_PREFIX, len(rows) + 1):
        snapshot = ledger["snapshots"][str(cutoff)]
        current: dict[str, dict[str, Any]] = {
            item["stable_id_candidate"]: item
            for items in snapshot.get("structures", {}).values()
            for item in items
        }
        obs_id = observation_id(rows, cutoff)
        for key, item in current.items():
            geometry_payload = {
                "geometry": item["geometry"],
                "engine_state": item["engine_state"],
            }
            revision = json_digest(
                {
                    "observation_id": obs_id,
                    "structure_key": key,
                    "payload": geometry_payload,
                }
            )
            payload_hash = json_digest(geometry_payload)
            collisions[revision].add(payload_hash)
            if key not in seen:
                status = "OBSERVED_NEW"
            elif key not in previous:
                status = "OBSERVED_NEW"
                reappearances += 1
            elif previous[key]["payload_hash"] == payload_hash:
                status = "OBSERVED_UNCHANGED"
            else:
                status = "OBSERVED_CHANGED"
            transition_counts[status] += 1
            records.append(
                {
                    "cutoff": cutoff,
                    "observation_id": obs_id,
                    "structure_key": key,
                    "revision_id": revision,
                    "payload_hash": payload_hash,
                    "status": status,
                    "kind": item["kind"],
                    "source_start": item["source_start"],
                    "source_end": item["source_end"],
                }
            )

        for key, prior in previous.items():
            if key not in current:
                transition_counts["OBSERVED_ABSENT"] += 1
                records.append(
                    {
                        "cutoff": cutoff,
                        "observation_id": obs_id,
                        "structure_key": key,
                        "revision_id": None,
                        "prior_revision_id": prior["revision_id"],
                        "status": "OBSERVED_ABSENT",
                    }
                )

        previous = {
            key: {
                "revision_id": next(
                    item["revision_id"]
                    for item in records[::-1]
                    if item.get("cutoff") == cutoff and item.get("structure_key") == key and item.get("revision_id")
                ),
                "payload_hash": json_digest({"geometry": item["geometry"], "engine_state": item["engine_state"]}),
            }
            for key, item in current.items()
        }
        seen.update(current)

    collision_count = sum(1 for values in collisions.values() if len(values) > 1)
    return {
        "observation_count": len({record["observation_id"] for record in records}),
        "record_count": len(records),
        "revision_count": len({record["revision_id"] for record in records if record.get("revision_id")}),
        "transition_counts": dict(sorted(transition_counts.items())),
        "reappearances": reappearances,
        "collision_count": collision_count,
        "history_digest": json_digest(records),
        "sample": records[:3] + records[-3:],
    }


def measure(rows: list[dict[str, Any]]) -> dict[str, Any]:
    warm_start = time.perf_counter_ns()
    safe_snapshot(rows)
    warm_ms = (time.perf_counter_ns() - warm_start) / 1_000_000
    sweep_start = time.perf_counter_ns()
    result = build_history(rows)
    sweep_ms = (time.perf_counter_ns() - sweep_start) / 1_000_000
    rss_bytes, rss_method = current_peak_rss_bytes()
    budget = {
        "warm_300_ms": round(warm_ms, 3),
        "prefix_sweep_ms": round(sweep_ms, 3),
        "peak_rss_bytes": rss_bytes,
        "peak_rss_method": rss_method,
        "warm_pass": warm_ms <= RESOURCE_BUDGET["warm_300_ms_max"],
        "prefix_sweep_pass": sweep_ms <= RESOURCE_BUDGET["prefix_sweep_ms_max"],
        "peak_rss_pass": rss_bytes is not None and rss_bytes <= RESOURCE_BUDGET["peak_rss_bytes_max"],
    }
    return {"history": result, "budget": budget}


def main() -> None:
    rows = make_rows(FIXTURE_SIZE)
    first = measure(rows)
    second = measure(rows)
    output = {
        "schema": "r4c-m1-r5-observed-revision-v1",
        "engine": "czsc",
        "engine_version": "1.0.1",
        "source_commit": SOURCE_COMMIT,
        "dialect_id": DIALECT_ID,
        "environment": {
            "platform": platform.platform(),
            "sys_platform": sys.platform,
            "python": sys.version,
        },
        "same_input_same_history": first["history"]["history_digest"] == second["history"]["history_digest"],
        "history": first["history"],
        "budget": first["budget"],
        "resource_budget_proposal": RESOURCE_BUDGET,
        "engine_confirmation": "unknown",
        "application_observation_status": "observed",
        "qualification": "EVIDENCE_ONLY_CLOSED_BLOCKED",
    }
    output["semantic_digest"] = json_digest(
        {
            "schema": output["schema"],
            "engine": output["engine"],
            "engine_version": output["engine_version"],
            "source_commit": output["source_commit"],
            "dialect_id": output["dialect_id"],
            "same_input_same_history": output["same_input_same_history"],
            "history": output["history"],
            "resource_budget_proposal": output["resource_budget_proposal"],
            "engine_confirmation": output["engine_confirmation"],
            "application_observation_status": output["application_observation_status"],
        }
    )
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()

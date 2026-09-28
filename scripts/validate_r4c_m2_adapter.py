from __future__ import annotations

import hashlib
import importlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "tests"))

import test_chan_m2_contract as fixture  # noqa: E402


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def observation_payload(observation: Any) -> dict[str, Any]:
    return {
        "observation_id": observation.observation_id,
        "instrument": observation.instrument,
        "interval": observation.interval,
        "series_id": observation.series_id,
        "price_basis_id": observation.price_basis_id,
        "adjustment_version": observation.adjustment_version,
        "input_revision_id": observation.input_revision_id,
        "settlement_status": observation.settlement_status,
        "config_id": observation.config_id,
        "input_hash": observation.input_hash,
        "cutoff": observation.cutoff,
        "cutoff_bar_id": observation.cutoff_bar_id,
        "engine_id": observation.engine_id,
        "engine_version": observation.engine_version,
        "dialect_id": observation.dialect_id,
        "engine_confirmation": observation.engine_confirmation,
        "application_observation_status": observation.application_observation_status,
        "structures": [
            {
                "kind": item.kind,
                "direction": item.direction,
                "mark": item.mark,
                "source_start": item.source_start,
                "source_end": item.source_end,
                "source_start_bar_id": item.source_start_bar_id,
                "source_end_bar_id": item.source_end_bar_id,
                "geometry": item.geometry_payload(),
                "engine_state": item.engine_state,
                "structure_key": item.structure_key,
                "revision_id": item.revision_id,
            }
            for item in observation.structures
        ],
    }


def main() -> None:
    adapter_module = importlib.import_module("app.research.chan_adapter")
    contract = importlib.import_module("app.research.chan_contract")
    installed_version = adapter_module.installed_czsc_version()
    if installed_version != "1.0.1":
        raise SystemExit(f"expected exact CZSC 1.0.1, found {installed_version!r}")

    adapter_module.load_czsc_bindings()
    rows = fixture._rows(300)
    prepared = fixture._prepared(contract, rows)
    adapter = adapter_module.ChanAdapter()
    warm_start = time.perf_counter()
    first = adapter.observe(prepared)
    warm_300_ms = (time.perf_counter() - warm_start) * 1000

    repeated = adapter_module.ChanAdapter().observe(prepared)
    first_payload = observation_payload(first)
    repeated_payload = observation_payload(repeated)
    same_input_same_output = first_payload == repeated_payload
    semantic_digest = hashlib.sha256(canonical_json(first_payload).encode("utf-8")).hexdigest()

    prepare_start = time.perf_counter()
    prefixes = [
        fixture._prepared(contract, rows[:prefix_length])
        for prefix_length in range(20, len(rows) + 1)
    ]
    prefix_preparation_ms = (time.perf_counter() - prepare_start) * 1000

    sweep_start = time.perf_counter()
    for prefix_length, prefix in enumerate(prefixes, start=20):
        observation = adapter.observe(prefix)
        if observation.cutoff != prefix_length:
            raise SystemExit(f"unexpected prefix cutoff {observation.cutoff}, expected {prefix_length}")
    prefix_sweep_ms = (time.perf_counter() - sweep_start) * 1000
    peak_rss_bytes = fixture._peak_rss_bytes()
    budget = {
        "warm_300_ms": warm_300_ms,
        "warm_300_ms_max": 250.0,
        "warm_300_pass": warm_300_ms <= 250.0,
        "prefix_sweep_ms": prefix_sweep_ms,
        "prefix_sweep_ms_max": 2000.0,
        "prefix_sweep_pass": prefix_sweep_ms <= 2000.0,
        "prefix_input_preparation_ms": prefix_preparation_ms,
        "peak_rss_bytes": peak_rss_bytes,
        "peak_rss_bytes_max": 384 * 1024 * 1024,
        "peak_rss_pass": peak_rss_bytes is not None and peak_rss_bytes <= 384 * 1024 * 1024,
    }

    counts: dict[str, int] = {}
    for item in first.structures:
        counts[item.kind] = counts.get(item.kind, 0) + 1

    output = {
        "schema": "r4c-m2-adapter-parity-v1",
        "engine": "czsc",
        "engine_version": installed_version,
        "environment": {
            "platform": platform.platform(),
            "sys_platform": sys.platform,
            "python": sys.version,
        },
        "fixture": {"bar_count": prepared.cutoff, "cutoff_bar_id": prepared.cutoff_bar_id},
        "same_input_same_output": same_input_same_output,
        "structure_counts": counts,
        "budget": budget,
        "engine_confirmation": first.engine_confirmation,
        "application_observation_status": first.application_observation_status,
        "semantic_digest": semantic_digest,
        "qualification": "EVIDENCE_ONLY_CLOSED_BLOCKED",
    }
    if not same_input_same_output:
        raise SystemExit("same-input adapter runs produced different normalized observations")
    if not all((budget["warm_300_pass"], budget["prefix_sweep_pass"], budget["peak_rss_pass"])):
        raise SystemExit("M1 resource budget was exceeded or peak RSS could not be measured")
    if first.engine_confirmation != "unknown" or first.application_observation_status != "observed":
        raise SystemExit("adapter crossed its selected disabled-observation contract")
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

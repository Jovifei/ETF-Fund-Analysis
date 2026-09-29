from __future__ import annotations

import importlib
import json
import sys
import time
import tomllib
from datetime import date, timedelta
from importlib.util import find_spec
from pathlib import Path

import pytest


def _module(name: str):
    spec = find_spec(name)
    assert spec is not None, f"M2 contract module is not implemented: {name}"
    return importlib.import_module(name)


def _rows(count: int = 40, *, volume: float | None = 100.0) -> list[dict[str, object]]:
    start = date(2026, 1, 5)
    rows: list[dict[str, object]] = []
    for index in range(count):
        phase = (index // 5) % 2
        close = 100.0 + (3.0 if phase == 0 else -3.0) + (index // 50) * 0.2
        open_price = close - 1.0 if phase == 0 else close + 1.0
        rows.append(
            {
                "source_bar_id": f"bar-{index:04d}",
                "timestamp": start + timedelta(days=index),
                "open": open_price,
                "high": max(open_price, close) + 1.0,
                "low": min(open_price, close) - 1.0,
                "close": close,
                "volume": volume,
                "amount": None if volume is None else volume * close,
            }
        )
    return rows


def _prepared(contract, rows=None, **overrides):
    values = {
        "instrument": "510300.SH",
        "interval": "D",
        "series_id": "series-510300-raw-r1",
        "price_basis_id": "basis-raw-v1",
        "adjustment_version": "none-v1",
        "input_revision_id": "input-revision-001",
        "settlement_status": "settled",
        "config_id": "default-czsc-r4-v1",
        "bars": _rows() if rows is None else rows,
    }
    values.update(overrides)
    return contract.prepare_research_input(**values)


def _structure(contract, prepared, *, high: float = 103.0):
    return contract.build_structure_evidence(
        prepared,
        observation_id=contract.build_observation_id(prepared),
        kind="fx",
        direction=None,
        mark="顶分型",
        source_start=str(prepared.bars[10].timestamp),
        source_end=str(prepared.bars[10].timestamp),
        source_start_bar_id=prepared.bars[10].source_bar_id,
        source_end_bar_id=prepared.bars[10].source_bar_id,
        geometry={"high": high, "low": 101.0},
        engine_state=None,
    )


def test_czsc_is_pinned_only_in_the_r4c_optional_extra():
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    optional = data["project"]["optional-dependencies"]
    assert optional["r4c"] == ["czsc==1.0.1"]
    assert "chanlun>=2606.73" in optional["market"]
    assert "czsc" not in data["project"].get("dependencies", [])


def test_input_identity_binds_series_basis_revision_and_actual_source_bars():
    contract = _module("app.research.chan_contract")
    first = _prepared(contract)
    repeated = _prepared(contract)
    assert contract.build_observation_id(first) == contract.build_observation_id(repeated)

    changed_rows = _rows()
    changed_rows[0]["close"] = float(changed_rows[0]["close"]) + 0.25
    corrected = _prepared(contract, changed_rows)
    revised = _prepared(contract, input_revision_id="input-revision-002")
    other_basis = _prepared(contract, price_basis_id="basis-split-research-v1")
    other_series = _prepared(contract, series_id="series-510300-split-r1")
    temporary = _prepared(contract, settlement_status="temporary")

    identity = contract.build_observation_id(first)
    assert contract.build_observation_id(corrected) != identity
    assert contract.build_observation_id(revised) != identity
    assert contract.build_observation_id(other_basis) != identity
    assert contract.build_observation_id(other_series) != identity
    assert contract.build_observation_id(temporary) != identity
    assert first.cutoff_bar_id == "bar-0039"
    assert first.input_hash
    with pytest.raises(TypeError):
        first._endpoint_index["2026-01-05 00:00:00"] = ("forged", 0)


def test_identity_carrying_records_require_validating_factories():
    contract = _module("app.research.chan_contract")
    for record_type in (
        contract.PreparedResearchInput,
        contract.StructureEvidence,
        contract.ResearchObservation,
    ):
        with pytest.raises(TypeError):
            record_type()


def test_research_input_rejects_unknown_volume_but_preserves_true_zero():
    contract = _module("app.research.chan_contract")
    unknown_rows = _rows(volume=None)
    with pytest.raises(contract.ChanContractError) as exc:
        _prepared(contract, unknown_rows)
    assert exc.value.code == "unknown_volume"

    zero_rows = _rows(volume=0.0)
    zero = _prepared(contract, zero_rows)
    assert zero.bars[0].volume == 0.0
    assert zero.bars[0].amount == 0.0

    unknown_amount_rows = _rows()
    unknown_amount_rows[0]["amount"] = None
    with pytest.raises(contract.ChanContractError) as missing_amount:
        _prepared(contract, unknown_amount_rows)
    assert missing_amount.value.code == "unknown_amount"


def test_research_input_rejects_duplicate_or_unordered_source_bars():
    contract = _module("app.research.chan_contract")
    duplicate = _rows()
    duplicate[1]["source_bar_id"] = duplicate[0]["source_bar_id"]
    with pytest.raises(contract.ChanContractError) as exc:
        _prepared(contract, duplicate)
    assert exc.value.code == "duplicate_source_bar_id"

    unordered = _rows()
    unordered[5], unordered[6] = unordered[6], unordered[5]
    with pytest.raises(contract.ChanContractError) as exc:
        _prepared(contract, unordered)
    assert exc.value.code == "unordered_source_bars"


def test_structure_key_uses_selected_namespace_while_revision_tracks_geometry():
    contract = _module("app.research.chan_contract")
    prepared = _prepared(contract)
    original = _structure(contract, prepared, high=103.0)
    changed_geometry = _structure(contract, prepared, high=104.0)
    changed_config_input = _prepared(contract, config_id="another-config-v1")
    namespaced = _structure(contract, changed_config_input, high=103.0)

    assert original.structure_key == changed_geometry.structure_key
    assert original.revision_id != changed_geometry.revision_id
    assert original.structure_key != namespaced.structure_key


def test_structure_source_bar_ids_must_match_causal_endpoint_timestamps():
    contract = _module("app.research.chan_contract")
    prepared = _prepared(contract)
    with pytest.raises(contract.ChanContractError) as exc:
        contract.build_structure_evidence(
            prepared,
            observation_id=contract.build_observation_id(prepared),
            kind="fx",
            direction=None,
            mark="顶分型",
            source_start=str(prepared.bars[10].timestamp),
            source_end=str(prepared.bars[10].timestamp),
            source_start_bar_id=prepared.bars[11].source_bar_id,
            source_end_bar_id=prepared.bars[10].source_bar_id,
            geometry={"high": 103.0, "low": 101.0},
            engine_state=None,
        )
    assert exc.value.code == "source_endpoint_mismatch"


def test_structure_key_and_replay_bind_changed_source_ids_at_same_timestamps():
    contract = _module("app.research.chan_contract")
    replay_module = _module("app.research.chan_replay")
    original_input = _prepared(contract)
    original_structure = _structure(contract, original_input)

    corrected_rows = _rows()
    corrected_rows[10]["source_bar_id"] = "bar-0010-corrected"
    corrected_input = _prepared(contract, corrected_rows, input_revision_id="input-revision-002")
    corrected_structure = _structure(contract, corrected_input)
    assert corrected_structure.source_start == original_structure.source_start
    assert corrected_structure.source_start_bar_id != original_structure.source_start_bar_id
    assert corrected_structure.structure_key != original_structure.structure_key

    replay = replay_module.ObservedRevisionReplay()
    replay.append(contract.make_observation(original_input, [original_structure]))
    transitions = replay.append(contract.make_observation(corrected_input, [corrected_structure]))
    assert {item.status for item in transitions} == {"OBSERVED_NEW", "OBSERVED_ABSENT"}


def test_r5_namespace_fields_change_only_the_intended_identity():
    contract = _module("app.research.chan_contract")
    prepared = _prepared(contract)
    structure = _structure(contract, prepared)
    observation_id = contract.build_observation_id(prepared)
    structure_key = structure.structure_key

    observation_variants = (
        _prepared(contract, instrument="510500.SH"),
        _prepared(contract, interval="W"),
        _prepared(contract, series_id="another-series"),
        _prepared(contract, price_basis_id="another-basis"),
        _prepared(contract, adjustment_version="another-adjustment"),
        _prepared(contract, input_revision_id="another-input-revision"),
        _prepared(contract, settlement_status="temporary"),
        _prepared(contract, config_id="another-config"),
    )
    assert all(contract.build_observation_id(item) != observation_id for item in observation_variants)

    instrument_variant = _prepared(contract, instrument="510500.SH")
    basis_variant = _prepared(contract, price_basis_id="another-basis")
    config_variant = _prepared(contract, config_id="another-config")
    assert _structure(contract, instrument_variant).structure_key != structure_key
    assert _structure(contract, basis_variant).structure_key != structure_key
    assert _structure(contract, config_variant).structure_key != structure_key

    source_variant = contract.build_structure_evidence(
        prepared,
        observation_id=observation_id,
        kind="fx",
        direction=None,
        mark="顶分型",
        source_start="2026-01-15 00:00:00",
        source_end="2026-01-16 00:00:00",
        source_start_bar_id="bar-0010",
        source_end_bar_id="bar-0011",
        geometry={"high": 103.0, "low": 101.0},
        engine_state=None,
    )
    assert source_variant.structure_key != structure_key


def test_config_keeps_selected_engine_disabled_after_m3_persistence():
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / "config" / "chan_research.json").read_text(encoding="utf-8"))
    assert config["enabled"] is False
    assert config["qualification_status"] == "BLOCKED"
    assert config["selection_status"] == "SELECTED_DISABLED"
    assert config["engine_id"] == "czsc"
    assert config["selection_contract"]["engine_confirmation"] == "unknown"
    assert config["reason_codes"] == [
        "RUNTIME_INTEGRATION_DISABLED",
        "USER_FACING_READ_MODEL_NOT_INTEGRATED",
    ]


def test_append_only_replay_records_changed_absent_and_reappearing_observations():
    contract = _module("app.research.chan_contract")
    replay_module = _module("app.research.chan_replay")
    replay = replay_module.ObservedRevisionReplay()

    first_input = _prepared(contract)
    first_structure = _structure(contract, first_input, high=103.0)
    first = contract.make_observation(first_input, [first_structure])
    first_events = replay.append(first)
    assert first.cutoff_at == first_input.cutoff_at
    assert [event.status for event in first_events] == ["OBSERVED_NEW"]
    first_history = replay.history
    first_event = first_history[0]

    second_input = _prepared(contract, input_revision_id="input-revision-002")
    changed_structure = _structure(contract, second_input, high=104.0)
    second = contract.make_observation(second_input, [changed_structure])
    assert second.cutoff_at == first.cutoff_at
    second_events = replay.append(second)
    assert [event.status for event in second_events] == ["OBSERVED_CHANGED"]
    assert replay.history[0] is first_event
    assert replay.history[0].revision_id == first_events[0].revision_id

    absent_input = _prepared(contract, input_revision_id="input-revision-003")
    absent = contract.make_observation(absent_input, [])
    absent_events = replay.append(absent)
    assert [event.status for event in absent_events] == ["OBSERVED_ABSENT"]
    next_absent_input = _prepared(contract, input_revision_id="input-revision-004")
    next_absent = contract.make_observation(next_absent_input, [])
    assert replay.append(next_absent) == ()

    return_input = _prepared(contract, input_revision_id="input-revision-005")
    returned = contract.make_observation(return_input, [_structure(contract, return_input, high=104.0)])
    returned_events = replay.append(returned)
    assert [event.status for event in returned_events] == ["OBSERVED_NEW"]
    assert returned_events[0].reappearance is True
    assert replay.observations == (first, second, absent, next_absent, returned)
    assert replay.history[0] is first_event


def test_replay_rejects_same_count_observation_with_earlier_cutoff_time():
    contract = _module("app.research.chan_contract")
    replay_module = _module("app.research.chan_replay")
    replay = replay_module.ObservedRevisionReplay()

    current_input = _prepared(contract)
    replay.append(contract.make_observation(current_input, []))
    earlier_rows = _rows()
    for row in earlier_rows:
        row["timestamp"] = row["timestamp"] - timedelta(days=1)
    earlier_input = _prepared(contract, earlier_rows, input_revision_id="input-revision-earlier")
    assert earlier_input.cutoff == current_input.cutoff
    assert earlier_input.cutoff_at < current_input.cutoff_at

    with pytest.raises(contract.ChanContractError) as exc:
        replay.append(contract.make_observation(earlier_input, []))
    assert exc.value.code == "observation_time_reversed"


def test_duplicate_factory_failure_does_not_affect_other_replay_stream():
    contract = _module("app.research.chan_contract")
    replay_module = _module("app.research.chan_replay")
    replay = replay_module.ObservedRevisionReplay()

    invalid_input = _prepared(contract)
    duplicate_structure = _structure(contract, invalid_input)
    with pytest.raises(contract.ChanContractError) as exc:
        contract.make_observation(invalid_input, [duplicate_structure, duplicate_structure])
    assert exc.value.code == "duplicate_structure_key"
    assert replay.observations == ()
    assert replay.history == ()

    other_stream = _prepared(contract, instrument="510500.SH")
    valid_observation = contract.make_observation(other_stream, [])
    assert replay.append(valid_observation) == ()
    assert replay.observations == (valid_observation,)


def test_empty_observation_is_stored_without_structure_transitions():
    contract = _module("app.research.chan_contract")
    replay_module = _module("app.research.chan_replay")
    replay = replay_module.ObservedRevisionReplay()
    prepared = _prepared(contract)
    observation = contract.make_observation(prepared, [])
    assert observation.structures == ()
    assert observation.engine_confirmation == "unknown"
    assert observation.application_observation_status == "observed"
    assert replay.append(observation) == ()
    assert replay.observations == (observation,)


def test_make_observation_rejects_duplicate_structure_keys():
    contract = _module("app.research.chan_contract")
    prepared = _prepared(contract)
    structure = _structure(contract, prepared)

    with pytest.raises(contract.ChanContractError) as exc:
        contract.make_observation(prepared, [structure, structure])
    assert exc.value.code == "duplicate_structure_key"


def test_make_observation_canonicalizes_structure_order_for_idempotent_replay():
    contract = _module("app.research.chan_contract")
    replay_module = _module("app.research.chan_replay")
    prepared = _prepared(contract)
    fx = _structure(contract, prepared)
    bi = contract.build_structure_evidence(
        prepared,
        observation_id=contract.build_observation_id(prepared),
        kind="bi",
        direction="up",
        mark=None,
        source_start=prepared.bars[10].timestamp.isoformat(sep=" "),
        source_end=prepared.bars[11].timestamp.isoformat(sep=" "),
        source_start_bar_id=prepared.bars[10].source_bar_id,
        source_end_bar_id=prepared.bars[11].source_bar_id,
        geometry={"high": 104.0, "low": 98.0},
        engine_state=None,
    )

    first = contract.make_observation(prepared, [fx, bi])
    reordered = contract.make_observation(prepared, [bi, fx])
    assert first == reordered
    assert [item.structure_key for item in first.structures] == sorted(
        item.structure_key for item in first.structures
    )

    replay = replay_module.ObservedRevisionReplay()
    replay.append(first)
    prior_history = replay.history
    assert replay.append(reordered) == ()
    assert replay.observations == (first,)
    assert replay.history == prior_history


def test_replay_rejects_conflicting_evidence_for_same_observation_id_atomically():
    contract = _module("app.research.chan_contract")
    replay_module = _module("app.research.chan_replay")
    prepared = _prepared(contract)
    empty = contract.make_observation(prepared, [])
    populated = contract.make_observation(prepared, [_structure(contract, prepared)])
    assert empty.observation_id == populated.observation_id
    assert empty != populated

    replay = replay_module.ObservedRevisionReplay()
    replay.append(empty)
    before = (
        replay.observations,
        replay.history,
        dict(replay._current),
        replay._seen_keys,
        replay._stream_identity,
    )
    with pytest.raises(contract.ChanContractError) as exc:
        replay.append(populated)
    assert exc.value.code == "observation_id_conflict"
    assert (
        replay.observations,
        replay.history,
        dict(replay._current),
        replay._seen_keys,
        replay._stream_identity,
    ) == before


def test_replay_stream_rejects_config_changes_but_allows_input_revision_and_settlement():
    contract = _module("app.research.chan_contract")
    replay_module = _module("app.research.chan_replay")
    prepared = _prepared(contract)
    replay = replay_module.ObservedRevisionReplay()
    replay.append(contract.make_observation(prepared, []))

    temporary = _prepared(
        contract,
        settlement_status="temporary",
        input_revision_id="temporary-revision",
    )
    assert replay.append(contract.make_observation(temporary, [])) == ()

    adjusted = _prepared(
        contract,
        adjustment_version="corporate-action-v2",
        input_revision_id="adjustment-revision",
    )
    before_adjustment = (replay.observations, replay.history, replay._stream_identity)
    with pytest.raises(contract.ChanContractError) as adjustment_exc:
        replay.append(contract.make_observation(adjusted, []))
    assert adjustment_exc.value.code == "replay_stream_mismatch"
    assert (replay.observations, replay.history, replay._stream_identity) == before_adjustment

    configured = _prepared(
        contract,
        config_id="another-config-v1",
        input_revision_id="config-revision",
    )
    before = (replay.observations, replay.history, replay._stream_identity)
    with pytest.raises(contract.ChanContractError) as exc:
        replay.append(contract.make_observation(configured, []))
    assert exc.value.code == "replay_stream_mismatch"
    assert (replay.observations, replay.history, replay._stream_identity) == before


def test_replay_stream_rejects_engine_or_dialect_namespace_changes(monkeypatch):
    contract = _module("app.research.chan_contract")
    replay_module = _module("app.research.chan_replay")
    prepared = _prepared(contract)
    replay = replay_module.ObservedRevisionReplay()
    replay.append(contract.make_observation(prepared, []))
    before = (replay.observations, replay.history, replay._stream_identity)

    monkeypatch.setattr(contract, "ENGINE_ID", "alternate-czsc")
    monkeypatch.setattr(contract, "ENGINE_VERSION", "9.9.9")
    monkeypatch.setattr(contract, "DIALECT_ID", "alternate-dialect-v1")
    alternate = contract.make_observation(prepared, [])
    with pytest.raises(contract.ChanContractError) as exc:
        replay.append(alternate)
    assert exc.value.code == "replay_stream_mismatch"
    assert (replay.observations, replay.history, replay._stream_identity) == before


def test_adapter_fails_closed_for_missing_or_wrong_distribution_version(monkeypatch):
    adapter_module = _module("app.research.chan_adapter")

    def importer_must_not_run(_name):
        raise AssertionError("CZSC importer ran before version was accepted")

    monkeypatch.setattr(adapter_module.importlib, "import_module", importer_must_not_run)

    def missing_distribution(_distribution):
        raise adapter_module.PackageNotFoundError("czsc")

    monkeypatch.setattr(adapter_module.importlib.metadata, "version", missing_distribution)
    with pytest.raises(adapter_module.ChanAdapterError) as missing:
        adapter_module.load_czsc_bindings()
    assert missing.value.code == "engine_dependency_missing"

    monkeypatch.setattr(adapter_module.importlib.metadata, "version", lambda _distribution: "1.0.2")
    with pytest.raises(adapter_module.ChanAdapterError) as wrong:
        adapter_module.load_czsc_bindings()
    assert wrong.value.code == "unsupported_engine_version"


def test_adapter_constructor_does_not_accept_unverified_binding_injection():
    adapter_module = _module("app.research.chan_adapter")
    with pytest.raises(TypeError):
        adapter_module.ChanAdapter(bindings_loader=lambda: adapter_module.CzscBindings("1.0.1", object, object, object))


def test_exact_pinned_engine_produces_observed_fx_bi_zs_without_confirmation_claim():
    adapter_module = _module("app.research.chan_adapter")
    contract = _module("app.research.chan_contract")
    version = adapter_module.installed_czsc_version()
    if version != "1.0.1":
        pytest.skip("exact optional CZSC 1.0.1 is not installed in this test environment")

    prepared = _prepared(contract, _rows(300))
    observation = adapter_module.ChanAdapter().observe(prepared)
    assert observation.engine_confirmation == "unknown"
    assert observation.application_observation_status == "observed"
    assert {item.kind for item in observation.structures} == {"fx", "bi", "zs"}
    assert {item.kind: sum(1 for row in observation.structures if row.kind == item.kind) for item in observation.structures} == {
        "fx": 49,
        "bi": 1,
        "zs": 1,
    }
    assert all(item.structure_key and item.revision_id for item in observation.structures)
    assert all(item.source_start_bar_id and item.source_end_bar_id for item in observation.structures)


def test_adapter_resolves_exact_engine_bindings_once_for_prefix_replay(monkeypatch):
    adapter_module = _module("app.research.chan_adapter")
    contract = _module("app.research.chan_contract")
    if adapter_module.installed_czsc_version() != "1.0.1":
        pytest.skip("exact optional CZSC 1.0.1 is not installed in this test environment")

    load_calls = 0

    original_loader = adapter_module.load_czsc_bindings

    def counted_loader():
        nonlocal load_calls
        load_calls += 1
        return original_loader()

    monkeypatch.setattr(adapter_module, "load_czsc_bindings", counted_loader)
    adapter = adapter_module.ChanAdapter()
    rows = _rows(24)
    for prefix_length in range(20, 25):
        adapter.observe(_prepared(contract, rows[:prefix_length]))

    assert load_calls == 1


def test_frozen_300_bar_resource_budget_remains_within_selected_m1_limits():
    adapter_module = _module("app.research.chan_adapter")
    contract = _module("app.research.chan_contract")
    version = adapter_module.installed_czsc_version()
    if version != "1.0.1":
        pytest.skip("exact optional CZSC 1.0.1 is not installed in this test environment")
    adapter_module.load_czsc_bindings()  # exclude one-time import from warm execution

    rows = _rows(300)
    adapter = adapter_module.ChanAdapter()
    full = _prepared(contract, rows)
    preparation_start = time.perf_counter()
    prefixes = [
        _prepared(contract, rows[:prefix_length])
        for prefix_length in range(20, 301)
    ]
    prefix_preparation_ms = (time.perf_counter() - preparation_start) * 1000
    warm_start = time.perf_counter()
    adapter.observe(full)
    warm_ms = (time.perf_counter() - warm_start) * 1000

    sweep_start = time.perf_counter()
    for prefix_length, prefix in enumerate(prefixes, start=20):
        observation = adapter.observe(prefix)
        assert observation.cutoff == prefix_length
    prefix_ms = (time.perf_counter() - sweep_start) * 1000
    combined_prefix_ms = prefix_preparation_ms + prefix_ms

    peak_rss_bytes = _peak_rss_bytes()
    assert warm_ms <= 250
    assert prefix_ms <= 2000
    assert combined_prefix_ms <= 2000
    assert peak_rss_bytes <= 384 * 1024 * 1024


def test_adapter_modules_do_not_import_provider_database_or_network_clients():
    _module("app.research.chan_contract")
    _module("app.research.chan_adapter")
    _module("app.research.chan_replay")
    root = Path(__file__).resolve().parents[1] / "app" / "research"
    forbidden = {"requests", "httpx", "sqlalchemy", "app.db", "app.providers"}
    for path in (root / "chan_contract.py", root / "chan_adapter.py", root / "chan_replay.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(f"import {name}" in source or f"from {name}" in source for name in forbidden), path.name

    route = (Path(__file__).resolve().parents[1] / "app" / "api" / "workbench_kline.py").read_text(encoding="utf-8")
    assert "ChanAdapter" not in route
    assert "chan_adapter" not in route


def _peak_rss_bytes() -> int:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("page_fault_count", wintypes.DWORD),
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
        psapi = ctypes.WinDLL("psapi.dll")
        kernel32 = ctypes.WinDLL("kernel32.dll")
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise AssertionError("Windows peak working set measurement failed")
        return int(counters.peak_working_set_size)

    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmHWM:"):
            return int(line.split()[1]) * 1024
    raise AssertionError("Linux VmHWM measurement unavailable")

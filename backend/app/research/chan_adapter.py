"""Narrow, lazy adapter for the pinned CZSC research engine.

The adapter accepts only pre-prepared causal bars. It never queries storage,
Providers, HTTP clients, or application request paths.
"""
from __future__ import annotations

import importlib
import importlib.metadata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.research.chan_contract import (
    ENGINE_VERSION,
    ChanContractError,
    PreparedResearchInput,
    ResearchObservation,
    build_observation_id,
    build_structure_evidence,
    make_observation,
)

PackageNotFoundError = importlib.metadata.PackageNotFoundError


class ChanAdapterError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class CzscBindings:
    version: str
    engine_type: type
    frequency_type: type
    raw_bar_type: type


_FREQUENCIES = {"D": "D", "W": "W", "M": "M"}


def installed_czsc_version() -> str | None:
    try:
        return importlib.metadata.version("czsc")
    except importlib.metadata.PackageNotFoundError:
        return None


def load_czsc_bindings() -> CzscBindings:
    try:
        version = importlib.metadata.version("czsc")
    except importlib.metadata.PackageNotFoundError as exc:
        raise ChanAdapterError("engine_dependency_missing", "optional CZSC dependency is not installed") from exc
    if version != ENGINE_VERSION:
        raise ChanAdapterError("unsupported_engine_version", f"expected CZSC {ENGINE_VERSION}, got {version}")
    try:
        module = importlib.import_module("czsc")
        bindings = CzscBindings(version, module.CZSC, module.Freq, module.RawBar)
    except (ImportError, AttributeError) as exc:
        raise ChanAdapterError("engine_import_failed", "pinned CZSC package could not be imported") from exc
    return bindings


def _datetime_key(value: Any) -> str:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, datetime.min.time())
    if not isinstance(value, datetime):
        raise ChanAdapterError("source_endpoint_invalid", "engine structure endpoint is not a date/time")
    return str(value.replace(tzinfo=None) if value.tzinfo else value)


def _optional_token(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


class ChanAdapter:
    def __init__(self) -> None:
        self._bindings: CzscBindings | None = None

    def observe(self, prepared: PreparedResearchInput) -> ResearchObservation:
        if not isinstance(prepared, PreparedResearchInput):
            raise ChanAdapterError("unprepared_input", "adapter requires a validated PreparedResearchInput")
        # Resolve the exact optional package once per adapter instance. Prefix
        # replay invokes observe repeatedly; package metadata lookup on every
        # prefix needlessly consumes the selected M1 resource budget.
        if self._bindings is None:
            loaded = load_czsc_bindings()
            if not isinstance(loaded, CzscBindings):
                raise ChanAdapterError("engine_binding_invalid", "CZSC loader returned an invalid binding")
            if loaded.version != ENGINE_VERSION:
                raise ChanAdapterError(
                    "unsupported_engine_version",
                    f"expected CZSC {ENGINE_VERSION}, got {loaded.version}",
                )
            self._bindings = loaded
        bindings = self._bindings
        freq_name = _FREQUENCIES.get(prepared.interval)
        if freq_name is None:
            raise ChanAdapterError("unsupported_interval", f"unsupported CZSC interval {prepared.interval}")
        try:
            freq = getattr(bindings.frequency_type, freq_name)
            raw_bars = [
                bindings.raw_bar_type(
                    prepared.instrument,
                    bar.timestamp,
                    freq,
                    bar.open,
                    bar.close,
                    bar.high,
                    bar.low,
                    bar.volume,
                    bar.amount,
                    index,
                )
                for index, bar in enumerate(prepared.bars)
            ]
            engine = bindings.engine_type(raw_bars)
            source_id_by_timestamp = {str(bar.timestamp): bar.source_bar_id for bar in prepared.bars}
            structures = []
            observation_id = build_observation_id(prepared)

            def append(kind: str, item: Any) -> None:
                if kind == "fx":
                    start_value = end_value = getattr(item, "dt", None)
                    direction = None
                    mark = _optional_token(getattr(item, "mark", None))
                    geometry = {"high": getattr(item, "high", None), "low": getattr(item, "low", None)}
                elif kind == "bi":
                    start_value = getattr(item, "sdt", None)
                    end_value = getattr(item, "edt", None)
                    direction = _optional_token(getattr(item, "direction", None))
                    mark = None
                    geometry = {"high": getattr(item, "high", None), "low": getattr(item, "low", None)}
                else:
                    start_value = getattr(item, "sdt", None)
                    end_value = getattr(item, "edt", None)
                    direction = _optional_token(getattr(item, "direction", None))
                    mark = None
                    geometry = {"zg": getattr(item, "zg", None), "zd": getattr(item, "zd", None)}

                source_start = _datetime_key(start_value)
                source_end = _datetime_key(end_value)
                start_bar_id = source_id_by_timestamp.get(source_start)
                end_bar_id = source_id_by_timestamp.get(source_end)
                if start_bar_id is None or end_bar_id is None:
                    raise ChanAdapterError("source_endpoint_missing", "structure endpoint is outside frozen input")
                structures.append(
                    build_structure_evidence(
                        prepared,
                        observation_id=observation_id,
                        kind=kind,
                        direction=direction,
                        mark=mark,
                        source_start=source_start,
                        source_end=source_end,
                        source_start_bar_id=start_bar_id,
                        source_end_bar_id=end_bar_id,
                        geometry=geometry,
                        engine_state=None,
                    )
                )

            for item in engine.fx_list:
                append("fx", item)
            for item in engine.bi_list:
                append("bi", item)
            for item in engine.zs_list:
                append("zs", item)
            structure_keys = [item.structure_key for item in structures]
            if len(structure_keys) != len(set(structure_keys)):
                raise ChanAdapterError("duplicate_structure_key", "engine returned duplicate candidate structure keys")
            return make_observation(prepared, structures)
        except ChanContractError:
            raise
        except ChanAdapterError:
            raise
        except Exception as exc:  # noqa: BLE001 - native errors are surfaced as a bounded fail-closed result
            raise ChanAdapterError("engine_compute_failed", "CZSC failed to compute this frozen input") from exc

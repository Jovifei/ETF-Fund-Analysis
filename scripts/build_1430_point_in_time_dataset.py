#!/usr/bin/env python3
"""Build a leakage-auditable 14:30 point-in-time research dataset from CSV files.

Required columns: ts_code, trade_time, open, high, low, close, volume, amount.
Features use only rows at or before the cutoff.  Historical labels and the first
tradable execution row are kept separately and never mixed into feature fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

REQUIRED = ("ts_code", "trade_time", "open", "high", "low", "close", "volume", "amount")
HORIZONS = (1, 3, 5, 10)


def _file_id(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"{path.name}:{digest[:16]}"


def load(paths: list[Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths:
        frame = pd.read_csv(path)
        missing = [name for name in REQUIRED if name not in frame.columns]
        if missing:
            raise ValueError(f"{path.name}: missing columns {missing}")
        frame = frame[list(REQUIRED)].copy()
        frame["source_file_id"] = _file_id(path)
        frames.append(frame)
    if not frames:
        raise ValueError("no input CSV files")
    data = pd.concat(frames, ignore_index=True)
    data["trade_time"] = pd.to_datetime(data["trade_time"], errors="raise")
    for column in ("open", "high", "low", "close", "volume", "amount"):
        data[column] = pd.to_numeric(data[column], errors="raise")
    invalid = (data["low"] > data[["open", "close", "high"]].min(axis=1)) | (data["high"] < data[["open", "close", "low"]].max(axis=1))
    if bool(invalid.any()):
        raise ValueError("input contains invalid OHLC relationships")
    return data.sort_values(["ts_code", "trade_time"]).drop_duplicates(["ts_code", "trade_time"], keep="last")


def build(data: pd.DataFrame, cutoff: str) -> list[dict]:
    cutoff_time = pd.Timestamp(f"2000-01-01 {cutoff}").time()
    records: list[dict] = []
    for ts_code, instrument in data.groupby("ts_code", observed=True):
        instrument = instrument.copy()
        instrument["trade_date"] = instrument["trade_time"].dt.date
        sessions = [(day, group.sort_values("trade_time")) for day, group in instrument.groupby("trade_date", observed=True)]
        base_records: list[dict] = []
        for day, session in sessions:
            feature_rows = session[session["trade_time"].dt.time <= cutoff_time]
            future_rows = session[session["trade_time"].dt.time > cutoff_time]
            if feature_rows.empty:
                continue
            last = feature_rows.iloc[-1]
            execution = future_rows.iloc[0] if not future_rows.empty else None
            base_records.append({
                "ts_code": str(ts_code),
                "trade_date": day.isoformat(),
                "decision_time": f"{day.isoformat()}T{cutoff}:00",
                "feature_cutoff_verified": bool(last["trade_time"].time() <= cutoff_time),
                "bars_available": int(len(feature_rows)),
                "open": float(feature_rows.iloc[0]["open"]),
                "high_to_cutoff": float(feature_rows["high"].max()),
                "low_to_cutoff": float(feature_rows["low"].min()),
                "close_at_cutoff": float(last["close"]),
                "volume_to_cutoff": float(feature_rows["volume"].sum()),
                "amount_to_cutoff": float(feature_rows["amount"].sum()),
                "vwap_to_cutoff": float(feature_rows["amount"].sum() / feature_rows["volume"].sum()) if float(feature_rows["volume"].sum()) > 0 else None,
                "execution_time": execution["trade_time"].isoformat() if execution is not None else None,
                "execution_price": float(execution["open"]) if execution is not None else None,
                "session_close": float(session.iloc[-1]["close"]),
                "session_high": float(session["high"].max()),
                "session_low": float(session["low"].min()),
                "source_file_ids": sorted(set(str(value) for value in session["source_file_id"])),
                "labels": {},
            })
        for index, record in enumerate(base_records):
            current = float(record["close_at_cutoff"])
            for horizon in HORIZONS:
                end = index + horizon
                if end >= len(base_records):
                    continue
                future = base_records[index + 1 : end + 1]
                terminal = float(base_records[end]["session_close"])
                record["labels"][str(horizon)] = {
                    "terminal_return": terminal / current - 1.0,
                    "path_low_return": min(float(item["session_low"]) for item in future) / current - 1.0,
                    "path_high_return": max(float(item["session_high"]) for item in future) / current - 1.0,
                    "label_end_date": base_records[end]["trade_date"],
                }
            records.append(record)
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--interval-minutes", type=int, choices=(5, 15), required=True)
    parser.add_argument("--cutoff", default="14:30")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = load(args.inputs)
    records = build(data, args.cutoff)
    payload = {
        "schema_version": "etf-1430-point-in-time-v0.1.0",
        "interval_minutes": args.interval_minutes,
        "feature_cutoff": args.cutoff,
        "execution_rule": "first_tradable_bar_after_cutoff",
        "record_count": len(records),
        "records": records,
        "governance": {
            "features_use_rows_at_or_before_cutoff": True,
            "labels_are_future_only": True,
            "random_time_series_shuffle_forbidden": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "record_count": len(records), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

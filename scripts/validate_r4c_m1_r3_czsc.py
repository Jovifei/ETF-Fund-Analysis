from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from czsc import CZSC, Freq, RawBar


def make_bars(count: int, volume: float = 100.0) -> list[RawBar]:
    rows = []
    start = datetime(2026, 1, 1)
    for index in range(count):
        phase = (index // 5) % 2
        close = 100.0 + (3.0 if phase == 0 else -3.0) + (index // 50) * 0.2
        open_price = close - 1.0 if phase == 0 else close + 1.0
        rows.append(RawBar("M1", start + timedelta(days=index), Freq.D,
                           open_price, close, max(open_price, close) + 1.0,
                           min(open_price, close) - 1.0, volume, volume * close, index))
    return rows


def normalized(count: int, volume: float = 100.0) -> dict[str, object]:
    engine = CZSC(make_bars(count, volume))
    fxs = [{"dt": str(getattr(item, "dt", None)), "mark": str(getattr(item, "mark", None)),
            "high": getattr(item, "high", None), "low": getattr(item, "low", None)}
           for item in engine.fx_list]
    bis = [{"sdt": str(getattr(item, "sdt", None)), "edt": str(getattr(item, "edt", None)),
            "direction": str(getattr(item, "direction", None)), "high": getattr(item, "high", None),
            "low": getattr(item, "low", None)} for item in engine.bi_list]
    zss = [{"sdt": str(getattr(item, "sdt", None)), "edt": str(getattr(item, "edt", None)),
            "zg": getattr(item, "zg", None), "zd": getattr(item, "zd", None)}
           for item in engine.zs_list]
    value = {"raw_bars": len(engine.bars_raw), "fx": fxs, "bi": bis, "zs": zss,
             "fx_count": len(fxs), "bi_count": len(bis), "zs_count": len(zss)}
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    return {"value": value, "digest": hashlib.sha256(encoded).hexdigest()}


def main() -> None:
    runs = [normalized(300), normalized(300)]
    prefixes = {str(n): normalized(n) for n in (80, 160, 240, 300)}
    volume_zero = normalized(300, 0.0)
    print(json.dumps({
        "engine": "czsc",
        "version": "1.0.1",
        "platform": "windows-cpython-3.12-cp310-abi3",
        "full_runs_equal": runs[0] == runs[1],
        "full": runs[0],
        "prefix_digests": {key: value["digest"] for key, value in prefixes.items()},
        "prefix_counts": {key: value["value"]["fx_count"] for key, value in prefixes.items()},
        "zero_volume_digest": volume_zero["digest"],
        "zero_volume_counts": volume_zero["value"]["fx_count"],
        "geometry_fields": "fx(dt,mark,high,low); bi(sdt,edt,direction,high,low); zs(sdt,edt,zg,zd)",
        "causal_observation": "probe records prefix and future comparisons; no confirmation timestamp is inferred",
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

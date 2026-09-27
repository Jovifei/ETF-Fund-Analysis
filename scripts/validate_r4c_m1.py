from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import chanlun


def bars(count: int) -> list[tuple[int, float, float, float, float]]:
    out = []
    for index in range(count):
        phase = (index // 5) % 2
        close = 100.0 + (3.0 if phase == 0 else -3.0) + (index // 50) * 0.2
        open_price = close - 1.0 if phase == 0 else close + 1.0
        out.append((index, open_price, max(open_price, close) + 1.0, min(open_price, close) - 1.0, close))
    return out


def observe(count: int) -> dict[str, object]:
    config = chanlun.缠论配置()
    observer = chanlun.观察者("M1", 86400, config)
    for index, open_price, high, low, close in bars(count):
        kline = chanlun.K线.创建普K(
            "M1",
            1_700_000_000 + index * 86400,
            open_price,
            high,
            low,
            close,
            100.0,
            index,
            86400,
        )
        observer.增加原始K线(kline)
    counts = {
        "raw_k": len(getattr(observer, "普通K线序列", []) or []),
        "fenxing": len(getattr(observer, "分型序列", []) or []),
        "bi": len(getattr(observer, "笔序列", []) or []),
        "segments": len(getattr(observer, "线段序列", []) or []),
        "zs": len(getattr(observer, "中枢序列", []) or []),
    }
    normalized = json.dumps(counts, ensure_ascii=False, sort_keys=True)
    return {"counts": counts, "digest": hashlib.sha256(normalized.encode()).hexdigest()}


def main() -> None:
    capability = {
        "raw_k": hasattr(chanlun.观察者, "增加原始K线"),
        "fenxing": hasattr(chanlun.观察者, "分型序列"),
        "bi": hasattr(chanlun.观察者, "笔序列"),
        "segments": hasattr(chanlun.观察者, "线段序列"),
        "zs": hasattr(chanlun.观察者, "中枢序列"),
        "backtest_or_signal_semantics": "not_qualified_by_this_probe",
    }
    runs = [observe(300), observe(300)]
    prefixes = {str(count): observe(count) for count in (80, 160, 240, 300)}
    result = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "package": "chanlun",
        "version": "2606.73",
        "source_mapping": "BLOCKED_UNRECONCILED_WHEEL_TO_UPSTREAM_COMMIT",
        "platform": "windows-cpython-3.13-win_amd64",
        "capability_surface": capability,
        "identical_fixture_runs_equal": runs[0] == runs[1],
        "runs": runs,
        "prefix_runs": prefixes,
        "geometry_evidence": "COUNTS_ONLY_NO_GEOMETRY_SERIALIZATION",
        "causal_confirmation_evidence": "NOT_ESTABLISHED",
        "linux_probe": "NOT_RUN_ENV",
        "czsc_probe": "NOT_INSTALLED",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

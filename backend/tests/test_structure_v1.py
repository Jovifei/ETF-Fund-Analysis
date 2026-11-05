"""structure_v1 research proxies + board soft-fill (Phase A; no assign_grade)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PKG_PARENT = REPO_ROOT / "research" / "etf_structure_features"
if str(PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(PKG_PARENT))

from etf_structure_features import RISK_BUCKET_RULE_VERSION, build_structure_row  # noqa: E402
from etf_structure_features.atr_risk import (  # noqa: E402
    BANDS,
    bucket_from_pct,
    wilder_atr14,
)
from etf_structure_features.dow_proxy import confirmed_pivots, dow_phase_from_pivots  # noqa: E402
from etf_structure_features.wyckoff_proxy import wyckoff_from_ohlcv  # noqa: E402

from app.research.structure_v1 import resolve_structure_v1, structure_v1_from_history  # noqa: E402
from app.services.decision_board_service import _resolve_structure_v1_for_row  # noqa: E402


def _zigzag(n: int, start: float, *, up: bool) -> dict[str, list[float]]:
    """Build HH/HL (up) or LH/LL (down) swings so swing_k=2 pivots confirm."""
    opens, highs, lows, closes, volumes = [], [], [], [], []
    # Anchor levels that rise (or fall) each full swing cycle of 6 bars.
    level = start
    i = 0
    cycle = 0
    while i < n:
        # amplitude grows slowly so successive swing highs/lows compare correctly
        amp = 3.0 + cycle * 0.8
        # 3 bars up to swing high, 3 bars down to swing low (or mirrored for downtrend)
        pattern = [0.2, 0.55, 1.0, 0.7, 0.35, 0.05]  # relative inside cycle
        for rel in pattern:
            if i >= n:
                break
            if up:
                center = level + amp * rel
            else:
                center = level - amp * rel
            o = center - 0.05
            c = center + 0.05
            h = max(o, c, center) + 0.15
            l = min(o, c, center) - 0.15
            opens.append(o)
            highs.append(h)
            lows.append(l)
            closes.append(c)
            volumes.append(1_000_000.0 + (i % 7) * 10_000)
            i += 1
        # next cycle base higher (up) / lower (down)
        level = level + (1.2 if up else -1.2)
        cycle += 1
    return {"opens": opens, "highs": highs, "lows": lows, "closes": closes, "volumes": volumes}


def _series_uptrend(n: int = 60, start: float = 100.0) -> dict[str, list[float]]:
    return _zigzag(n, start, up=True)


def _series_downtrend(n: int = 60, start: float = 100.0) -> dict[str, list[float]]:
    return _zigzag(n, start, up=False)


def _series_quiet_range(n: int = 40, mid: float = 10.0) -> dict[str, list[float]]:
    """Low ATR% range near mid — should bucket low when pct < 1%."""
    opens, highs, lows, closes, volumes = [], [], [], [], []
    for i in range(n):
        o = mid + (0.01 if i % 2 == 0 else -0.01)
        c = mid + (-0.01 if i % 2 == 0 else 0.01)
        opens.append(o)
        highs.append(mid + 0.02)
        lows.append(mid - 0.02)
        closes.append(c)
        volumes.append(500_000.0)
    return {"opens": opens, "highs": highs, "lows": lows, "closes": closes, "volumes": volumes}


def _history_from_series(series: dict[str, list[float]], start_date: str = "2026-01-02") -> list[dict]:
    from datetime import date, timedelta

    d0 = date.fromisoformat(start_date)
    out = []
    for i in range(len(series["closes"])):
        d = d0 + timedelta(days=i)
        # skip weekends lightly
        while d.weekday() >= 5:
            d += timedelta(days=1)
            d0 = d - timedelta(days=i)  # keep advancing uniquely via i offset below
        out.append(
            {
                "date": (date.fromisoformat(start_date) + timedelta(days=i)).isoformat(),
                "open": series["opens"][i],
                "high": series["highs"][i],
                "low": series["lows"][i],
                "close": series["closes"][i],
                "volume": series["volumes"][i],
            }
        )
    return out


def test_atr_pct_fixed_v1_bands_and_rule_version():
    assert RISK_BUCKET_RULE_VERSION == "atr_pct_fixed_v1"
    assert [b[0] for b in BANDS] == ["low", "mid", "high", "extreme"]
    assert bucket_from_pct(None) == "unknown"
    assert bucket_from_pct(0.0) == "low"
    assert bucket_from_pct(0.009999) == "low"
    assert bucket_from_pct(0.01) == "mid"
    assert bucket_from_pct(0.019999) == "mid"
    assert bucket_from_pct(0.02) == "high"
    assert bucket_from_pct(0.034999) == "high"
    assert bucket_from_pct(0.035) == "extreme"
    assert bucket_from_pct(0.10) == "extreme"


def test_wilder_atr14_needs_history_and_is_positive():
    s = _series_uptrend(30)
    assert wilder_atr14(s["highs"][:10], s["lows"][:10], s["closes"][:10]) is None
    atr = wilder_atr14(s["highs"], s["lows"], s["closes"])
    assert atr is not None and atr > 0


def test_confirmed_pivots_not_stub_empty_on_trend():
    s = _series_uptrend(80)
    pivots = confirmed_pivots(s["highs"], s["lows"], as_of_index=len(s["closes"]) - 1, lag_n=2)
    assert isinstance(pivots, list)
    assert len(pivots) >= 2  # stubs returned []
    phase, score, conf, ev = dow_phase_from_pivots(pivots)
    assert phase in {
        "uptrend",
        "downtrend",
        "sideways",
        "correction_in_uptrend",
        "rally_in_downtrend",
        "unknown",
    }
    assert conf >= 0
    assert isinstance(ev, list)


def test_dow_uptrend_and_downtrend_labels():
    up = _series_uptrend(80)
    piv_up = confirmed_pivots(up["highs"], up["lows"], as_of_index=len(up["closes"]) - 1)
    phase_up, score_up, _, _ = dow_phase_from_pivots(piv_up)
    assert phase_up == "uptrend"
    assert score_up > 0

    dn = _series_downtrend(80)
    piv_dn = confirmed_pivots(dn["highs"], dn["lows"], as_of_index=len(dn["closes"]) - 1)
    phase_dn, score_dn, _, _ = dow_phase_from_pivots(piv_dn)
    assert phase_dn == "downtrend"
    assert score_dn < 0


def test_wyckoff_proxy_not_always_unknown():
    s = _series_uptrend(40)
    # Boost last vols + push price to top of range → markup-ish
    s["volumes"][-1] = max(s["volumes"]) * 2.5
    phase, score, conf, ev = wyckoff_from_ohlcv(
        s["opens"], s["highs"], s["lows"], s["closes"], s["volumes"], as_of_index=len(s["closes"]) - 1
    )
    assert phase != "unknown"
    assert phase in {"accumulation", "distribution", "markup", "markdown", "range"}
    assert isinstance(ev, list) and ev


def test_build_structure_row_emits_real_fields():
    s = _series_quiet_range(40)
    row = build_structure_row(
        ts_code="510300.SH",
        as_of="2026-11-05",
        name="沪深300ETF",
        **s,
    )
    assert row["schema_version"] == "structure_v1"
    assert row["research_only"] is True
    assert row["atr14"] is not None and row["atr14"] > 0
    assert row["atr_pct"] is not None
    assert row["atr_risk_bucket"] in {"low", "mid", "high", "extreme", "unknown"}
    # quiet ~0.4% range vs price 10 → atr_pct well under 1% → low
    assert row["atr_risk_bucket"] == "low"
    assert row["wyckoff_phase"] != "unknown" or row["dow_phase"] != "unknown" or row["atr14"]
    assert row["dow_phase"] in {
        "uptrend",
        "downtrend",
        "sideways",
        "correction_in_uptrend",
        "rally_in_downtrend",
        "unknown",
    }


def test_structure_v1_from_history_soft_fail_and_fill():
    assert structure_v1_from_history(ts_code="X", history=None) is None
    assert structure_v1_from_history(ts_code="X", history=[]) is None
    assert structure_v1_from_history(ts_code="X", history=[{"date": "2026-01-01", "close": 1}]) is None

    s = _series_uptrend(40)
    hist = _history_from_series(s)
    row = structure_v1_from_history(ts_code="510300.SH", history=hist, name="demo")
    assert isinstance(row, dict)
    assert row["schema_version"] == "structure_v1"
    assert row["ts_code"] == "510300.SH"
    assert row["atr_risk_bucket"] in {"low", "mid", "high", "extreme"}


def test_resolve_prefers_existing_block():
    existing = {"schema_version": "structure_v1", "wyckoff_phase": "range", "atr_risk_bucket": "mid"}
    out = resolve_structure_v1(existing=existing, ts_code="X", history=None)
    assert out is existing


def test_board_helper_fills_when_missing():
    s = _series_uptrend(40)
    hist = _history_from_series(s)
    filled = _resolve_structure_v1_for_row(
        grade_row={},
        values={},
        ts_code="510300.SH",
        name="demo",
        history=hist,
    )
    assert isinstance(filled, dict)
    assert filled.get("schema_version") == "structure_v1"
    assert filled.get("atr14") is not None

    # soft-fail path
    assert (
        _resolve_structure_v1_for_row(
            grade_row={}, values={}, ts_code="X", name=None, history=None
        )
        is None
    )

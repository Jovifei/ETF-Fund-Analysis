"""Pure helpers for the research-only HS300 passive-holdings ratio.

    ratio = Σ(HS300-tracking ETF value) / Σ(HS300 constituent 流通市值)

Both sides must share one trade date and one denominator convention. Nothing
here reads a database or a network: callers pass already-validated records.

The ratio is a *level*, not a signal. A high level does not mean "sell", a low
level does not mean "buy", and neither is a fund-flow observation.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.utils.hashing import stable_hash

FLOAT_MARKET_CAP = "float_market_cap"
MARKET_VALUE_AT_CLOSE = "market_value_at_close"
AUM_AT_NAV = "aum_at_nav"

# The sum of every HS300-tracking ETF cannot plausibly exceed half of the
# index's floating market value. Beyond this the inputs are wrong (wrong unit,
# wrong index list, unadjusted shares) and a number must not be published.
MAX_PLAUSIBLE_RATIO = 0.5

UNIVERSE_PROVISIONAL = "provisional"
UNIVERSE_CONFIRMED = "confirmed"


def universe_hash(index_code: str, funds: list[str]) -> str:
    """Stable identity of the frozen fund list, independent of file order."""
    return stable_hash(
        {
            "index_code": str(index_code or "").strip().upper(),
            "funds": sorted({str(item or "").strip().upper() for item in funds}),
        }
    )


def load_universe(path: Path) -> dict[str, Any]:
    """Read the frozen list. An unreadable or malformed file refuses, never guesses."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": UNIVERSE_PROVISIONAL, "reason": "universe_unreadable", "funds": []}
    if not isinstance(payload, dict):
        return {"status": UNIVERSE_PROVISIONAL, "reason": "universe_invalid", "funds": []}
    return payload


def normalize_funds(raw: Any) -> tuple[list[str], list[str]]:
    """Return ``(valid ts_codes, rejected entries)`` in deterministic order.

    Only exchange-listed 6-digit ETF/LOF codes are accepted. Anything else
    (blank, wrong suffix, 联接 fund codes) is reported instead of silently
    dropped, so a typo in the frozen list cannot shrink the numerator.
    """
    if not isinstance(raw, (list, tuple)):
        return [], []
    valid: set[str] = set()
    rejected: set[str] = set()
    for item in raw:
        code = str(item or "").strip().upper()
        if not code:
            continue
        symbol, _, exchange = code.partition(".")
        if len(symbol) == 6 and symbol.isdigit() and exchange in {"SH", "SZ"}:
            valid.add(code)
        else:
            rejected.add(code)
    return sorted(valid), sorted(rejected)


def compute_ratio(numerator: float | None, denominator: float | None) -> float | None:
    """Return the ratio only when both sides are finite, positive and plausible."""
    if numerator is None or denominator is None:
        return None
    if not (math.isfinite(numerator) and math.isfinite(denominator)):
        return None
    if numerator <= 0 or denominator <= 0:
        return None
    ratio = numerator / denominator
    if ratio <= 0 or ratio > MAX_PLAUSIBLE_RATIO:
        return None
    return ratio

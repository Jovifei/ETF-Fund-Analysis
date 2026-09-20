"""Independent absolute 量/额 certification. Ratio is a sanity check, never proof.

Documented multipliers below are the conversions already implemented in the
provider adapters (Tushare fund_daily vol×100 / amount×1000, East Money
成交量×100 / 成交额 CNY). This module does not invent new factors, rescale
stored bars, or treat a matching VWAP as qualification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.providers.data_contract import UNVERIFIED_UNIT_SOURCES, finite

# Endpoint field contracts copied from the adapters that already apply them.
# A new provider must add a row here and an independent same-day fixture.
DOCUMENTED_ENDPOINT_FIELDS = {
    "tushare:fund_daily:v101": {
        "volume_raw_field": "vol",
        "volume_raw_unit": "hand_100_shares",
        "volume_to_shares": 100,
        "amount_raw_field": "amount",
        "amount_raw_unit": "thousand_cny",
        "amount_to_cny": 1000,
        "evidence": "adapter_contract_tushare_fund_daily_v101",
    },
    "akshare:em:v101": {
        "volume_raw_field": "成交量",
        "volume_raw_unit": "hand_100_shares",
        "volume_to_shares": 100,
        "amount_raw_field": "成交额",
        "amount_raw_unit": "cny",
        "amount_to_cny": 1,
        "evidence": "adapter_contract_akshare_em_v101",
    },
    "akshare:sina:v101": {
        "volume_raw_field": "volume",
        "volume_raw_unit": "hand_100_shares",
        "volume_to_shares": 100,
        "amount_raw_field": "amount",
        "amount_raw_unit": "cny",
        "amount_to_cny": 1,
        "evidence": "akshare_sina_volume_docs_and_tencent_same_day_cross_check_20260921",
    },
    "tencent:stock_zh_a_hist_tx:v101": {
        "volume_raw_field": "volume",
        "volume_raw_unit": "shares",
        "volume_to_shares": 1,
        "amount_raw_field": "amount",
        "amount_raw_unit": "cny",
        "amount_to_cny": 1,
        "evidence": "akshare_stock_zh_a_hist_tx_adapter_contract_v101",
    },
    "ftshare:fetch_daily_bars": {
        "volume_raw_field": "volume",
        "volume_raw_unit": "shares",
        "volume_to_shares": 1,
        "amount_raw_field": "amount",
        "amount_raw_unit": "cny",
        "amount_to_cny": 1,
        "evidence": "adapter_contract_ftshare_fetch_daily_bars",
    },
}

VWAP_SANITY_TOLERANCE = 0.10
VOLUME_ABS_TOLERANCE_SHARES = 0.5
AMOUNT_ABS_TOLERANCE_CNY = 0.5


@dataclass(frozen=True, slots=True)
class UnitObservation:
    ts_code: str
    trade_date: date
    close: float
    source: str
    raw_volume: float | None
    raw_amount: float | None
    converted_volume: float | None = None
    converted_amount: float | None = None


@dataclass(frozen=True, slots=True)
class UnitCertification:
    certified: bool
    volume: float | None
    amount: float | None
    ratio_sanity_passed: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def get(self, key, default=None):
        return getattr(self, key, default)


def _source_family(source: str) -> str:
    return str(source or "").split(":", 1)[0]


def _apply_documented(source: str, raw_volume, raw_amount):
    spec = DOCUMENTED_ENDPOINT_FIELDS.get(source)
    if spec is None:
        return None, None, ["unknown_endpoint_units_unverified"]
    volume = float(raw_volume) * spec["volume_to_shares"] if finite(raw_volume) else None
    amount = float(raw_amount) * spec["amount_to_cny"] if finite(raw_amount) else None
    return volume, amount, []


def _claimed_matches(applied, claimed) -> bool:
    if applied is None or claimed is None:
        return applied is None and claimed is None
    return abs(float(applied) - float(claimed)) <= VOLUME_ABS_TOLERANCE_SHARES


def _amount_matches(applied, claimed) -> bool:
    if applied is None or claimed is None:
        return applied is None and claimed is None
    return abs(float(applied) - float(claimed)) <= AMOUNT_ABS_TOLERANCE_CNY


def _vwap_sane(volume, amount, close) -> bool:
    if not (finite(volume) and finite(amount) and finite(close)):
        return False
    if float(volume) <= 0 or float(close) <= 0:
        return False
    return abs(float(amount) / float(volume) / float(close) - 1.0) <= VWAP_SANITY_TOLERANCE


def _canonical(observation: UnitObservation) -> tuple[float | None, float | None, list[str]]:
    reasons: list[str] = []
    if observation.source in UNVERIFIED_UNIT_SOURCES and (
        not finite(observation.raw_volume) or not finite(observation.raw_amount)
    ):
        reasons.append("sina_absolute_units_unverified")
    volume, amount, extra = _apply_documented(observation.source, observation.raw_volume, observation.raw_amount)
    reasons.extend(extra)
    if observation.converted_volume is not None and volume is not None:
        if not _claimed_matches(volume, observation.converted_volume):
            reasons.append("converted_volume_does_not_match_documented_field_def")
    elif observation.converted_volume is not None and volume is None:
        reasons.append("converted_volume_does_not_match_documented_field_def")
    if observation.converted_amount is not None and amount is not None:
        if not _amount_matches(amount, observation.converted_amount):
            reasons.append("converted_amount_does_not_match_documented_field_def")
    elif observation.converted_amount is not None and amount is None:
        reasons.append("converted_amount_does_not_match_documented_field_def")
    if volume is None or amount is None:
        reasons.append("volume_or_amount_missing")
    return volume, amount, reasons


def certify_absolute_units(primary: UnitObservation, independent: UnitObservation | None = None) -> UnitCertification:
    """Qualify canonical shares/CNY only with a documented field def AND a second source.

    A matching VWAP may fail the pair; it can never pass it.
    """

    reasons: list[str] = []
    primary_volume, primary_amount, primary_reasons = _canonical(primary)
    reasons.extend(primary_reasons)

    if independent is None:
        reasons.append("independent_same_day_observation_missing")
        ratio_ok = _vwap_sane(primary_volume, primary_amount, primary.close)
        if ratio_ok:
            reasons.append("ratio_only_is_not_qualification")
        return UnitCertification(False, primary_volume, primary_amount, ratio_ok, tuple(dict.fromkeys(reasons)))

    if (primary.ts_code, primary.trade_date) != (independent.ts_code, independent.trade_date):
        reasons.append("independent_observation_not_same_day")
    if _source_family(primary.source) == _source_family(independent.source):
        reasons.append("independent_observation_not_second_source")

    other_volume, other_amount, other_reasons = _canonical(independent)
    reasons.extend(other_reasons)

    primary_ratio = _vwap_sane(primary_volume, primary_amount, primary.close)
    other_ratio = _vwap_sane(other_volume, other_amount, independent.close)
    ratio_ok = primary_ratio and other_ratio
    if not ratio_ok:
        reasons.append("ratio_sanity_failed")

    volumes_match = (
        finite(primary_volume)
        and finite(other_volume)
        and _claimed_matches(primary_volume, other_volume)
    )
    amounts_match = (
        finite(primary_amount)
        and finite(other_amount)
        and _amount_matches(primary_amount, other_amount)
    )
    if finite(primary_volume) and finite(other_volume) and not volumes_match:
        reasons.append("absolute_volume_mismatch")
    if finite(primary_amount) and finite(other_amount) and not amounts_match:
        reasons.append("absolute_amount_mismatch")
    if ratio_ok and not (volumes_match and amounts_match):
        reasons.append("ratio_only_is_not_qualification")

    certified = not reasons and volumes_match and amounts_match and ratio_ok
    return UnitCertification(
        certified=certified,
        volume=primary_volume,
        amount=primary_amount,
        ratio_sanity_passed=ratio_ok,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def history_units_independently_certified(rows) -> UnitCertification:
    """Database bars have no second-source raw fields; source membership is not proof."""

    if not rows:
        return UnitCertification(False, None, None, False, ("independent_same_day_observation_missing",))
    reasons = ["independent_same_day_observation_missing"]
    if any(getattr(row, "source", None) in UNVERIFIED_UNIT_SOURCES for row in rows):
        reasons.append("sina_absolute_units_unverified")
    missing = any(not finite(getattr(row, "volume", None)) or not finite(getattr(row, "amount", None)) for row in rows)
    if missing:
        reasons.append("volume_or_amount_missing")
        volume = None
        amount = None
    else:
        last = rows[-1]
        volume = float(last.volume)
        amount = float(last.amount)
        if _vwap_sane(volume, amount, last.close):
            reasons.append("ratio_only_is_not_qualification")
    return UnitCertification(False, volume if not missing else None, amount if not missing else None, False, tuple(dict.fromkeys(reasons)))

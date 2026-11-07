"""Phase A structure proxies — flat structure_v1 only."""

from .atr_risk import RISK_BUCKET_RULE_VERSION
from .pipeline import build_structure_row

__all__ = ["build_structure_row", "RISK_BUCKET_RULE_VERSION"]

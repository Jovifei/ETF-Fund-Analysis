"""Read-time version/date contract. Does not relabel, repair, or promote snapshots."""
from __future__ import annotations

from app.utils.hashing import stable_hash


def snapshot_issues(row, settings, expected_date, *, kind='indicator') -> list[str]:
    if row is None:
        return [f'{kind}_missing']
    cfg = settings.load_strategy()
    version = getattr(row, 'version' if kind == 'indicator' else 'model_version', None)
    reasons = []
    if version != cfg['indicator_version' if kind == 'indicator' else 'forecast_version']:
        reasons.append(f'{kind}_version_mismatch')
    if getattr(row, 'feature_schema_version', None) != cfg['feature_schema_version']:
        reasons.append(f'{kind}_schema_mismatch')
    if getattr(row, 'config_hash', None) != stable_hash(cfg):
        reasons.append(f'{kind}_config_mismatch')
    if expected_date is not None and getattr(row, 'as_of_date', None) != expected_date:
        reasons.append(f'{kind}_date_mismatch')
    return reasons

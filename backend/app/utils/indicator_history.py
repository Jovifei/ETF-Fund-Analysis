"""Comparison requires the immediately prior dated snapshot with the same semantics."""
from sqlalchemy import select
from app.models import IndicatorSnapshot

IDENTITY_FIELDS = ("version", "config_hash", "feature_schema_version")

def previous_values(db, current):
    if not all(getattr(current, field, None) for field in IDENTITY_FIELDS):
        return None
    row = db.scalar(select(IndicatorSnapshot).where(
        IndicatorSnapshot.instrument_id == current.instrument_id,
        IndicatorSnapshot.as_of_date < current.as_of_date,
    ).order_by(IndicatorSnapshot.as_of_date.desc(), IndicatorSnapshot.generated_at.desc(),
               IndicatorSnapshot.id.desc()).limit(1))
    if row is None or not row.values_json or any(
        getattr(row, field, None) != getattr(current, field, None) for field in IDENTITY_FIELDS
    ):
        return None
    return {**dict(row.values_json), "_as_of_date": row.as_of_date.isoformat(),
            "_comparison_basis": "previous_same_formula_snapshot"}

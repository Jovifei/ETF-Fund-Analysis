"""US markets research block (CPO/optical, memory/storage baskets, US indices).

Research-only display data. It never feeds the grading code, signals, the five
grades, positions or strategy e-mails.
"""

from app.us_markets_research.contracts import (
    PART_NAME,
    SCHEMA_VERSION,
    validate_part,
)

__all__ = ["PART_NAME", "SCHEMA_VERSION", "validate_part"]

"""Hash actual calculation inputs, not a trusted cache hash or a tail sample."""
from app.utils.hashing import stable_hash

BAR_FIELDS = ("trade_date", "open", "high", "low", "close", "pre_close", "volume", "amount", "pct_change", "adjust", "source")

def history_digest(rows):
    return stable_hash([{key: getattr(row, key, None) for key in BAR_FIELDS} for row in rows])

def calculation_digest(histories, strategy, component, **kwargs):
    # Include the entire panel: RPS/cross-sectional features depend on peers too.
    return stable_hash({"histories": {str(k): v for k, v in sorted(histories.items())},
                        "strategy": strategy, "component": component, **kwargs})

"""Hash actual calculation inputs, not a trusted cache hash or a tail sample."""
import hashlib
import json

from app.utils.hashing import stable_hash

BAR_FIELDS = ("trade_date", "open", "high", "low", "close", "pre_close", "volume", "amount", "pct_change", "adjust", "source")

def history_digest(rows):
    # Byte-for-byte compatible with stable_hash(list_of_records), without a
    # second full-history list or a full serialized JSON allocation.
    digest = hashlib.sha256(b"[")
    separator = b""
    for row in rows:
        digest.update(separator)
        record = {key: getattr(row, key, None) for key in BAR_FIELDS}
        digest.update(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                 default=str, separators=(",", ":")).encode("utf-8"))
        separator = b","
    digest.update(b"]")
    return digest.hexdigest()

def calculation_digest(histories, strategy, component, **kwargs):
    # Include the entire panel: RPS/cross-sectional features depend on peers too.
    return stable_hash({"histories": {str(k): v for k, v in sorted(histories.items())},
                        "strategy": strategy, "component": component, **kwargs})

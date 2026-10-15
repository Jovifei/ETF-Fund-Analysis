"""Explicit target writes with an unchanged all-enabled research background."""
from app.utils.hashing import stable_hash

EXECUTION_SCOPE_VERSION = "execution-scope-v1"


def target_instruments(instruments, codes=None):
    if codes is None:
        return list(instruments)
    if (not isinstance(codes, (list, tuple)) or not codes
            or any(not isinstance(code, str) or not code or code != code.strip() for code in codes)
            or len(set(codes)) != len(codes)):
        raise ValueError("execution_scope_invalid_codes")
    targets = [item for item in instruments if item.ts_code in set(codes)]
    if {item.ts_code for item in targets} != set(codes):
        raise ValueError("execution_scope_unknown_or_disabled_code")
    return targets


def execution_scope(instruments, codes):
    targets = target_instruments(instruments, codes)
    return {"version": EXECUTION_SCOPE_VERSION, "target_codes": sorted(item.ts_code for item in targets),
            "target_count": len(targets), "background_count": len(instruments),
            "background_scope_hash": stable_hash(sorted(item.ts_code for item in instruments))}


def scope_metadata(instruments, codes):
    return {} if codes is None else {"execution_scope": execution_scope(instruments, codes)}


def validate_execution_scope(value, instruments, codes):
    if (codes is None or not isinstance(value, dict)
            or any(type(value.get(key)) is not int for key in ("target_count", "background_count"))
            or value != execution_scope(instruments, codes)):
        raise ValueError("execution_scope_completion_mismatch")

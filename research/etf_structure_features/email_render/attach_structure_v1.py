# -*- coding: utf-8 -*-
"""Attach optional structure_v1 blocks onto an existing slim JSON from a shadow/sidecar file.
Does not invent grades. slim_version bumped to etf-email-slim-v1.1.
Usage: python attach_structure_v1.py <slim.json> <shadow.json> [out.json]
"""
import json, sys
from pathlib import Path
from extract_slim import _load_structure_sidecar, _structure_v1

def main():
    slim_path, shadow_path = sys.argv[1], sys.argv[2]
    out_path = sys.argv[3] if len(sys.argv) > 3 else None
    slim = json.loads(Path(slim_path).read_text(encoding="utf-8"))
    idx = _load_structure_sidecar(shadow_path)
    for r in slim.get("rows") or []:
        # Prefer matching as_of from row if present; helper falls back to (ts_code, "")
        fake = {"ts_code": r.get("ts_code"), "as_of": r.get("returns_as_of") or r.get("sr_as_of"), "name": r.get("name"), "support_resistance": {}}
        sv = _structure_v1(fake, None, idx)
        if isinstance(sv, dict):
            if r.get("atr14") is not None and sv.get("atr14") is None:
                sv["atr14"] = r.get("atr14")
            elif r.get("atr14") is not None:
                sv["atr14"] = r.get("atr14")  # prefer slim top-level
            r["structure_v1"] = sv
        else:
            r.pop("structure_v1", None)
    slim["slim_version"] = "etf-email-slim-v1.1"
    txt = json.dumps(slim, ensure_ascii=False, separators=(",", ":"))
    if out_path:
        Path(out_path).write_text(txt, encoding="utf-8")
    else:
        sys.stdout.write(txt)

if __name__ == "__main__":
    main()

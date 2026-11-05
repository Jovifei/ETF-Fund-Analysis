# -*- coding: utf-8 -*-
"""从本机 live compute 的 bundle_*.json 中抽取邮件所需的精简字段（仅标准库，只读）。

用法：
  python extract_slim.py <bundle.json>            # 输出到 stdout
  python extract_slim.py <bundle.json> <out.json>  # 写入文件（不要在 Jovi 上使用此形式）
字段原样抽取，不做任何推算；缺失字段保留为 null。
"""
import json
import sys


def _g(d, *path):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def _level(lv):
    if not isinstance(lv, dict):
        return None
    return {k: lv.get(k) for k in ("price", "zone_low", "zone_high", "distance_pct", "strength", "methods")}


def _fc(fc, h):
    x = fc.get(h) if isinstance(fc, dict) else None
    if not isinstance(x, dict):
        return None
    return {k: x.get(k) for k in ("expected_return", "p_up", "q10", "q50", "q90", "as_of_date", "calibration_status")}



def _structure_v1(row, det=None, sidecar_index=None):
    """Optional Phase A research block; never invent grades. Prefer row, then details, then sidecar by ts_code+as_of."""
    block = None
    if isinstance(row, dict) and isinstance(row.get("structure_v1"), dict):
        block = row.get("structure_v1")
    elif isinstance(det, dict) and isinstance(det.get("structure_v1"), dict):
        block = det.get("structure_v1")
    elif isinstance(sidecar_index, dict):
        key = (str(row.get("ts_code") or ""), str(
            (row.get("support_resistance") or {}).get("snapshot_as_of_date")
            or (row.get("support_resistance") or {}).get("source_as_of_date")
            or row.get("as_of")
            or ""
        ))
        hit = sidecar_index.get(key) or sidecar_index.get((key[0], ""))
        if isinstance(hit, dict):
            block = hit
    if not isinstance(block, dict):
        return None
    if block.get("schema_version") not in (None, "structure_v1"):
        return None
    out = {
        "schema_version": "structure_v1",
        "ts_code": block.get("ts_code") or row.get("ts_code"),
        "name": block.get("name") if block.get("name") is not None else row.get("name"),
        "as_of": block.get("as_of"),
        "lag_n": block.get("lag_n", 2),
        "wyckoff_phase": block.get("wyckoff_phase"),
        "wyckoff_score": block.get("wyckoff_score"),
        "wyckoff_confidence": block.get("wyckoff_confidence"),
        "dow_phase": block.get("dow_phase"),
        "dow_score": block.get("dow_score"),
        "dow_confidence": block.get("dow_confidence"),
        "atr14": block.get("atr14"),
        "atr_pct": block.get("atr_pct"),
        "atr_risk_bucket": block.get("atr_risk_bucket"),
        "evidence": block.get("evidence") if isinstance(block.get("evidence"), list) else [],
        "research_only": True,
    }
    if block.get("proxy_disclaimer"):
        out["proxy_disclaimer"] = block.get("proxy_disclaimer")
    # Prefer same atr14 as top-level SR when present and block atr missing
    return out


def _load_structure_sidecar(path):
    """Sidecar JSON: list of structure_v1 rows, or {ts_code: row} / {"rows":[...]}. Keyed by ts_code(+as_of)."""
    if not path:
        return None
    from pathlib import Path as _P
    sp = _P(path)
    if not sp.is_file():
        return None
    raw = json.loads(sp.read_text(encoding="utf-8"))
    rows = []
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        if isinstance(raw.get("rows"), list):
            rows = raw["rows"]
        elif isinstance(raw.get("structure_v1_by_ts_code"), dict):
            rows = list(raw["structure_v1_by_ts_code"].values())
        else:
            # map ts_code -> block
            rows = [v for v in raw.values() if isinstance(v, dict) and (v.get("schema_version") == "structure_v1" or "wyckoff_phase" in v)]
    index = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        ts = str(r.get("ts_code") or "")
        as_of = str(r.get("as_of") or "")
        if not ts:
            continue
        index[(ts, as_of)] = r
        index.setdefault((ts, ""), r)
    return index


FC_KEYS = ("expected_return", "p_up", "q10", "q50", "q90", "confidence", "sample_count", "as_of_date",
           "calibration_status", "terminal_price_q10", "terminal_price_q50", "terminal_price_q90")


def _fc_all(row_fc, det_fc):
    """按 bundle 实际存在的预测期限原样抽取（行 forecasts 为主，details 补充 terminal_price 等）；不补齐缺失期限。
    不设期限白名单：bundle 中出现的任何 horizon_days（如 1/3/5/7/10/20/60）都原样透传，由渲染器按精确期限取用。"""
    out = {}
    hs = set((row_fc or {}).keys()) | set((det_fc or {}).keys()) if isinstance(row_fc, dict) or isinstance(det_fc, dict) else set()
    for h in sorted(hs, key=lambda x: int(x) if str(x).isdigit() else 999):
        a = (row_fc or {}).get(h) if isinstance(row_fc, dict) else None
        d = (det_fc or {}).get(h) if isinstance(det_fc, dict) else None
        a = a if isinstance(a, dict) else {}
        d = d if isinstance(d, dict) else {}
        rec = {k: (a.get(k) if a.get(k) is not None else d.get(k)) for k in FC_KEYS}
        if any(v is not None for k, v in rec.items() if k not in ("as_of_date", "calibration_status")):
            out[str(h)] = rec
    return out


def slim_bundle(b, structure_sidecar=None):
    man = b.get("manifest") or {}
    ov = _g(b, "parts", "overview") or {}
    details = _g(b, "parts", "details") or {}
    rows = []
    for r in ov.get("rows") or []:
        det = details.get(r.get("ts_code")) or {}
        det_avail = _g(det, "availability", "forecasts", "by_horizon")
        q = r.get("quote") or {}
        sr = r.get("support_resistance") or {}
        ee = r.get("entry_exit_ref") or {}
        ret = r.get("returns") or {}
        fc = r.get("forecasts") or {}
        hist = r.get("history") or []
        last_bar = hist[-1] if hist and isinstance(hist[-1], dict) and not hist[-1].get("is_forecast") else None
        rows.append({
            "ts_code": r.get("ts_code"),
            "name": r.get("name"),
            "theme_l1": r.get("theme_l1"),
            "theme_l2": r.get("theme_l2"),
            "grade": r.get("grade"),
            "grade_reason": r.get("grade_reason"),
            "price": r.get("price"),
            "price_basis": r.get("price_basis"),
            "freshness": r.get("freshness"),
            "data_status": r.get("data_status"),
            "return_1d": r.get("return_1d"),
            "return_5d": r.get("return_5d"),
            "returns_basis": ret.get("basis"),
            "returns_as_of": ret.get("as_of_date"),
            "quote_source": q.get("source"),
            "quote_source_time": q.get("source_time"),
            "quote_status": q.get("status"),
            "nearest_support": _level(sr.get("nearest_support")),
            "nearest_resistance": _level(sr.get("nearest_resistance")),
            "sr_as_of": sr.get("snapshot_as_of_date") or sr.get("source_as_of_date"),
            "sr_qualified": sr.get("qualified"),
            "support_zone": ee.get("support_zone"),
            "resistance_zone": ee.get("resistance_zone"),
            "band_position": ee.get("position"),
            "fc1": _fc(fc, "1"),
            "fc5": _fc(fc, "5"),
            "fc": _fc_all(fc, det.get("forecasts")),
            "fc_availability": {h: v.get("status") for h, v in det_avail.items()} if isinstance(det_avail, dict) else None,
            "sr_levels_n": len(sr.get("levels") or []),
            "atr14": sr.get("atr14"),
            "chan_zone": {k: _g(r, "chan", "zone", k) for k in ("lower", "middle", "upper", "qualified")}
            if isinstance(_g(r, "chan", "zone"), dict) else None,
            "kdj_j": _g(r, "kdj", "j"),
            "kdj_label": _g(r, "kdj", "label"),
            "rsi": _g(r, "rsi", "value"),
            "macd_label": _g(r, "macd", "label"),
            "ma_label": _g(r, "ma", "label"),
            "volume_label": _g(r, "volume", "label"),
            "volume_ratio": _g(r, "volume", "ratio"),
            "last_bar": {k: last_bar.get(k) for k in ("date", "open", "high", "low", "close")} if last_bar else None,
            "actionable": r.get("actionable"),
        })
    st = ov.get("sector_timing") or {}
    themes = []
    for t in st.get("themes") or []:
        themes.append({k: t.get(k) for k in ("theme_l1", "observation", "member_count", "add_grade_count",
                                              "reduce_grade_count", "mean_return_5d", "strength_score")})
    return {
        "slim_version": "etf-email-slim-v1.1",
        "manifest": {k: man.get(k) for k in ("sequence", "code_sha", "config_hash", "generated_at", "expires_at",
                                              "actionable", "research_only", "calibration_status", "data_origin")},
        "overview": {k: ov.get(k) for k in ("snapshot_id", "generated_at", "target_trade_date", "actionable",
                                             "research_only", "contains_mock")},
        "sector_timing": {
            "headline": _g(st, "digest", "headline"),
            "add_themes": _g(st, "summary", "add_observation_themes"),
            "reduce_themes": _g(st, "summary", "reduce_observation_themes"),
            "neutral_themes": _g(st, "summary", "neutral_observation_themes"),
            "calibration_status": st.get("calibration_status"),
            "themes": themes,
        } if st else None,
        "rows": rows,
    }


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sidecar = None
    for a in sys.argv[1:]:
        if a.startswith("--structure-sidecar="):
            sidecar = a.split("=", 1)[1]
        elif a == "--structure-sidecar" and args:
            # handled below via explicit flag scan
            pass
    # positional: bundle [out] ; flag --structure-sidecar PATH
    argv = sys.argv[1:]
    sidecar = None
    positional = []
    i = 0
    while i < len(argv):
        if argv[i] == "--structure-sidecar" and i + 1 < len(argv):
            sidecar = argv[i + 1]
            i += 2
            continue
        if argv[i].startswith("--structure-sidecar="):
            sidecar = argv[i].split("=", 1)[1]
            i += 1
            continue
        positional.append(argv[i])
        i += 1
    with open(positional[0], encoding="utf-8") as f:
        data = slim_bundle(json.load(f), structure_sidecar=sidecar)
    txt = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(positional) > 1:
        with open(positional[1], "w", encoding="utf-8") as f:
            f.write(txt)
    else:
        sys.stdout.write(txt)

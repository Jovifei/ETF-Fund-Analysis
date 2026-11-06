# -*- coding: utf-8 -*-
"""ETF Bot 图文版策略邮件渲染器（11:40 / 14:30 / 14:45 / 收盘复核）。

只读输入、只写本地文件；不发送任何邮件。所有数字均来自输入 JSON，缺失字段直接省略。
详见同目录 README.md。
"""
import argparse
import datetime as dt
import html
import json
import os
import sys
import warnings
from collections import Counter, OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from extract_slim import slim_bundle  # noqa: E402
from market_summary import format_market_summary_text, format_market_summary_html, build_market_summary  # noqa: E402
DEFAULT_ATTACH_DIR = "/home/box/agent-data/agents/16301bb9-f7e1-4e48-8d7e-6a397eb81271/attachments"
CST = dt.timezone(dt.timedelta(hours=8))
GRADES = ["可入场", "可试探", "观望", "减仓"]
# A 股惯例：红=积极/上涨，绿=消极/下跌，灰=中性
GRADE_COLOR = {"可入场": "#b71c1c", "可试探": "#f06a4a", "观望": "#9aa0a6", "减仓": "#2e7d32"}
UP_COLOR, DOWN_COLOR, FLAT_COLOR = "#d32f2f", "#2e7d32", "#777777"
OTHER_COLOR = "#9e9e9e"
GRADE_TEXT_COLOR = {"可入场": "#ffffff", "可试探": "#ffffff", "观望": "#1f1f1f", "减仓": "#ffffff"}


def ret_color(x):
    if not is_num(x) or x == 0:
        return FLAT_COLOR
    return UP_COLOR if x > 0 else DOWN_COLOR
SLOT_TAG = {"11:40": "1140", "14:30": "1430", "14:45": "1445", "收盘复核": "close"}
STRATEGY_SLOTS = ("11:40", "14:30", "14:45")
WEEKDAY = "一二三四五六日"
GATE_DESC = OrderedDict([
    ("G1", "上一交易日完整日线"),
    ("G2", "EOD refresh_bars 覆盖完整"),
    ("G3", "本时段槽位 DELIVERED"),
    ("G4", "报价新鲜"),
    ("G5", "指标 as_of 对齐"),
    ("G6", "board 一致且 actionable=false"),
    ("G7", "Jovi 可达"),
])
CJK_FONT_FILES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]
CJK_FONT_NAME = "Noto Sans CJK SC"


# ---------------------------------------------------------------- helpers
def esc(x):
    return html.escape("" if x is None else str(x))


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def fmt_num(x, nd=4):
    if not is_num(x):
        return None
    s = f"{x:.{nd}f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def fmt_pct_ratio(x, nd=2, sign=True):
    """decimal_ratio → 百分比字符串。"""
    if not is_num(x):
        return None
    return f"{x * 100:+.{nd}f}%" if sign else f"{x * 100:.{nd}f}%"


def fmt_pct_already(x, nd=2):
    if not is_num(x):
        return None
    return f"{x:+.{nd}f}%"


def to_cst(ts):
    """ISO 时间 → 北京时间字符串；无时区视为本机（北京）时间。"""
    if not ts:
        return None
    try:
        t = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return str(ts)
    if t.tzinfo is not None:
        t = t.astimezone(CST)
    return t.strftime("%Y-%m-%d %H:%M:%S")


def code6(ts_code):
    return (ts_code or "").split(".")[0]


def date_label(d):
    try:
        x = dt.date.fromisoformat(d)
        return f"{d}，周{WEEKDAY[x.weekday()]}"
    except ValueError:
        return d


def zone_text(zone, near):
    parts = []
    if isinstance(zone, dict) and is_num(zone.get("low")) and is_num(zone.get("high")):
        lo, hi = fmt_num(zone["low"]), fmt_num(zone["high"])
        parts.append(lo if lo == hi else f"{lo}–{hi}")
    elif isinstance(near, dict) and is_num(near.get("zone_low")) and is_num(near.get("zone_high")):
        lo, hi = fmt_num(near["zone_low"]), fmt_num(near["zone_high"])
        parts.append(lo if lo == hi else f"{lo}–{hi}")
    if isinstance(near, dict) and is_num(near.get("distance_pct")):
        parts.append(f"距 {fmt_pct_already(near['distance_pct'])}")
    return "，".join(parts) if parts else None


# ---------------------------------------------------------------- inputs
def load_data(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if "parts" in d and "manifest" in d:
        return slim_bundle(d)
    if d.get("slim_version"):
        return d
    # 兼容旧版提取（etf_1445_slim 等）：字段名映射，仅取存在的
    rows = []
    for r in d.get("rows") or []:
        rows.append({
            "ts_code": r.get("ts_code"), "name": r.get("name"), "grade": r.get("grade"),
            "grade_reason": r.get("grade_reason") or r.get("reason"),
            "price": r.get("price") if is_num(r.get("price")) else (r.get("last") if is_num(r.get("last")) else None),
            "return_5d": r.get("return_5d", r.get("ret_5d")),
            "quote_source_time": r.get("quote_source_time"),
            "theme_l1": r.get("theme_l1"), "theme_l2": r.get("theme_l2"),
            "nearest_support": r.get("nearest_support"), "nearest_resistance": r.get("nearest_resistance"),
            "support_zone": r.get("support_zone") or (r.get("entry_exit_ref") or {}).get("support_zone"),
            "resistance_zone": r.get("resistance_zone") or (r.get("entry_exit_ref") or {}).get("resistance_zone"),
            "actionable": r.get("actionable"),
        })
    return {"slim_version": "legacy", "manifest": d.get("manifest") or {}, "overview": d.get("overview") or {},
            "sector_timing": None, "rows": rows}


def load_prev(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if isinstance(d, dict) and all(isinstance(v, str) for v in d.values()) and d:
        return {k: {"grade": v} for k, v in d.items()}  # {ts_code: grade}
    data = load_data(path)
    return {r["ts_code"]: r for r in data["rows"] if r.get("ts_code")}


def load_gates(path):
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    g = d.get("gates", d) if isinstance(d, dict) else {}
    out = OrderedDict()
    for k in sorted(g, key=lambda s: (len(s), s)):
        if not str(k).upper().startswith("G"):
            continue
        v = g[k]
        if isinstance(v, bool):
            out[k] = {"pass": v, "note": None}
        elif isinstance(v, dict) and "pass" in v:
            out[k] = {"pass": bool(v["pass"]), "note": v.get("note")}
    return out


# ---------------------------------------------------------------- charts
def setup_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager, rcParams
    found = False
    for p in CJK_FONT_FILES:
        if os.path.exists(p):
            font_manager.fontManager.addfont(p)
            found = True
    if not found:
        raise SystemExit("未找到 CJK 字体（Noto Sans CJK），请先安装 fonts-noto-cjk")
    rcParams["font.family"] = "sans-serif"
    rcParams["font.sans-serif"] = [CJK_FONT_NAME, "DejaVu Sans"]
    rcParams["axes.unicode_minus"] = False
    rcParams["savefig.dpi"] = 150
    import matplotlib.pyplot as plt
    return plt


class GlyphGuard:
    """捕获 matplotlib 的缺字警告；出现即视为失败（防止豆腐块）。"""

    def __enter__(self):
        self._cm = warnings.catch_warnings(record=True)
        self.w = self._cm.__enter__()
        warnings.simplefilter("always")
        return self

    def __exit__(self, *a):
        self._cm.__exit__(*a)
        bad = [str(x.message) for x in self.w if "missing from" in str(x.message) or "Glyph" in str(x.message)]
        if bad:
            raise RuntimeError("图表缺字: " + "; ".join(sorted(set(bad))[:5]))


def save(fig, path, plt):
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    if os.path.getsize(path) > 1024 * 1024:  # 超 1MB 降 dpi 重存
        raise RuntimeError(f"{path} 超过 1MB")


def chart_grade_dist(plt, counts, title, path):
    labels = [g for g in GRADES] + [g for g in counts if g not in GRADES]
    vals = [counts.get(g, 0) for g in labels]
    colors = [GRADE_COLOR.get(g, OTHER_COLOR) for g in labels]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    bars = ax.bar(labels, vals, color=colors, width=0.6)
    total = sum(vals)
    for b, v in zip(bars, vals):
        pct = f"{v / total * 100:.0f}%" if total else ""
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + max(vals) * 0.02, f"{v} 只  {pct}",
                ha="center", va="bottom", fontsize=12, fontweight="bold")
    ax.set_ylim(0, max(vals) * 1.22 if vals and max(vals) else 1)
    ax.set_title(title, fontsize=14, fontweight="bold", loc="left")
    ax.set_ylabel("标的数")
    ax.tick_params(axis="x", labelsize=13)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    save(fig, path, plt)


def chart_grade_tiles(plt, rows, title, path):
    """按分级分组的色块网格：每格显示名称、代码、当日涨跌（若有）。"""
    order = {g: i for i, g in enumerate(GRADES)}
    rs = sorted(rows, key=lambda r: (order.get(r.get("grade"), 9),
                                     -(r["return_1d"] if is_num(r.get("return_1d")) else -9e9)))
    ncol = 5
    nrow = (len(rs) + ncol - 1) // ncol
    fig_w, cell_h = 10, 0.78
    fig, ax = plt.subplots(figsize=(fig_w, nrow * cell_h + 0.9))
    ax.set_xlim(0, ncol)
    ax.set_ylim(nrow, -0.05)
    ax.axis("off")
    for i, r in enumerate(rs):
        c, rr = i % ncol, i // ncol
        g = r.get("grade")
        ax.add_patch(plt.Rectangle((c + 0.03, rr + 0.05), 0.94, 0.9, color=GRADE_COLOR.get(g, OTHER_COLOR), lw=0))
        tc = GRADE_TEXT_COLOR.get(g, "#ffffff")
        ax.text(c + 0.5, rr + 0.33, r.get("name") or "", ha="center", va="center", fontsize=10.5,
                fontweight="bold", color=tc)
        sub = code6(r.get("ts_code"))
        p = fmt_pct_ratio(r.get("return_1d"))
        if p:
            x = r["return_1d"]
            sub += f"  {'▲' if x > 0 else ('▼' if x < 0 else '—')}{p}"
        ax.text(c + 0.5, rr + 0.68, sub, ha="center", va="center", fontsize=9, color=tc)
    ax.set_title(title, fontsize=14, fontweight="bold", loc="left", pad=30)
    handles = [plt.Rectangle((0, 0), 1, 1, color=GRADE_COLOR[g]) for g in GRADES]
    ax.legend(handles, GRADES, ncol=4, loc="lower left", bbox_to_anchor=(0.0, 1.0), borderaxespad=0.2,
              frameon=False, fontsize=10.5, handlelength=1.2)
    save(fig, path, plt)


def chart_transition(plt, changes, prev_counts, cur_counts, prev_label, cur_label, title, path):
    import numpy as np
    labels = GRADES
    m = np.zeros((4, 4), dtype=int)
    for pg, cg in changes["pairs"]:
        if pg in labels and cg in labels:
            m[labels.index(pg), labels.index(cg)] += 1
    off = m.copy()
    np.fill_diagonal(off, 0)
    fig, ax = plt.subplots(figsize=(7.2, 5.4))
    import matplotlib.colors as mcolors
    # A 股惯例：升档（列在左、更积极）用红，降档用绿；颜色深浅＝只数
    vmax = max(1, off.max())
    up_c = mcolors.LinearSegmentedColormap.from_list("u", ["#fdecea", UP_COLOR])
    dn_c = mcolors.LinearSegmentedColormap.from_list("d", ["#e8f5e9", DOWN_COLOR])
    rgb = np.ones((4, 4, 4))
    for i in range(4):
        for j in range(4):
            v = off[i, j]
            if i == j or not v:
                rgb[i, j] = mcolors.to_rgba("#f4f6f8")
            else:
                rgb[i, j] = (up_c if j < i else dn_c)(0.35 + 0.65 * v / vmax)
    ax.imshow(rgb)
    for i in range(4):
        for j in range(4):
            v = m[i, j]
            if v and i == j:
                ax.text(j, i, f"{v}\n不变", ha="center", va="center", fontsize=12, color="#777")
            elif v:
                ax.text(j, i, str(v), ha="center", va="center", fontsize=15, fontweight="bold",
                        color="white" if v > vmax * 0.45 else "#1a1a1a")
            if i == j:
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, ec="#888", lw=1.2, ls="--"))
    ax.set_xticks(range(4), [f"{g}\n({cur_counts.get(g, 0)})" for g in labels], fontsize=11)
    ax.set_yticks(range(4), [f"{g} ({prev_counts.get(g, 0)})" for g in labels], fontsize=11)
    ax.set_xlabel(f"{cur_label} 分级", fontsize=12)
    ax.set_ylabel(f"{prev_label} 分级", fontsize=12)
    ax.set_title(title, fontsize=13.5, fontweight="bold", loc="left", pad=24)
    ax.text(0, 1.015, "行=前一时段，列=本时段；红格＝升档，绿格＝降档，虚线框（灰字）＝不变", transform=ax.transAxes,
            fontsize=9.5, color="#555", va="bottom")
    save(fig, path, plt)


def chart_return_rank(plt, rows, title, path):
    rs = [r for r in rows if is_num(r.get("return_1d"))]
    rs.sort(key=lambda r: r["return_1d"])
    fig, ax = plt.subplots(figsize=(8, 0.28 * len(rs) + 1.2))
    vals = [r["return_1d"] * 100 for r in rs]
    names = [f"{r.get('name')}（{code6(r.get('ts_code'))}）· {r.get('grade') or ''}" for r in rs]
    ax.barh(range(len(rs)), vals, color=[ret_color(r["return_1d"]) for r in rs], height=0.7)
    ax.set_yticks(range(len(rs)), names, fontsize=9)
    for lab, r in zip(ax.get_yticklabels(), rs):
        lab.set_color("#5f6368" if r.get("grade") == "观望" else GRADE_COLOR.get(r.get("grade"), "#333"))
        lab.set_fontweight("bold")
    ax.axvline(0, color="#333", lw=0.8)
    span = max(abs(v) for v in vals) if vals else 1
    for i, v in enumerate(vals):
        ax.text(v + (span * 0.02 if v >= 0 else -span * 0.02), i, f"{v:+.2f}%", va="center",
                ha="left" if v >= 0 else "right", fontsize=8.5)
    ax.set_xlim(-span * 1.3, span * 1.3)
    ax.set_xlabel("当日涨跌幅（%）", labelpad=2)
    ax.set_title(title, fontsize=13.5, fontweight="bold", loc="left")
    handles = [plt.Rectangle((0, 0), 1, 1, color=UP_COLOR), plt.Rectangle((0, 0), 1, 1, color=DOWN_COLOR)]
    ax.legend(handles, ["上涨", "下跌"], ncol=2, loc="lower right", fontsize=9, frameon=False)
    ax.text(0, -0.06 - 0.6 / max(len(rs), 1), "柱色：红涨绿跌；左侧名称颜色＝分级（深红可入场、橙红可试探、灰观望、绿减仓）",
            transform=ax.transAxes, fontsize=8.5, color="#555", va="top")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="x", alpha=0.25)
    save(fig, path, plt)


def chart_concept_board(plt, concepts, title, path):
    """概念强弱横条：最强/最弱各若干，钉住项置顶并加星标。pct_change 已为百分数。"""
    concepts = concepts or {}
    rows = []
    for p in concepts.get("pinned") or []:
        if p.get("missing"):
            continue
        if p.get("pct_change") is None:
            continue
        label = f"★ {p.get('sector_name')}"
        if not p.get("same_day") and p.get("as_of"):
            label += f"（as_of {p['as_of']}）"
        rows.append({"name": label, "pct": float(p["pct_change"]), "pinned": True})
    for it in concepts.get("strongest") or []:
        if it.get("pct_change") is None:
            continue
        rows.append({"name": it.get("sector_name"), "pct": float(it["pct_change"]), "pinned": False})
    for it in concepts.get("weakest") or []:
        if it.get("pct_change") is None:
            continue
        rows.append({"name": it.get("sector_name"), "pct": float(it["pct_change"]), "pinned": False})
    # de-dupe by name keeping first (pinned first)
    seen, uniq = set(), []
    for r in rows:
        k = r["name"].lstrip("★ ").split("（as_of")[0]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    rows = uniq
    if not rows:
        raise ValueError("concepts empty for chart")
    # sort: pinned first (keep order), then by pct desc for rest
    pinned = [r for r in rows if r.get("pinned")]
    rest = sorted([r for r in rows if not r.get("pinned")], key=lambda r: r["pct"], reverse=True)
    rows = pinned + rest
    fig, ax = plt.subplots(figsize=(8, 0.32 * len(rows) + 1.4))
    vals = [r["pct"] for r in rows]
    names = [r["name"] for r in rows]
    colors = [UP_COLOR if v >= 0 else DOWN_COLOR for v in vals]
    ax.barh(range(len(rows)), vals, color=colors, height=0.7)
    ax.set_yticks(range(len(rows)), names, fontsize=9)
    for lab, r in zip(ax.get_yticklabels(), rows):
        if r.get("pinned"):
            lab.set_fontweight("bold")
            lab.set_color("#b71c1c")
    ax.axvline(0, color="#333", lw=0.8)
    span = max(abs(v) for v in vals) if vals else 1
    for i, v in enumerate(vals):
        ax.text(v + (span * 0.02 if v >= 0 else -span * 0.02), i, f"{v:+.2f}%", va="center",
                ha="left" if v >= 0 else "right", fontsize=8.5)
    ax.set_xlim(-span * 1.35, span * 1.35)
    ax.set_xlabel("涨跌幅（%）", labelpad=2)
    ax.set_title(title, fontsize=13.5, fontweight="bold", loc="left")
    n = concepts.get("count")
    ax.text(0, -0.08 - 0.5 / max(len(rows), 1),
            f"红涨绿跌；★ 为钉住概念（默认 CPO概念）。当日概念条数 {n if n is not None else '—'}。",
            transform=ax.transAxes, fontsize=8.5, color="#555", va="top")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="x", alpha=0.25)
    # invert so first row (pinned) at top
    ax.invert_yaxis()
    save(fig, path, plt)


# ---------------------------------------------------------------- model
def build_context(data, slot, date, prev, prev_label, gates, bundle_name, bundle_id, market_summary=None):
    rows = data["rows"]
    man, ov = data.get("manifest") or {}, data.get("overview") or {}
    counts = Counter(r.get("grade") for r in rows)
    qtimes = sorted(t for t in (r.get("quote_source_time") for r in rows) if t)
    q_status = Counter(r.get("quote_status") for r in rows if r.get("quote_status"))
    q_src = Counter(r.get("quote_source") for r in rows if r.get("quote_source"))
    sr_asof = Counter(r.get("sr_as_of") for r in rows if r.get("sr_as_of"))
    fc_asof = Counter((r.get("fc1") or {}).get("as_of_date") for r in rows if (r.get("fc1") or {}).get("as_of_date"))
    ret_basis = Counter(r.get("returns_basis") for r in rows if r.get("returns_basis"))
    changes = None
    if prev:
        allc, same, pairs = [], 0, []
        for r in rows:
            p = prev.get(r.get("ts_code"))
            if not p or not p.get("grade"):
                continue
            pairs.append((p["grade"], r.get("grade")))
            if p["grade"] == r.get("grade"):
                same += 1
                continue
            allc.append({"ts_code": r["ts_code"], "name": r.get("name"), "prev": p["grade"], "cur": r.get("grade"),
                         "prev_price": p.get("price") if is_num(p.get("price")) else None,
                         "cur_price": r.get("price"), "reason": r.get("grade_reason")})
        rank = {g: i for i, g in enumerate(GRADES)}
        allc.sort(key=lambda c: (rank.get(c["cur"], 9), rank.get(c["prev"], 9)))
        prev_counts = Counter(p.get("grade") for k, p in prev.items() if k in {r["ts_code"] for r in rows})
        changes = {"all": allc, "same": same, "pairs": pairs, "prev_counts": prev_counts,
                   "matched": same + len(allc), "label": prev_label}
    return {
        "slot": slot, "date": date, "rows": rows, "manifest": man, "overview": ov, "counts": counts,
        "qtimes": (qtimes[0], qtimes[-1]) if qtimes else None, "q_status": q_status, "q_src": q_src,
        "sr_asof": sr_asof, "fc_asof": fc_asof, "ret_basis": ret_basis, "changes": changes, "gates": gates,
        "sector": data.get("sector_timing"),
        "market_summary": market_summary,
        "bundle_name": bundle_name, "bundle_id": bundle_id,
    }


def counter_text(c):
    return "；".join(f"{k} {v}/{sum(c.values())}" for k, v in c.most_common())


def meta_lines(ctx):
    """数据来源与时间戳（纯文本行列表），仅输出存在的字段。"""
    man, ov, L = ctx["manifest"], ctx["overview"], []
    if ov.get("target_trade_date"):
        L.append(f"目标交易日 target_trade_date：{ov['target_trade_date']}")
    if ctx["qtimes"]:
        a, b = ctx["qtimes"]
        L.append(f"报价 source_time：{a} 至 {b}（北京时间），{sum(1 for r in ctx['rows'] if r.get('quote_source_time'))}/{len(ctx['rows'])} 只")
    if ctx["q_src"]:
        L.append(f"报价来源：{counter_text(ctx['q_src'])}")
    if ctx["q_status"]:
        L.append(f"报价状态：{counter_text(ctx['q_status'])}")
    if ctx["sr_asof"]:
        L.append(f"指标/支撑压力 as_of：{counter_text(ctx['sr_asof'])}")
    if ctx["fc_asof"]:
        L.append(f"预测 as_of：{counter_text(ctx['fc_asof'])}")
    if ctx["ret_basis"]:
        L.append(f"涨跌幅口径：{counter_text(ctx['ret_basis'])}")
    if ov.get("generated_at"):
        L.append(f"看板生成时间：{to_cst(ov['generated_at'])}（北京时间）")
    if man.get("generated_at"):
        L.append(f"bundle 生成时间：{to_cst(man['generated_at'])}（北京时间）")
    ids = []
    if ctx["bundle_name"]:
        ids.append(f"bundle={ctx['bundle_name']}")
    if ctx["bundle_id"]:
        ids.append(f"bundle_id={ctx['bundle_id']}")
    if man.get("sequence") is not None:
        ids.append(f"sequence={man['sequence']}")
    if ov.get("snapshot_id"):
        ids.append(f"snapshot_id={ov['snapshot_id']}")
    if man.get("code_sha"):
        ids.append(f"code_sha={man['code_sha'][:12]}")
    if ids:
        L.append("标识：" + "；".join(ids))
    flags = []
    if man.get("actionable") is not None or ov.get("actionable") is not None:
        flags.append(f"actionable={str(bool(man.get('actionable') or ov.get('actionable'))).lower()}")
    if man.get("calibration_status"):
        flags.append(f"calibration_status={man['calibration_status']}")
    if man.get("research_only") or ov.get("research_only"):
        flags.append("research_only=true")
    if flags:
        L.append("标记：" + "；".join(flags))
    return L


def gate_lines(gates):
    if gates is None:
        return None
    out = []
    for k, v in gates.items():
        s = f"{k} {GATE_DESC.get(k, '')}：{'通过' if v['pass'] else '失败'}"
        if v.get("note"):
            s += f"（{v['note']}）"
        out.append(s)
    return out


def row_detail(r):
    """单只标的的说明要素（列表），仅含存在的字段。"""
    d = []
    if r.get("grade_reason"):
        d.append(f"理由：{r['grade_reason']}")
    sig = []
    for lab, key in (("MA", "ma_label"), ("MACD", "macd_label"), ("KDJ", "kdj_label"), ("量能", "volume_label")):
        if r.get(key):
            sig.append(f"{lab} {r[key]}")
    if is_num(r.get("kdj_j")):
        sig.append(f"J={fmt_num(r['kdj_j'], 1)}")
    if is_num(r.get("rsi")):
        sig.append(f"RSI={fmt_num(r['rsi'], 1)}")
    if sig:
        d.append("信号：" + "，".join(sig))
    if r.get("theme_l1"):
        d.append("主题：" + "/".join(x for x in (r.get("theme_l1"), r.get("theme_l2")) if x))
    return d


# ---------------------------------------------------------------- forecasts / levels
# 列名 → bundle 中的期限键（交易日，horizon_days）。只做精确映射：明日=1、3日=3、7日=7、一个月=20、3个月=60；
# 不插值、不外推、不以其他期限替代（5/10 日数据不用于 7日/一个月）。数据缺少的期限一律显示「当前未提供」。
HZ_COLS = [("明日", ("1",)), ("3日", ("3",)), ("7日", ("7",)), ("一个月", ("20",)), ("3个月", ("60",))]
OPTIONAL_HZ = set()  # 五个期限均为用户指定列，始终显示
NA = "当前未提供"

# Phase A research display (structure_v1) — proxy labels only; never feed assign_grade
WYCKOFF_PHASE_ZH = {
    "unknown": "未知",
    "accumulation": "吸筹",
    "markup": "拉升",
    "distribution": "派发",
    "markdown": "下跌",
    "reaccumulation": "再吸筹",
    "redistribution": "再派发",
    "range": "震荡",
}
DOW_PHASE_ZH = {
    "unknown": "未知",
    "uptrend": "上升趋势",
    "downtrend": "下降趋势",
    "correction_in_uptrend": "升势回调",
    "rally_in_downtrend": "跌势反弹",
    "sideways": "横盘",
}
ATR_BUCKET_ZH = {
    "unknown": "未知",
    "low": "低波",
    "mid": "中波",
    "high": "高波",
    "extreme": "极端",
}
STRUCTURE_PROXY_DISCLAIMER = (
    "威科夫/道氏列为 OHLCV 代理相位（非资金流）；ATR 风险桶复用 atr14。结构影子为冻结 soft_c 权重的并行研究信号，仅展示，不参与五档分级。"
)

# Phase B1 bypass: frozen soft_c_strict overlay (same constants as
# backend/app/research/structure_shadow.py; keep in sync). Never feeds 分级.
SHADOW_ATR_SCALE = {"low": 1.0, "mid": 0.9, "high": 0.4, "extreme": 0.0, "unknown": 0.4}


def structure_shadow_signal(sv):
    """Ternary shadow signal from a structure_v1 block; missing/invalid → None."""
    if not isinstance(sv, dict):
        return None
    try:
        wy_s = float(sv.get("wyckoff_score"))
        wy_c = float(sv.get("wyckoff_confidence"))
        dow_s = float(sv.get("dow_score"))
        dow_c = float(sv.get("dow_confidence"))
    except (TypeError, ValueError):
        return None
    raw = (0.40 * wy_s * wy_c + 0.60 * dow_s * dow_c) / 1.0
    if (wy_c + dow_c) / 2.0 < 0.45:
        raw = 0.0
    score = max(-1.0, min(1.0, raw * SHADOW_ATR_SCALE.get(sv.get("atr_risk_bucket") or "unknown", 0.4)))
    if score >= 0.30:
        label = "偏多"
    elif score <= -0.30:
        label = "偏空"
    elif abs(score) < 0.12:
        label = "中性"
    elif score > 0:
        label = "弱偏多"
    else:
        label = "弱偏空"
    return f"{label} {'+' if score >= 0 else ''}{score:.2f}"


def structure_shadow_col(r):
    sh = r.get("structure_shadow") if isinstance(r, dict) else None
    if isinstance(sh, dict) and sh.get("signal"):
        score = sh.get("score")
        if is_num(score):
            return f"{sh['signal']} {'+' if score >= 0 else ''}{float(score):.2f}"
        return str(sh["signal"])
    return structure_shadow_signal(structure_v1_of(r)) or "—"


def structure_v1_of(r):
    sv = r.get("structure_v1") if isinstance(r, dict) else None
    return sv if isinstance(sv, dict) else None


def structure_col(r, kind):
    """Return Chinese display for 威科夫 / 道氏 / ATR风险桶; missing → —."""
    sv = structure_v1_of(r)
    if not sv:
        return "—"
    if kind == "wyckoff":
        raw = sv.get("wyckoff_phase")
        return WYCKOFF_PHASE_ZH.get(raw, "—") if raw else "—"
    if kind == "dow":
        raw = sv.get("dow_phase")
        return DOW_PHASE_ZH.get(raw, "—") if raw else "—"
    if kind == "atr":
        raw = sv.get("atr_risk_bucket")
        return ATR_BUCKET_ZH.get(raw, "—") if raw else "—"
    return "—"



def fc_get(r, keys):
    fc = r.get("fc") or {}
    for k in keys:
        if isinstance(fc.get(k), dict) and is_num(fc[k].get("expected_return")):
            return fc[k]
    legacy = {"1": r.get("fc1"), "5": r.get("fc5")}
    for k in keys:
        x = legacy.get(k)
        if isinstance(x, dict) and is_num(x.get("expected_return")):
            return x
    return None


def horizon_cols(rows):
    cols = []
    for lab, keys in HZ_COLS:
        have = any(fc_get(r, keys) for r in rows)
        if lab in OPTIONAL_HZ and not have:
            continue
        cols.append((lab, keys, have))
    return cols


def fc_asof(rows):
    used = {k for _, keys in HZ_COLS for k in keys}  # 仅统计邮件实际展示的期限
    return Counter(f.get("as_of_date") for r in rows for h, f in (r.get("fc") or {}).items()
                   if str(h) in used and isinstance(f, dict) and f.get("as_of_date"))


def fc_cell_text(f):
    bits = [f"预测涨幅 {fmt_pct_ratio(f.get('expected_return'))}"]
    if is_num(f.get("p_up")):
        bits.append(f"上涨概率 {fmt_pct_ratio(f['p_up'], sign=False)}")
    return "，".join(b for b in bits if b)


def lvl_zone(near, zone):
    if isinstance(near, dict) and is_num(near.get("zone_low")) and is_num(near.get("zone_high")):
        return near["zone_low"], near["zone_high"]
    if isinstance(zone, dict) and is_num(zone.get("low")) and is_num(zone.get("high")):
        return zone["low"], zone["high"]
    if isinstance(near, dict) and is_num(near.get("price")):
        return near["price"], near["price"]
    return None


def zstr(z):
    if not z:
        return None
    a, b = fmt_num(z[0]), fmt_num(z[1])
    return a if a == b else f"{a}–{b}"


def ee_same_as_nearest(r):
    def same(near, zone):
        z1 = lvl_zone(near, None)
        z2 = (zone["low"], zone["high"]) if isinstance(zone, dict) and is_num(zone.get("low")) and is_num(zone.get("high")) else None
        return z2 is None or (z1 is not None and abs(z1[0] - z2[0]) < 1e-9 and abs(z1[1] - z2[1]) < 1e-9)
    return same(r.get("nearest_support"), r.get("support_zone")) and same(r.get("nearest_resistance"), r.get("resistance_zone"))


def ordered_rows(rows):
    out = []
    for g in GRADES + sorted({r.get("grade") for r in rows} - set(GRADES), key=str):
        out += [r for r in rows if r.get("grade") == g]
    return out


def chart_forecast_heat(plt, rows, cols, title, path):
    import matplotlib.colors as mcolors
    rs = ordered_rows(rows)
    n, m = len(rs), len(cols)
    vals = [fc_get(r, k)["expected_return"] for r in rs for _, k, h in cols if h and fc_get(r, k)]
    vmax = max([abs(v) for v in vals] or [1]) or 1
    up_c = mcolors.LinearSegmentedColormap.from_list("u", ["#ffffff", UP_COLOR])
    dn_c = mcolors.LinearSegmentedColormap.from_list("d", ["#ffffff", DOWN_COLOR])
    fig, ax = plt.subplots(figsize=(1.45 * m + 2.8, 0.44 * n + 1.5))
    ax.set_xlim(0, m)
    ax.set_ylim(n, 0)
    for j, (lab, keys, have) in enumerate(cols):
        if not have:  # 整列无数据：合并灰色列，明确标注「当前未提供」
            ax.add_patch(plt.Rectangle((j, 0), 1, n, color="#eeeeee", lw=0))
            for yy in sorted({0.5, n / 2, max(n - 0.5, 0.5)}):
                ax.text(j + 0.5, yy, NA, ha="center", va="center", fontsize=9.5, color="#777", fontweight="bold")
            continue
        for i, r in enumerate(rs):
            f = fc_get(r, keys)
            if f:
                v = f["expected_return"]
                col = (up_c if v > 0 else dn_c)(0.12 + 0.75 * abs(v) / vmax) if v else "#f4f4f4"
                ax.add_patch(plt.Rectangle((j, i), 1, 1, color=col, lw=0))
                fg = "white" if abs(v) / vmax > 0.6 else "#1a1a1a"
                pu = f"上涨 {f['p_up'] * 100:.0f}%" if is_num(f.get("p_up")) else "上涨 —"
                ax.text(j + 0.5, i + 0.5, f"{fmt_pct_ratio(v)}  {pu}", ha="center", va="center", fontsize=8.4, color=fg)
            else:
                ax.add_patch(plt.Rectangle((j, i), 1, 1, color="#eeeeee", lw=0))
                ax.text(j + 0.5, i + 0.5, NA, ha="center", va="center", fontsize=7.6, color="#888")
    for j in range(m + 1):
        ax.axvline(j, color="white", lw=1.2)
    for i in range(n + 1):
        ax.axhline(i, color="white", lw=0.8)
    ax.set_xticks([j + 0.5 for j in range(m)],
                  [f"{lab}\n（{keys[0]} 交易日）" if have else f"{lab}\n（{NA}）" for lab, keys, have in cols], fontsize=10)
    for t, (_, _, have) in zip(ax.get_xticklabels(), cols):
        t.set_color("#1a1a1a" if have else "#888")
    ax.xaxis.tick_top()
    ax.set_yticks([i + 0.5 for i in range(n)], [f"{r.get('name')}（{code6(r.get('ts_code'))}）" for r in rs], fontsize=8.6)
    for lab_, r in zip(ax.get_yticklabels(), rs):
        lab_.set_color("#5f6368" if r.get("grade") == "观望" else GRADE_COLOR.get(r.get("grade"), "#333"))
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title(title, fontsize=13, fontweight="bold", loc="left", pad=36)
    ax.text(0, -0.035 - 0.5 / n, "单元格＝预测涨幅（期望收益，红正绿负）与上涨概率；灰色＝当前未提供；模型未校准（not_calibrated），仅供研究",
            transform=ax.transAxes, fontsize=8.5, color="#555", va="top")
    save(fig, path, plt)


def chart_sr_range(plt, rows, title, path):
    rs = [r for r in ordered_rows(rows) if is_num(r.get("price")) and r["price"] > 0
          and (lvl_zone(r.get("nearest_support"), r.get("support_zone")) or lvl_zone(r.get("nearest_resistance"), r.get("resistance_zone")))]
    n = len(rs)
    fig, ax = plt.subplots(figsize=(9, 0.34 * n + 1.5))
    xs = []
    for i, r in enumerate(rs):
        p = r["price"]
        pc = lambda x: (x - p) / p * 100
        f1 = fc_get(r, ("1",))
        xl = xr = 0
        if f1 and is_num(f1.get("terminal_price_q10")) and is_num(f1.get("terminal_price_q90")):
            a, b = pc(f1["terminal_price_q10"]), pc(f1["terminal_price_q90"])
            xl, xr = a, b
            ax.plot([a, b], [i, i], color="#b0b4ba", lw=6, solid_capstyle="butt", zorder=1)
            xs += [a, b]
        sz = lvl_zone(r.get("nearest_support"), r.get("support_zone"))
        if sz:
            a, b = pc(sz[0]), pc(sz[1])
            w = max(b - a, 0.06)
            ax.barh(i, w, left=a if b - a >= 0.06 else a - 0.03, height=0.55, color=DOWN_COLOR, zorder=2)
            ax.text(min(a, xl) - 0.08, i, fmt_num(sz[0]), ha="right", va="center", fontsize=7.6, color=DOWN_COLOR,
                    bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.85), zorder=4)
            xs.append(a)
        rz = lvl_zone(r.get("nearest_resistance"), r.get("resistance_zone"))
        if rz:
            a, b = pc(rz[0]), pc(rz[1])
            w = max(b - a, 0.06)
            ax.barh(i, w, left=a if b - a >= 0.06 else a - 0.03, height=0.55, color=UP_COLOR, zorder=2)
            ax.text(max(b, xr) + 0.08, i, fmt_num(rz[1]), ha="left", va="center", fontsize=7.6, color=UP_COLOR,
                    bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.85), zorder=4)
            xs.append(b)
        ax.plot([0], [i], "o", color="#111", ms=5, zorder=3)
    span = max([abs(x) for x in xs] or [1])
    ax.set_xlim(-span * 1.3, span * 1.3)
    ax.set_ylim(n - 0.4, -0.6)
    ax.axvline(0, color="#111", lw=0.8, zorder=0)
    ax.set_yticks(range(n), [f"{r.get('name')}（{code6(r.get('ts_code'))}） {fmt_num(r['price'])}" for r in rs], fontsize=8.6)
    for lab_, r in zip(ax.get_yticklabels(), rs):
        lab_.set_color("#5f6368" if r.get("grade") == "观望" else GRADE_COLOR.get(r.get("grade"), "#333"))
    ax.set_xlabel("相对现价（%）", fontsize=10)
    ax.grid(axis="x", alpha=0.25)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=DOWN_COLOR), plt.Rectangle((0, 0), 1, 1, color=UP_COLOR),
               plt.Line2D([0], [0], marker="o", color="#111", lw=0, ms=5), plt.Line2D([0], [0], color="#b0b4ba", lw=6)]
    ax.legend(handles, ["最近支撑区", "最近压力区", "现价", "明日预测 q10–q90（未校准）"], ncol=4, fontsize=8.5,
              frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0))
    ax.set_title(title, fontsize=13, fontweight="bold", loc="left", pad=26)
    save(fig, path, plt)


# ---------------------------------------------------------------- text body
def slot_title(slot):
    return "收盘复核" if slot == "收盘复核" else f"{slot} 买卖策略"


def render_text(ctx, charts_meta):
    slot, date = ctx["slot"], ctx["date"]
    T = [f"【ETF Bot】{slot_title(slot)}（{date_label(date)}）", ""]
    T.append("一、数据来源与时间戳")
    for i, l in enumerate(meta_lines(ctx), 1):
        T.append(f"{i}. {l}")
    T.append("")
    T.append("二、数据闸门")
    gl = gate_lines(ctx["gates"])
    if gl is None:
        T.append("本次渲染未附闸门结果。")
    else:
        T.append("全部通过。" if all(v["pass"] for v in ctx["gates"].values()) else "存在失败项。")
        T += [f"- {x}" for x in gl]
    T.append("")
    T.append("三、分级分布（图1）")
    c = ctx["counts"]
    T.append("；".join(f"{g} {c.get(g, 0)} 只" for g in GRADES + [g for g in c if g not in GRADES]) + f"；合计 {len(ctx['rows'])} 只。")
    T.append("")
    sec = 4
    ch = ctx["changes"]
    if ch is not None:
        T.append(f"{'四五六七八'[sec - 4]}、相对 {ch['label']} 的变化（图3）")
        T.append(f"可比 {ch['matched']} 只：分级不变 {ch['same']} 只，变化 {len(ch['all'])} 只。")
        pc = ch["prev_counts"]
        T.append(f"{ch['label']} 分布：" + "；".join(f"{g} {pc.get(g, 0)} 只" for g in GRADES))
        for i, x in enumerate(ch["all"], 1):
            pp = f"（{fmt_num(x['prev_price'])}）" if x["prev_price"] is not None else ""
            cp = f"（{fmt_num(x['cur_price'])}）" if is_num(x["cur_price"]) else ""
            T.append(f"{i}. {x['name']}（{code6(x['ts_code'])}）：「{x['prev']}」{pp} → 「{x['cur']}」{cp}")
        T.append("")
        sec += 1
    st = ctx["sector"]
    if st and (st.get("add_themes") or st.get("reduce_themes") or st.get("themes")):
        T.append(f"{'四五六七八'[sec - 4]}、板块观察（sector_timing，未校准）")
        if st.get("add_themes"):
            T.append("偏强观察：" + "、".join(st["add_themes"]))
        if st.get("reduce_themes"):
            T.append("偏弱观察：" + "、".join(st["reduce_themes"]))
        if st.get("neutral_themes"):
            T.append("中性：" + "、".join(st["neutral_themes"]))
        for t in st.get("themes") or []:
            bits = [t.get("observation") or ""]
            if t.get("member_count") is not None:
                bits.append(f"成员 {t['member_count']}")
            if is_num(t.get("mean_return_5d")):
                bits.append(f"近5日均收益 {fmt_pct_ratio(t['mean_return_5d'])}")
            if is_num(t.get("strength_score")):
                bits.append(f"强度 {fmt_num(t['strength_score'], 2)}")
            T.append(f"- {t.get('theme_l1')}：" + "，".join(b for b in bits if b))
        T.append("")
        sec += 1
    T.append(f"{'四五六七八九十'[sec - 4]}、逐标的决策点（图2 为色块总览" + ("，图4 为当日涨跌排行" if "rank" in charts_meta else "") + "）")
    order = {g: i for i, g in enumerate(GRADES)}
    n = 0
    for g in GRADES + sorted({r.get("grade") for r in ctx["rows"]} - set(GRADES), key=str):
        grp = [r for r in ctx["rows"] if r.get("grade") == g]
        if not grp:
            continue
        T.append(f"【{g}】{len(grp)} 只")
        for r in grp:
            n += 1
            head = f"{n}. {r.get('name')}（{code6(r.get('ts_code'))}）"
            bits = []
            if is_num(r.get("price")):
                bits.append(f"价格 {fmt_num(r['price'])}")
            if is_num(r.get("return_1d")) or is_num(r.get("return_5d")):
                bits.append("当日/近5日 " + " / ".join(fmt_pct_ratio(r.get(k)) or "—" for k in ("return_1d", "return_5d")))
            T.append(head + "：" + "；".join(bits + row_detail(r)) + "。")
    T.append("")
    cols = horizon_cols(ctx["rows"])
    if any(h for _, _, h in cols):
        sec += 1
        T.append(f"{'四五六七八九十'[sec - 4]}、多期限预测（图5；模型未校准 not_calibrated，仅供研究，不构成投资建议）")
        T.append("期限映射：" + "；".join(f"{lab}={keys[0]} 个交易日" if h else f"{lab}：{NA}" for lab, keys, h in cols)
                 + "。格式：预测涨幅（期望收益），上涨概率。")
        fa = fc_asof(ctx["rows"])
        if fa:
            T.append("预测 as_of：" + counter_text(fa))
        for i, r in enumerate(ordered_rows(ctx["rows"]), 1):
            parts = []
            for lab, keys, h in cols:
                f = fc_get(r, keys) if h else None
                parts.append(f"{lab} {fc_cell_text(f)}" if f else f"{lab} {NA}")
            T.append(f"{i}. {r.get('name')}（{code6(r.get('ts_code'))}）：" + "；".join(parts))
        T.append("")
    if any(lvl_zone(r.get("nearest_support"), r.get("support_zone")) or lvl_zone(r.get("nearest_resistance"), r.get("resistance_zone")) for r in ctx["rows"]):
        sec += 1
        T.append(f"{'四五六七八九十'[sec - 4]}、支撑与压力（图6）")
        if all(ee_same_as_nearest(r) for r in ctx["rows"]):
            T.append("说明：本次各标的 entry_exit_ref 进出参考区与最近支撑/压力区一致，合并列示。")
        for i, r in enumerate(ordered_rows(ctx["rows"]), 1):
            bits = []
            if is_num(r.get("price")):
                bits.append(f"现价 {fmt_num(r['price'])}")
            for lab, near, zone in (("支撑", r.get("nearest_support"), r.get("support_zone")),
                                    ("压力", r.get("nearest_resistance"), r.get("resistance_zone"))):
                z = zstr(lvl_zone(near, zone))
                if z:
                    t = f"{lab} {z}"
                    if isinstance(near, dict) and is_num(near.get("distance_pct")):
                        t += f"（距 {fmt_pct_already(near['distance_pct'])}）"
                    if isinstance(near, dict) and near.get("methods"):
                        t += f"［{'、'.join(near['methods'][:3])}］"
                    bits.append(t)
            if not ee_same_as_nearest(r):
                for lab, zone in (("进出参考支撑区", r.get("support_zone")), ("进出参考压力区", r.get("resistance_zone"))):
                    if isinstance(zone, dict) and is_num(zone.get("low")):
                        bits.append(f"{lab} {zstr((zone['low'], zone['high']))}")
            T.append(f"{i}. {r.get('name')}（{code6(r.get('ts_code'))}）：" + "；".join(bits))
        T.append("")
    ms = ctx.get("market_summary")
    sec += 1
    _labs = "一二三四五六七八九十"
    lab = _labs[sec - 1] if 1 <= sec <= 10 else str(sec)
    T.append(f"{lab}、全市场总结")
    T += format_market_summary_text(ms)
    T.append("")
    T.append("说明")
    T += [f"- {x}" for x in footer_lines(ctx)]
    T.append("")
    T.append("ETF Bot")
    return "\n".join(T) + "\n"


def footer_lines(ctx):
    L = ["本结果为研究用途（research only），actionable=false，模型与板块观察均未校准（not_calibrated），不构成投资建议。",
         "图表与表格中的数字均直接取自本机 live compute 输出；缺失字段已省略，未作推算或替代。",
         STRUCTURE_PROXY_DISCLAIMER]
    if ctx["slot"] == "收盘复核":
        L.append("收盘复核基于收盘后快照（非盘中实时报价），仅用于复盘与次日参考。")
    else:
        L.append(f"本邮件由 ETF Bot 在工作日 {ctx['slot']} 决策点例行发出。")
    return L


# ---------------------------------------------------------------- html body
FONT = "-apple-system,'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',Arial,sans-serif"


def chip(g):
    bg = GRADE_COLOR.get(g, OTHER_COLOR)
    fg = GRADE_TEXT_COLOR.get(g, "#ffffff")
    return (f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;background:{bg};color:{fg};'
            f'font-size:12px;font-weight:bold;white-space:nowrap;">{esc(g)}</span>')


def h2(t):
    return (f'<tr><td style="padding:22px 20px 8px 20px;font-family:{FONT};font-size:17px;font-weight:bold;'
            f'color:#1a1a1a;border-bottom:2px solid #1f5fa8;">{esc(t)}</td></tr>')


def para(inner, pad="10px 20px"):
    return f'<tr><td style="padding:{pad};font-family:{FONT};font-size:14px;line-height:1.7;color:#333;">{inner}</td></tr>'


def img(cid, alt, caption):
    return (f'<tr><td style="padding:10px 12px 2px 12px;" align="center"><img src="cid:{esc(cid)}" alt="{esc(alt)}" '
            f'width="576" style="display:block;width:100%;max-width:576px;height:auto;border:0;"></td></tr>'
            f'<tr><td style="padding:0 20px 8px 20px;font-family:{FONT};font-size:12px;color:#777;" align="center">{esc(caption)}</td></tr>')


def render_html(ctx, charts):
    slot, date = ctx["slot"], ctx["date"]
    H = []
    H.append('<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>{esc("ETF Bot " + slot_title(slot))}</title></head>'
             f'<body style="margin:0;padding:0;background:#eef1f5;">'
             '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eef1f5;"><tr><td align="center" style="padding:12px 6px;">'
             '<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;background:#ffffff;border-radius:6px;">')
    # header
    qt = ""
    if ctx["qtimes"]:
        a, b = ctx["qtimes"]
        qt = f"报价 {esc(a.replace('T', ' '))} 至 {esc(b.replace('T', ' ')[11:] if a[:10] == b[:10] else b)}（北京时间）"
    H.append(f'<tr><td style="background:#1f5fa8;padding:18px 20px;border-radius:6px 6px 0 0;font-family:{FONT};color:#fff;">'
             f'<div style="font-size:13px;opacity:0.85;">ETF Bot · 本机 live compute</div>'
             f'<div style="font-size:22px;font-weight:bold;margin-top:4px;">{esc(slot_title(slot))}</div>'
             f'<div style="font-size:14px;margin-top:4px;">{esc(date_label(date))}</div>'
             + (f'<div style="font-size:12px;margin-top:6px;opacity:0.9;">{qt}</div>' if qt else "")
             + '</td></tr>')
    # gate banner
    gates = ctx["gates"]
    if gates is None:
        gb, gbg, gfg = "本次渲染未附闸门结果", "#fff8e1", "#6d4c00"
    elif all(v["pass"] for v in gates.values()):
        gb, gbg, gfg = f"数据闸门 {'/'.join(gates)} 全部通过", "#e8f5e9", "#1b5e20"
    else:
        gb, gbg, gfg = "数据闸门存在失败项", "#ffebee", "#b71c1c"
    H.append(f'<tr><td style="padding:10px 20px;background:{gbg};font-family:{FONT};font-size:13px;color:{gfg};font-weight:bold;">{esc(gb)}</td></tr>')
    # summary cards
    c = ctx["counts"]
    cells = []
    for g in GRADES:
        cells.append(f'<td width="25%" align="center" style="padding:6px 3px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
                     f'<tr><td align="center" style="background:{GRADE_COLOR[g]};border-radius:6px;padding:10px 2px;font-family:{FONT};color:{GRADE_TEXT_COLOR[g]};">'
                     f'<div style="font-size:24px;font-weight:bold;line-height:1.1;">{c.get(g, 0)}</div>'
                     f'<div style="font-size:12px;margin-top:2px;">{esc(g)}</div></td></tr></table></td>')
    H.append(h2("一、摘要"))
    H.append('<tr><td style="padding:8px 17px 2px 17px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
             + "".join(cells) + '</tr></table></td></tr>')
    summ = [f"观察池合计 <b>{len(ctx['rows'])}</b> 只。"]
    extra = [g for g in c if g not in GRADES]
    if extra:
        summ.append("其他状态：" + "；".join(f"{esc(g)} {c[g]} 只" for g in extra) + "。")
    ch = ctx["changes"]
    if ch is not None:
        summ.append(f"相对 {esc(ch['label'])}：分级不变 <b>{ch['same']}</b> 只，变化 <b>{len(ch['all'])}</b> 只。")
    st = ctx["sector"]
    if st and st.get("add_themes"):
        summ.append("偏强观察主题：" + esc("、".join(st["add_themes"])) + "。")
    if st and st.get("reduce_themes"):
        summ.append("偏弱观察主题：" + esc("、".join(st["reduce_themes"])) + "。")
    H.append(para("<br>".join(summ)))
    # charts
    if charts:
        H.append(h2("二、图表"))
        for ch_ in charts:
            H.append(img(ch_["filename"], ch_["title"], ch_["caption"]))
    sec = ["三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"]
    si = 0
    # changes table
    if ch is not None and ch["all"]:
        H.append(h2(f"{sec[si]}、相对 {ch['label']} 的分级变化（{len(ch['all'])} 只）"))
        si += 1
        trs = []
        for i, x in enumerate(ch["all"]):
            bg = "#ffffff" if i % 2 == 0 else "#f7f9fb"
            pp = f'<div style="font-size:11px;color:#888;">{esc(fmt_num(x["prev_price"]))}</div>' if x["prev_price"] is not None else ""
            cp = f'<div style="font-size:11px;color:#888;">{esc(fmt_num(x["cur_price"]))}</div>' if is_num(x["cur_price"]) else ""
            trs.append(f'<tr style="background:{bg};"><td style="padding:7px 6px;font-family:{FONT};font-size:13px;color:#222;">'
                       f'<b>{esc(x["name"])}</b><div style="font-size:11px;color:#888;">{esc(code6(x["ts_code"]))}</div></td>'
                       f'<td align="center" style="padding:7px 4px;">{chip(x["prev"])}{pp}</td>'
                       f'<td align="center" style="padding:7px 0;font-family:{FONT};font-size:14px;color:#999;">→</td>'
                       f'<td align="center" style="padding:7px 4px;">{chip(x["cur"])}{cp}</td></tr>')
        H.append('<tr><td style="padding:6px 14px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e3e7ec;">'
                 f'<tr style="background:#eef2f7;"><td style="padding:6px;font-family:{FONT};font-size:12px;color:#555;">标的</td>'
                 f'<td align="center" style="padding:6px;font-family:{FONT};font-size:12px;color:#555;">{esc(ch["label"])}</td><td></td>'
                 f'<td align="center" style="padding:6px;font-family:{FONT};font-size:12px;color:#555;">{esc(slot_title(slot) if slot == "收盘复核" else slot)}</td></tr>'
                 + "".join(trs) + '</table></td></tr>')
    # sector themes
    if st and st.get("themes"):
        H.append(h2(f"{sec[si]}、板块观察（sector_timing，未校准）"))
        si += 1
        trs = []
        smax = max([abs(t["strength_score"]) for t in st["themes"] if is_num(t.get("strength_score"))] or [1]) or 1
        for t in st["themes"]:
            obs = t.get("observation") or ""
            col = UP_COLOR if "强" in obs else (DOWN_COLOR if "弱" in obs else FLAT_COLOR)
            bar = ""
            if is_num(t.get("strength_score")):
                w = min(100, max(2, int(round(abs(t["strength_score"]) / smax * 100))))
                bar = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
                       f'<td width="{w}%" style="background:{col};height:8px;font-size:0;line-height:0;">&nbsp;</td>'
                       f'<td style="font-size:0;line-height:0;">&nbsp;</td></tr></table>'
                       f'<div style="font-size:11px;color:#666;margin-top:2px;">强度 {esc(fmt_num(t["strength_score"], 2))}</div>')
            m5 = fmt_pct_ratio(t.get("mean_return_5d"))
            mem = t.get("member_count")
            sub = esc(f"成员 {mem}") if mem is not None else ""
            if m5:
                sub += ("，" if sub else "") + f'近5日均 <span style="color:{ret_color(t.get("mean_return_5d"))};">{esc(m5)}</span>'
            trs.append(f'<tr><td style="padding:6px;font-family:{FONT};font-size:13px;color:#222;white-space:nowrap;"><b>{esc(t.get("theme_l1"))}</b>'
                       f'<div style="font-size:11px;color:{col};">{esc(obs)}</div></td>'
                       f'<td style="padding:6px;font-family:{FONT};">{bar}</td>'
                       f'<td align="right" style="padding:6px;font-family:{FONT};font-size:11px;color:#666;">{sub}</td></tr>')
        H.append('<tr><td style="padding:6px 14px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e3e7ec;">'
                 + "".join(trs) + '</table></td></tr>')
    # ---- 以下三张逐标的表使用 cellpadding / bgcolor / <font> 精简标记，控制 HTML 体积（Gmail 102KB 截断）
    TBL = ('<tr><td style="padding:6px 14px;"><table role="presentation" width="100%" cellpadding="4" cellspacing="0" '
           'border="0" style="border:1px solid #e3e7ec;font-size:12px;">')
    TBL_END = '</table></td></tr>'

    def F(t, color=None, b=False, small=False):
        t = f"<b>{t}</b>" if b else t
        attrs = (f' color="{color}"' if color else "") + (' size="1"' if small else "")
        return f"<font{attrs}>{t}</font>" if attrs else t

    def name_cell(r, extra=""):
        gcol = "#5f6368" if r.get("grade") == "观望" else GRADE_COLOR.get(r.get("grade"), "#333")
        return f'<td>{F(esc(r.get("name")), gcol, True)}<br>{F(esc(code6(r.get("ts_code"))), "#999", small=True)}{extra}</td>'

    def zebra(i):
        return ' bgcolor="#f6f8fa"' if i % 2 else ""

    cols = horizon_cols(ctx["rows"])
    rs_all = ordered_rows(ctx["rows"])
    if any(h for _, _, h in cols):
        H.append(h2(f"{sec[si]}、多期限预测（未校准）"))
        si += 1
        fa = fc_asof(ctx["rows"])
        note = ("单元格为预测涨幅（期望收益，红正绿负）与上涨概率。期限：" + "；".join(f"{lab}={keys[0]} 个交易日" if h else f"{lab} {NA}" for lab, keys, h in cols)
                + "。" + (f"as_of {esc(counter_text(fa))}。" if fa else "")
                + "明日价格区间（q10–q90）见图6。模型未校准（not_calibrated），仅供研究，不构成投资建议。")
        H.append(para(F(note, "#666"), "4px 20px"))
        head = "".join(f'<td align="center"><b>{esc(lab)}</b>' + ("" if h else "<br>" + F(NA, "#888", small=True)) + "</td>" for lab, _, h in cols)
        trs = [f'<tr bgcolor="#eef2f7"><td><b>标的</b></td>{head}</tr>']
        for i, r in enumerate(rs_all):
            cells = []
            for lab, keys, h in cols:
                if not h:
                    if i == 0:
                        cells.append(f'<td rowspan="{len(rs_all)}" align="center" valign="top" bgcolor="#f1f1f1">{F(NA, "#888", small=True)}</td>')
                    continue
                f = fc_get(r, keys)
                if not f:
                    cells.append(f'<td align="center">{F(NA, "#888", small=True)}</td>')
                    continue
                v = f["expected_return"]
                pu = "<br>" + F(f"上涨概率 {f['p_up'] * 100:.0f}%", "#888", small=True) if is_num(f.get("p_up")) else ""
                cells.append(f'<td align="center">{F(esc(fmt_pct_ratio(v)), ret_color(v), True)}{pu}</td>')
            trs.append(f'<tr{zebra(i)}>{name_cell(r)}{"".join(cells)}</tr>')
        H.append(TBL + "".join(trs) + TBL_END)
    if any(lvl_zone(r.get("nearest_support"), r.get("support_zone")) or lvl_zone(r.get("nearest_resistance"), r.get("resistance_zone")) for r in ctx["rows"]):
        H.append(h2(f"{sec[si]}、支撑与压力"))
        si += 1
        same_all = all(ee_same_as_nearest(r) for r in ctx["rows"])
        H.append(para(F("最近支撑区（绿）与最近压力区（红），小字为距现价百分比与主要依据方法；"
                        + ("本次 entry_exit_ref 进出参考区与之一致，合并列示。" if same_all else "进出参考区与之不同时另列。"), "#666"), "4px 20px"))
        trs = [f'<tr bgcolor="#eef2f7"><td><b>标的</b></td><td align="right"><b>现价</b></td>'
               f'<td align="center">{F("支撑", DOWN_COLOR, True)}</td><td align="center">{F("压力", UP_COLOR, True)}</td></tr>']
        for i, r in enumerate(rs_all):
            def cell(near, zone, colr):
                z = zstr(lvl_zone(near, zone))
                if not z:
                    return f'<td align="center">{F(NA, "#888", small=True)}</td>'
                sub = []
                if isinstance(near, dict) and is_num(near.get("distance_pct")):
                    sub.append(fmt_pct_already(near["distance_pct"]))
                if isinstance(near, dict) and near.get("methods"):
                    sub.append("、".join(near["methods"][:2]))
                return f'<td align="center">{F(esc(z), colr)}' + ("<br>" + F(esc(" ".join(sub)), "#888", small=True) if sub else "") + "</td>"
            extra = ""
            if not same_all and not ee_same_as_nearest(r):
                bits = [f"{lab} {zstr((z['low'], z['high']))}" for lab, z in (("参考支撑", r.get("support_zone")), ("参考压力", r.get("resistance_zone")))
                        if isinstance(z, dict) and is_num(z.get("low"))]
                extra = "<br>" + F(esc("；".join(bits)), "#888", small=True)
            trs.append(f'<tr{zebra(i)}>{name_cell(r, extra)}<td align="right"><b>{esc(fmt_num(r.get("price")) or NA)}</b></td>'
                       + cell(r.get("nearest_support"), r.get("support_zone"), DOWN_COLOR)
                       + cell(r.get("nearest_resistance"), r.get("resistance_zone"), UP_COLOR) + '</tr>')
        H.append(TBL + "".join(trs) + TBL_END)
    # full table
    H.append(h2(f"{sec[si]}、逐标的决策点（{len(ctx['rows'])} 只）"))
    si += 1
    trs = []
    # column header for Phase A structure display
    trs.append('<tr bgcolor="#eef2f7"><td><b>标的</b></td><td align="right"><b>现价/涨跌</b></td>'
               '<td align="center"><b>威科夫</b></td><td align="center"><b>道氏</b></td>'
               '<td align="center"><b>ATR风险桶</b></td><td align="center"><b>结构影子</b></td><td><b>理由/信号</b></td></tr>')
    H.append(para(F(STRUCTURE_PROXY_DISCLAIMER, "#666"), "2px 20px"))
    for g in GRADES + sorted({r.get("grade") for r in ctx["rows"]} - set(GRADES), key=str):
        grp = [r for r in ctx["rows"] if r.get("grade") == g]
        if not grp:
            continue
        # Phase A: 威科夫 / 道氏 / ATR风险桶 display columns (structure_v1; missing → —)
        trs.append(f'<tr bgcolor="{GRADE_COLOR.get(g, OTHER_COLOR)}"><td colspan="7">{F(f"{esc(g)} · {len(grp)} 只", GRADE_TEXT_COLOR.get(g, "#fff"), True)}</td></tr>')
        for i, r in enumerate(grp):
            price = []
            if is_num(r.get("price")):
                price.append(F(esc(fmt_num(r["price"])), "#222", True))
            for lab, k in (("当日", "return_1d"), ("近5日", "return_5d")):
                p = fmt_pct_ratio(r.get(k))
                if p:
                    price.append(F(lab, "#666", small=True) + " " + F(esc(p), ret_color(r.get(k)), True))
            det = [esc(x) for x in row_detail(r) if not x.startswith("主题：")]
            theme = "/".join(x for x in (r.get("theme_l1"), r.get("theme_l2")) if x)
            wy = esc(structure_col(r, "wyckoff"))
            dw = esc(structure_col(r, "dow"))
            ab = esc(structure_col(r, "atr"))
            sh = esc(structure_shadow_col(r))
            trs.append(f'<tr{zebra(i)}><td valign="top"><b>{esc(r.get("name"))}</b><br>{F(esc(code6(r.get("ts_code")) + ("　" + theme if theme else "")), "#999", small=True)}</td>'
                       f'<td valign="top" align="right" nowrap>{"<br>".join(price)}</td>'
                       f'<td valign="top" align="center" nowrap>{F(wy, "#444")}</td>'
                       f'<td valign="top" align="center" nowrap>{F(dw, "#444")}</td>'
                       f'<td valign="top" align="center" nowrap>{F(ab, "#444")}</td>'
                       f'<td valign="top" align="center" nowrap>{F(sh, "#444")}</td>'
                       f'<td valign="top">{F("<br>".join(det), "#666", small=True)}</td></tr>')
    H.append(TBL + "".join(trs) + TBL_END)
    # data sources + gates
    H.append(h2(f"{sec[si]}、数据来源、时间戳与闸门"))
    lines = [esc(x) for x in meta_lines(ctx)]
    gl = gate_lines(gates)
    if gl is None:
        lines.append("闸门：本次渲染未附闸门结果。")
    else:
        lines += [("✔ " if gates[k]["pass"] else "✘ ") + esc(x) for k, x in zip(gates, gl)]
    H.append(para('<div style="font-size:12px;line-height:1.7;color:#555;word-break:break-all;">' + "<br>".join(lines) + "</div>"))
    # 全市场总结（文末，说明之前）
    lab = sec[si] if si < len(sec) else "附"
    H.append(h2(f"{lab}、全市场总结"))
    H.append(format_market_summary_html(ctx.get("market_summary"), esc, para, h2, FONT))
    # footer
    H.append(f'<tr><td style="padding:14px 20px 18px 20px;background:#f5f6f8;border-radius:0 0 6px 6px;font-family:{FONT};font-size:12px;line-height:1.7;color:#666;">'
             + "<br>".join(esc(x) for x in footer_lines(ctx)) + '<br><b>ETF Bot</b></td></tr>')
    H.append('</table></td></tr></table></body></html>')
    return compact_html("".join(H))


def compact_html(h):
    """为避免 Gmail 在 102KB 处截断：去掉逐格重复的 font-family，改由外层表格统一继承。"""
    h = h.replace(f"font-family:{FONT};", "")
    h = h.replace('<table role="presentation"', f'<table role="presentation" style="font-family:{FONT};"', 1)
    h = h.replace('<body style="', f'<body style="font-family:{FONT};', 1)
    h = h.replace('<table role="presentation" style="font-family:' + FONT + ';" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eef1f5;">',
                  '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eef1f5;font-family:' + FONT + ';">', 1)
    return h


# ---------------------------------------------------------------- not ready
def render_not_ready(slot, date, gates, reason):
    subject = f"【ETF Bot】{slot} 数据未就绪（{date_label(date)}）"
    T = [subject, "", "本时段不提供带分级、方向或买卖点的策略内容，亦不使用公开行情降级替代。", ""]
    gl = gate_lines(gates) or []
    if gl:
        T.append("闸门结果：")
        T += [f"- {x}" for x in gl]
        T.append("")
    if reason:
        T += ["说明：" + reason, ""]
    T += ["本通知由 ETF Bot 在工作日 " + slot + " 决策点例行发出。", "", "ETF Bot"]
    items = []
    for k, x in zip(gates or {}, gl):
        ok = gates[k]["pass"]
        items.append(f'<tr><td style="padding:5px 8px;font-family:{FONT};font-size:13px;color:{"#1b5e20" if ok else "#b71c1c"};'
                     f'{"" if ok else "font-weight:bold;"}border-bottom:1px solid #eee;">{"✔" if ok else "✘"} {esc(x)}</td></tr>')
    H = ('<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>'
         '<body style="margin:0;padding:0;background:#eef1f5;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eef1f5;"><tr><td align="center" style="padding:12px 6px;">'
         '<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;background:#fff;border-radius:6px;">'
         f'<tr><td style="background:#b26a00;padding:18px 20px;border-radius:6px 6px 0 0;font-family:{FONT};color:#fff;">'
         f'<div style="font-size:13px;opacity:0.85;">ETF Bot</div><div style="font-size:22px;font-weight:bold;margin-top:4px;">{esc(slot)} 数据未就绪</div>'
         f'<div style="font-size:14px;margin-top:4px;">{esc(date_label(date))}</div></td></tr>'
         + para("本时段不提供带分级、方向或买卖点的策略内容，亦不使用公开行情降级替代。", "16px 20px 8px 20px")
         + (f'<tr><td style="padding:4px 14px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #f0d9b5;background:#fffaf2;">{"".join(items)}</table></td></tr>' if items else "")
         + (para("说明：" + esc(reason)) if reason else "")
         + f'<tr><td style="padding:14px 20px 18px 20px;background:#f5f6f8;border-radius:0 0 6px 6px;font-family:{FONT};font-size:12px;color:#666;">'
         f'本通知由 ETF Bot 在工作日 {esc(slot)} 决策点例行发出。<br><b>ETF Bot</b></td></tr></table></td></tr></table></body></html>')
    return subject, "\n".join(T) + "\n", H


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="ETF Bot 图文版策略邮件渲染（不发送）")
    ap.add_argument("--input", help="bundle_*.json 或 extract_slim.py 输出的精简 JSON")
    ap.add_argument("--slot", required=True, help="11:40 / 14:30 / 14:45 / 收盘复核")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD（北京时间交易日）")
    ap.add_argument("--prev", help="上一时段的 bundle / 精简 JSON / {ts_code: grade} 映射（可选）")
    ap.add_argument("--prev-label", default=None, help="上一时段名称，如 14:30")
    ap.add_argument("--gates", help="闸门结果 JSON：{G1: true|{pass,note}, ...} 或 {gates:{...}}")
    ap.add_argument("--bundle-id", default=None)
    ap.add_argument("--bundle-name", default=None, help="展示用 bundle 文件名")
    ap.add_argument("--not-ready", action="store_true", help="强制输出『数据未就绪』版本")
    ap.add_argument("--reason", default=None, help="数据未就绪版本的补充说明")
    ap.add_argument("--allow-missing-gates", action="store_true", help="仅测试：策略时段缺闸门也渲染")
    ap.add_argument("--no-rank-chart", action="store_true")
    ap.add_argument("--recheck-g4", action="store_true",
                    help="14:30/14:45：渲染时按当前时间复核报价 ≤10 分钟，超时则改出『数据未就绪』")
    ap.add_argument("--g4-max-age-min", type=float, default=10.0)
    ap.add_argument("--out", default=None, help="body/manifest 输出目录")
    ap.add_argument("--attach-dir", default=DEFAULT_ATTACH_DIR)
    ap.add_argument("--market-summary", default=None,
                    help="jovi_gate_extract 产出的 market_summary.json；缺省则仅用跟踪池字段拼装")
    a = ap.parse_args()

    tag = SLOT_TAG.get(a.slot, a.slot.replace(":", ""))
    stamp = a.date.replace("-", "")
    out = Path(a.out or HERE / "out" / f"{stamp}_{tag}")
    out.mkdir(parents=True, exist_ok=True)
    attach = Path(a.attach_dir)
    attach.mkdir(parents=True, exist_ok=True)
    gates = load_gates(a.gates)

    if a.recheck_g4 and a.input and gates is not None and a.slot in ("14:30", "14:45") \
            and gates.get("G4", {}).get("pass"):
        qts = [r.get("quote_source_time") for r in load_data(a.input)["rows"] if r.get("quote_source_time")]
        if qts:
            oldest = min(dt.datetime.fromisoformat(to_cst(q)) for q in qts)
            age = (dt.datetime.now(CST).replace(tzinfo=None) - oldest).total_seconds() / 60
            if age > a.g4_max_age_min:
                gates["G4"] = {"pass": False, "note": f"渲染时（{dt.datetime.now(CST):%H:%M:%S} 北京时间）最旧报价"
                               f" {oldest:%H:%M:%S} 已过 {age:.1f} 分钟，超过 {a.g4_max_age_min:g} 分钟闸门"}
    failed = gates is not None and not all(v["pass"] for v in gates.values())
    if a.slot in STRATEGY_SLOTS and gates is None and not a.not_ready and not a.allow_missing_gates:
        raise SystemExit("策略时段必须提供 --gates（或 --not-ready）；测试请加 --allow-missing-gates")
    if a.not_ready or failed or not a.input:
        subject, txt, htm = render_not_ready(a.slot, a.date, gates, a.reason)
        (out / "body.txt").write_text(txt, encoding="utf-8")
        (out / "body.html").write_text(htm, encoding="utf-8")
        man = {"variant": "not_ready", "subject": subject, "slot": a.slot, "date": a.date,
               "body_txt": str(out / "body.txt"), "body_html": str(out / "body.html"), "attachments": [],
               "gates": gates}
        (out / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(man, ensure_ascii=False, indent=2))
        return

    data = load_data(a.input)
    if not data["rows"]:
        raise SystemExit("输入中没有 rows")
    prev = load_prev(a.prev) if a.prev else None
    prev_label = a.prev_label or ("上一时段" if prev else None)
    bundle_name = a.bundle_name or (Path(a.input).name if Path(a.input).name.startswith("bundle_") else None)
    ms = None
    if a.market_summary and Path(a.market_summary).exists():
        with open(a.market_summary, encoding="utf-8") as f:
            ms = json.load(f)
    elif data.get("market_summary"):
        ms = data["market_summary"]
    else:
        ms = build_market_summary(
            slot=a.slot, date=a.date, checked_at=None,
            rows=data["rows"], rc=None, fetch_indices=False,
        )
        ms["indices_note"] = "本次渲染未附 Jovi market_summary；指数与全市场宽度未取数，仅列跟踪池"
    ctx = build_context(data, a.slot, a.date, prev, prev_label, gates, bundle_name, a.bundle_id, market_summary=ms)

    plt = setup_matplotlib()
    charts = []
    title_tail = f"{a.date} {slot_title(a.slot)}"
    with GlyphGuard():
        fn = f"etf_{stamp}_{tag}_1_grade_dist.png"
        chart_grade_dist(plt, ctx["counts"], f"分级分布 · {title_tail}", attach / fn)
        charts.append({"key": "dist", "filename": fn, "title": "分级分布", "caption": "图1 分级分布（标的数与占比）"})
        fn = f"etf_{stamp}_{tag}_2_grade_tiles.png"
        chart_grade_tiles(plt, ctx["rows"], f"逐标的分级总览 · {title_tail}", attach / fn)
        has_r1 = any(is_num(r.get("return_1d")) for r in ctx["rows"])
        charts.append({"key": "tiles", "filename": fn, "title": "逐标的分级总览",
                       "caption": "图2 逐标的分级总览（颜色=分级" + ("，数字=当日涨跌幅" if has_r1 else "") + "）"})
        if ctx["changes"] is not None:
            fn = f"etf_{stamp}_{tag}_3_vs_prev.png"
            chart_transition(plt, ctx["changes"], ctx["changes"]["prev_counts"], ctx["counts"], prev_label,
                             "收盘" if a.slot == "收盘复核" else a.slot,
                             f"分级迁移矩阵 · {prev_label} → {'收盘' if a.slot == '收盘复核' else a.slot}", attach / fn)
            charts.append({"key": "change", "filename": fn, "title": "分级迁移",
                           "caption": f"图3 相对 {prev_label} 的分级迁移（行=前、列=后，括号内为各档合计）"})
        if has_r1 and not a.no_rank_chart:
            fn = f"etf_{stamp}_{tag}_4_return_rank.png"
            chart_return_rank(plt, ctx["rows"], f"当日涨跌幅排行 · {title_tail}", attach / fn)
            charts.append({"key": "rank", "filename": fn, "title": "当日涨跌幅排行",
                           "caption": "图4 当日涨跌幅排行（颜色=分级；口径见文末数据说明）"})
        con = (ctx.get("market_summary") or {}).get("concepts")
        if con and (con.get("strongest") or con.get("weakest") or any(not x.get("missing") for x in (con.get("pinned") or []))):
            try:
                fn = f"etf_{stamp}_{tag}_7_concept_board.png"
                chart_concept_board(plt, con, f"概念强弱榜 · {title_tail}", attach / fn)
                charts.append({"key": "concept", "filename": fn, "title": "概念强弱榜",
                               "caption": "图7 概念强弱榜（★钉住 CPO概念；红涨绿跌）"})
            except Exception as exc:
                print(f"跳过概念榜图: {type(exc).__name__}: {exc}", file=sys.stderr)
        cols = horizon_cols(ctx["rows"])
        if any(h for _, _, h in cols):
            fn = f"etf_{stamp}_{tag}_5_forecast_horizons.png"
            chart_forecast_heat(plt, ctx["rows"], cols, f"多期限预测（未校准）· {title_tail}", attach / fn)
            charts.append({"key": "fc", "filename": fn, "title": "多期限预测",
                           "caption": "图5 多期限预测（明日/3日/7日/一个月/3个月）：预测涨幅（红正绿负）与上涨概率；" + "、".join(lab for lab, _, h in cols if not h) + ("：" + NA if any(not h for _, _, h in cols) else "")})
        if any(lvl_zone(r.get("nearest_support"), r.get("support_zone")) for r in ctx["rows"]):
            fn = f"etf_{stamp}_{tag}_6_support_resistance.png"
            chart_sr_range(plt, ctx["rows"], f"支撑/压力区间 · {title_tail}", attach / fn)
            charts.append({"key": "sr", "filename": fn, "title": "支撑压力",
                           "caption": "图6 现价（黑点）与最近支撑区（绿）、压力区（红），灰条为明日预测 q10–q90（未校准）"})
    keys = {c["key"] for c in charts}
    txt = render_text(ctx, keys)
    htm = render_html(ctx, charts)
    subject = f"【ETF Bot】{slot_title(a.slot)}（{date_label(a.date)}）"
    (out / "body.txt").write_text(txt, encoding="utf-8")
    (out / "body.html").write_text(htm, encoding="utf-8")
    if len(htm.encode("utf-8")) > 95 * 1024:
        print(f"警告：body.html {len(htm.encode('utf-8'))} 字节，接近 Gmail 102KB 截断阈值", file=sys.stderr)
    att = [{"path": str(attach / c["filename"]), "cid": c["filename"], "bytes": os.path.getsize(attach / c["filename"])}
           for c in charts]
    man = {"variant": "strategy", "subject": subject, "slot": a.slot, "date": a.date,
           "body_txt": str(out / "body.txt"), "body_html": str(out / "body.html"),
           "attachments": att, "attachments_total_bytes": sum(x["bytes"] for x in att),
           "gates": gates, "grade_counts": dict(ctx["counts"]), "rows": len(ctx["rows"]),
           "input": str(Path(a.input).resolve()), "prev": str(Path(a.prev).resolve()) if a.prev else None,
           "send_hint": "SendEmail(from=jovi-bot@mail.grokbot.com, subject, body=body.txt, html_body=body.html, attachments=[...path])"}
    (out / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(man, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

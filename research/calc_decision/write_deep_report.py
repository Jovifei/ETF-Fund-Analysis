# -*- coding: utf-8 -*-
from pathlib import Path
import json
import pandas as pd

ROOT = Path(r"E:\worktrees\etf-calc-decision-20261024")
OUT = ROOT / "research" / "calc_decision" / "out"
metrics = pd.read_csv(ROOT / "docs" / "factor_empirical_metrics_20261024.csv")
rank = pd.read_csv(OUT / "holdout_factor_rank_20261024.csv")
cov = json.loads((OUT / "data_inventory_20261024.json").read_text(encoding="utf-8"))
meta = pd.read_csv(OUT / "data_coverage_by_etf.csv")

def fmt(x, pct=False):
    if pd.isna(x):
        return "n/a"
    return f"{x*100:.1f}%" if pct else f"{x:.4f}"

def table_for(sample, horizons=(1, 7, 20)):
    rows = []
    sub = metrics[metrics["sample"] == sample]
    for fac in rank["factor"]:
        r = {"factor": fac}
        for h in horizons:
            g = sub[(sub.factor == fac) & (sub.horizon == h)]
            if len(g) == 0:
                continue
            g = g.iloc[0]
            r[f"hit_h{h}"] = g.hit_rate
            r[f"ic_h{h}"] = g.ic_spearman
            r["sh"] = g.sharpe_longflat_d1
            r[f"n_h{h}"] = int(g.n_signals)
        rows.append(r)
    return pd.DataFrame(rows)

hold = table_for("holdout_2y_longhist")
allh = table_for("all_longhist")

md = []
md.append("# 决策因子加深实证报告（本机篮子）")
md.append("")
md.append("日期：2026-10-24（Asia/Shanghai）  ")
md.append("分支：`codex/calc-decision-factors-20261024`  ")
md.append("脚本：`research/calc_decision/run_empirical_factors.py`  ")
md.append("主库：`F:\\ETF_Data\\ETF-Fund-Analysis\\db\\research.sqlite3`（只读）")
md.append("")
md.append("> **诚实声明**：以下数字来自本机日线回放，未扣费、未做 purged CV、未做多重检验校正。胜率接近 50% 是常态；动量类常靠盈亏比而非命中率。`adjust=none`，拆分前价格可能有跳点。不构成投资建议；策略邮件仍应保持 `actionable=false` 直至独立校准通过。")
md.append("")
md.append("## 1. 数据盘点")
md.append("")
md.append("| 项 | 值 |")
md.append("|---|---|")
md.append(f"| DB | `{cov['db_path']}` |")
md.append(f"| 日线条数 | {cov['bars_n']} |")
md.append(f"| 日期覆盖 | {cov['date_min']} → {cov['date_max']} |")
md.append(f"| Watchlist enabled | {cov['watchlist_n']} |")
md.append(f"| 长历史面板（≥400 bars） | {cov['long_history_n']} 只 |")
md.append(f"| 主源 | {cov['sources']} |")
md.append(f"| 复权标记 | {cov['adjust']} |")
md.append(f"| Holdout 起点 | {cov['holdout_start']}（最近 2 年） |")
md.append(f"| 单边成本假设（评论用） | {cov['cost_assumption_bps_one_way']} bps |")
md.append("| `etf_share_scales` | **0 行** → 跳过 share_chg |")
md.append("| quote 中 premium/iopv/shares | **全空** → 跳过 premium_iopv 历史实证 |")
md.append("| 原生美股 ETF（SPY/QQQ 等） | **本地无**；仅有中概跨境 `513100`/`513500`（后者仅 ~278 日） |")
md.append("")
md.append("### 1.1 长历史 17 只（主实证面板）")
md.append("")
long = meta[meta.n >= 400].sort_values("n", ascending=False)
md.append("| ts_code | name | n | start | end |")
md.append("|---|---|---:|---|---|")
for _, r in long.iterrows():
    md.append(f"| {r.ts_code} | {r['name']} | {int(r.n)} | {str(r.start)[:10]} | {str(r.end)[:10]} |")
md.append("")
md.append("其余 enabled 标的多数从 **2025-08-18** 才有约 278 根日线，只进 `recent_all_enabled` 稳健性切片，不进主 holdout 排名。")
md.append("")
md.append("### 1.2 美股侧缺口")
md.append("")
md.append("- 本地无 SPY/QQQ/IWM/XL* 日线，**不能**在本机做原生美股 ETF 面板实证。")
md.append("- 篮子内 `513100.SH`（纳指100ETF）有 2017-03→2026-10 长历史，可作「美股敞口的 A 股上市代理」；`513500.SH` 历史过短。")
md.append("- 美股文献结论（动量、ETF 份额流、折溢价）见第 5 节；落地需另接美股数据源后再跑同一脚本。")
md.append("")
md.append("## 2. 方法")
md.append("")
md.append("- **收益**：优先用库内 `pct_change`，否则 `close/pre_close-1`。")
md.append("- **远期窗口**：1 / 3 / 7 / 20 / 60 个交易日（对齐产品五期限中的短中窗；「一个月/三个月」近似 20/60）。")
md.append("- **样本**：`train_earlier` vs `holdout_2y`；另报 `all_longhist` 与 `recent_all_enabled`。")
md.append("- **截面动量**：日频，当日因子值上下三分位；多头命中=远期收益>0；IC=当日截面 Spearman。")
md.append("- **时序信号**：信号非 0 时，符号与远期收益同向计命中；多头/空头各自平均远期收益。")
md.append("- **Sharpe**：多头-空仓、等权、用次日 `ret_1` 估算年化（未扣费）；同一因子各 horizon 共用该日频 Sharpe。")
md.append("- **未做**：滑点/印花税/冲击、涨跌停可成交过滤、purged/embargo CV、Harvey 式多重检验、实盘 T+1 约束精细化。")
md.append("")
md.append("## 3. Holdout（近 2 年）主结果")
md.append("")
md.append("排序按合成分：`0.4*IC_7 + 0.3*IC_20 + 0.2*(hit_7-0.5) + 0.1*(Sharpe/2)`，并标注 train↔holdout 的 IC_7 是否翻号。")
md.append("")
md.append("| 排名 | 因子 | score | hold IC_7 | train IC_7 | 翻号? | hold hit_7 | Sharpe≈ |")
md.append("|---:|---|---:|---:|---:|:---:|---:|---:|")
for i, r in enumerate(rank.itertuples(), 1):
    flip = "Y" if r.sign_flip else "N"
    md.append(
        f"| {i} | `{r.factor}` | {r.score:.4f} | {r.hold_ic7:.4f} | {r.train_ic7:.4f} | {flip} | {r.hold_hit7:.1%} | {r.hold_sh:.3f} |"
    )
md.append("")
md.append("### 3.1 Holdout 明细（hit / IC）")
md.append("")
md.append("| 因子 | hit_1 | IC_1 | hit_7 | IC_7 | hit_20 | IC_20 | Sharpe |")
md.append("|---|---:|---:|---:|---:|---:|---:|---:|")
for _, r in hold.iterrows():
    md.append(
        f"| `{r.factor}` | {fmt(r.hit_h1, True)} | {fmt(r.ic_h1)} | {fmt(r.hit_h7, True)} | {fmt(r.ic_h7)} | {fmt(r.hit_h20, True)} | {fmt(r.ic_h20)} | {fmt(r.sh)} |"
    )
md.append("")
md.append("### 3.2 全样本长历史（对照，易乐观）")
md.append("")
md.append("| 因子 | hit_7 | IC_7 | hit_20 | IC_20 | Sharpe |")
md.append("|---|---:|---:|---:|---:|---:|")
for _, r in allh.iterrows():
    md.append(
        f"| `{r.factor}` | {fmt(r.hit_h7, True)} | {fmt(r.ic_h7)} | {fmt(r.hit_h20, True)} | {fmt(r.ic_h20)} | {fmt(r.sh)} |"
    )
md.append("")
md.append("## 4. 解读（针对本篮子）")
md.append("")
md.append("### 相对更站得住（holdout 未翻号 + IC 为正）")
md.append("")
md.append("1. **`tsmom_volscaled` / `tsmom_12m`**：holdout IC_7≈0.10 / 0.06，hit_7≈53.0%；IC_20 仍为正。波动缩放略抬 IC。适合做「趋势 regime / 仓位缩放」而不是高频买卖点。")
md.append("2. **`mom_120_cs`**：截面中期动量 holdout IC_7/20 均为正且未翻号；在本 17 只长历史上 **120 日截面** 比 20 日更稳。")
md.append("3. **`ichimoku_cloud`**：IC 很弱但符号稳定，Sharpe 尚可；更像过滤器。")
md.append("4. **`macd`**：holdout 短窗（h7）IC 尚可，但 **h20 翻负**；只能当短窗辅助，不能单独驱动「一个月」档。")
md.append("")
md.append("### 看起来香、但 holdout 翻号或不稳")
md.append("")
md.append("- **`mom_20_cs` / `turtle_20_10` / `rs_vs_300_20`**：短窗 holdout 不错，但相对训练集 IC 翻号或 h20 大幅转负 → 易过拟合轮动节奏。")
md.append("- **`dual_ma` / `adx_trend` / `atr_gate_dual_ma`**：holdout 中期 IC 转负；ADX 门控未救均线。")
md.append("- **`z_mr_20`**：整体偏负；仅在部分 h20 切片偶发为正，**不能**当主信号。")
md.append("- **`td9_setup`**：事件稀疏（holdout h1 仅 ~239 次），h1 命中可到 ~56%，但 h3/h7 迅速掉到 <50%；九转更像噪音脉冲。")
md.append("")
md.append("### 成本直觉")
md.append("")
md.append("若单边 10bps、双边 20bps：日频换手的截面动量/海龟，毛 Sharpe 0.5–0.9 很容易被吃光。更现实的是 **周频或事件触发** 重估，而不是每日满仓轮动。")
md.append("")
md.append("## 5. 文献加深（附录，不删旧 caveat）")
md.append("")
md.append("### A 股 / 中国 ETF")
md.append("")
md.append("- 华宝证券（2024-12）：300+ ETF 跟踪指数，**短窗动量（约 15–25 日）**更强；IC>0 占比仅略高于 50%，盈利靠盈亏比；高换手。")
md.append("- Ma / Liao / Jiang（2022）：中国 **因子动量** 显著（TSFM/CSFM），即便个股动量弱。")
md.append("- Cui & Li（2024, Pacific-Basin）：中国动量形成偏 **7–12 月**；因子动量可进四因子。")
md.append("- 北向资金：指数层对未来 2/5/10/20 日超额有预测力（Jorms 2024）；个股周度持股变化多空约 61bps/周（APJFS）；2024 全年北向净流出，行业有效性可能时变。")
md.append("- 日历：A 股 **农历正月效应**强于公历一月（AJFS 2022）；中国上市 ETF 样本上公历一月效应不稳。")
md.append("")
md.append("### 美股 ETF（文献；本地无原生面板）")
md.append("")
md.append("- Asness / Moskowitz / Pedersen：跨资产价值+动量仍是基准叙事。")
md.append("- ETF 份额流 / 套利：创建赎回可预测短期收益（部分为压力后反转）；溢价后常伴次日价格回吐（Fulkerson & Jordan 等）。")
md.append("- 对本项目：美股基金买卖应优先接 **US OHLCV + shares outstanding + premium**，再复用本脚本；在只有 `513100` 代理时，只把美股因子当「主题敞口动量」弱证据。")
md.append("")
md.append("## 6. 部署进现有五期限 + 分档（计算分支建议）")
md.append("")
md.append("| 优先级 | 特征 | 接到哪里 | 用法 |")
md.append("|---:|---|---|---|")
md.append("| P0 | `tsmom_12m` + `vol_20` 缩放 | 仓位/regime | 年化波动目标；不直接当「明日买卖点」 |")
md.append("| P0 | `mom_120` 截面秩 | 3日/7日/一个月排序 | 篮内相对强弱；输出分位而非裸信号 |")
md.append("| P1 | `mom_20` 截面秩 | 明日/3日 | 仅当与 P0 同向或趋势确认 |")
md.append("| P1 | `rs_vs_300_20` | 门控 | 弱于基准则降低「可入场」 |")
md.append("| P2 | `ichimoku` / `turtle` | 过滤器 | 云上/突破只加分，不单独触发减仓 |")
md.append("| P2 | `macd` hist | 短窗辅助 | 禁止单独驱动 20/60 日档 |")
md.append("| 观察 | `td9` | 事件标记 | 只作文案/研究标签 |")
md.append("| 暂缓 | `z_mr`、裸 `dual_ma` | — | holdout 不支持主信号 |")
md.append("| 缺数 | `share_chg` / `premium_iopv` / 北向行业聚合 | — | 先把 `etf_share_scales` 与北向行业流水接进库 |")
md.append("")
md.append("映射到现有四档（可入场/可试探/观望/减仓）建议：")
md.append("")
md.append("1. 先算 **regime**（TSMOM 符号 + 云/趋势位置）。")
md.append("2. 再算 **截面分数**（mom_120 为主，mom_20 为辅）。")
md.append("3. 五期限预测仍用现有收益模型；本因子层只提供 **排序与门控**，校准前继续 `actionable=false`。")
md.append("4. 上线门：walk-forward + purged CV + 扣费后 ICIR；周六例程继续扫新因子，但 **必须用本脚本同口径复测** 才可进候选。")
md.append("")
md.append("## 7. 产物路径")
md.append("")
md.append("- `docs/decision_factors_deep_empirical_20261024.md`（本文件）")
md.append("- `docs/factor_empirical_metrics_20261024.csv`")
md.append("- `research/calc_decision/out/data_coverage_by_etf.csv`")
md.append("- `research/calc_decision/out/holdout_factor_rank_20261024.csv`")
md.append("- `research/calc_decision/out/data_inventory_20261024.json`")
md.append("- `research/calc_decision/run_empirical_factors.py`")
md.append("")
md.append("未触碰 live task SHA / 服务器 / 策略邮件发送。")
md.append("")

text = "\n".join(md)
path1 = ROOT / "docs" / "decision_factors_deep_empirical_20261024.md"
path1.write_text(text, encoding="utf-8")
print("wrote", path1, "chars", len(text))

cat = ROOT / "docs" / "decision_factors_catalog_20261024.md"
append = """

---

## Appendix B — Literature deepen (2026-10-24 empirical pass)

Previous honesty caveats in this catalog still apply (factor zoo / multiple testing / win-rate ≠ edge).

### Added China / A-share ETF sources
- 华宝证券《ETF策略：短期、中期还是长期动量效应有效？》(2024-12)：短窗 15–25 日更强；IC>0 仅略高于 50%。
- Ma, Liao, Jiang (2022), Factor Momentum in the Chinese Stock Market：TSFM/CSFM 显著。
- Cui & Li (2024), Pacific-Basin Finance Journal：中国动量形成 7–12 月；因子动量四因子。
- Northbound predictability: Jorms 2024 (2/5/10/20D index); APJFS weekly holdings HPC ~61bps/week L-S; 2024 net outflow year → regime risk.
- Lunar January effect in A-shares (AJFS 2022); solar January weak/absent for China ETFs in some samples.

### Added US ETF sources (no local native panel this pass)
- ETF flows / creation-redemption return predictability and reversals (Staer; Brown/Davies/Ringgenberg RoF line of work).
- Premium/discount short-horizon predictability (Fulkerson & Jordan; Rompotis iShares).
- Value & Momentum Everywhere remains the cross-asset baseline (Asness, Moskowitz, Pedersen).

### Local empirical override
See `docs/decision_factors_deep_empirical_20261024.md` for **measured** hit/IC/Sharpe on this watchlist’s long-history 17 ETFs. Literature win-rates are not substitutes for that table.
"""
with cat.open("a", encoding="utf-8") as f:
    f.write(append)
print("appended catalog")

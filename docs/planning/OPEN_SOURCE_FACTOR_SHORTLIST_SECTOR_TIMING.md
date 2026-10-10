# 开源启发因子短名单（sector-timing 下一阶段，研究向）

> 状态：选型笔记 · **不进生产五档** · **不 vendor 整仓** · 保持 \ctionable=false\ / ot_calibrated
## 已有工程内能力（优先复用）

| 能力 | 位置 | 说明 |
|---|---|---|
| 主题内 5 日相对强弱 | \decision_reference.theme_relative_ranks\ | 已用；本观察层已读 eturn_5d\ |
| 信号中心板块强度 | \signal_center_service._sectors\ | 动量/宽度/新闻聚合，研究视图 |
| Alphalens 风格 IC | \actor_analysis_service\ | 已有；继续删无增量因子 |
| OSS 研究因子清单 | \OSS_RESEARCH_FACTORS\（若存在） | 只借鉴定义 |

## 候选（借鉴思想，不拷贝巨型仓库）

| 来源 | 可借鉴点 | 接入建议 | 风险 |
|---|---|---|---|
| zhangsensen/etf-rotation-strategy | 排名迟滞、最短持有、波动/回撤门控 | 下一阶段把“波动门控”做成观察字段（如 20d 波动分位），**不**自动改档 | 参数一变必须 walk-forward |
| Healermm/AlphaLab | 因子→申万行业→行业 ETF 映射 | 与现有 taxonomy / board catalog 对齐；可作映射质量对账 | 行业映射非 PIT |
| yansongwel/etf-quant | 板块轮动时钟（强弱切换） | 仅作状态标签（升温/降温），挂到 \sector_timing.themes[].research_tags\ | 易被误读为交易信号 |
| stefan-jansen/alphalens-reloaded | IC / RankIC / 分位收益 | 继续用现有 effectiveness 报告筛因子 | 不 pip 进生产路径 |
| Microsoft Qlib | 因子定义启发 | **禁止 vendor**；只抄公式进研究清单 | 过重、许可与运维成本 |
| Nixtla/mlforecast + MAPIE | 全局时序 + conformal 区间 | S8 校准阶段隔离研究 | 通过前保持 not_calibrated |

## 下一阶段试点顺序（建议）

1. **动量 RS（已部分具备）**：主题内 eturn_5d/20d\ 密度 → 已在观察层；补 20d 与波动分位旁注。
2. **波动门控**：高波动主题降权显示（仍非改档）。
3. **行业→ETF 映射对账**：SectorSnapshot / taxonomy / board catalog 三者一致率报告。
4. **IC 短名单**：对 \ma_gap_*\、\oss\、份额/资金流研究字段跑 ICIR；稳定者进研究特征清单，**不进五档**。

## 明确不做

- 不把轮动策略参数直接写成生产加减仓指令。
- 不引入 vn.py / rqalpha / backtrader 作为主路径。
- 不在未校准前展示“可操作涨跌幅预测”。

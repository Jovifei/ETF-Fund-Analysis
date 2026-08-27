# GitHub Research Notes

v0.5.0 继续遵循“优先借鉴成熟开源工程、确定性计算与 AI 分离、所有新增因子必须回测验证”的原则。

## 本轮重点参考

### wukan1986/ta_cn — MIT

固定参考提交：`a569a618109daa804541c5d67fa4c0407f03fd49`。

值得借鉴：
- 中国化技术指标组织方式；
- `chip.py` 的成交/换手在价格网格上分配、WINNER/COST 的研究思想。

本项目没有把股票真实筹码模型直接套到 ETF/LOF，而是实现 `volume_profile_approx`：近 120 日成交量按价格区间与时间衰减形成成交密集峰、成本分位和近似获利盘，并显式标注 estimated。

### bukosabino/ta — MIT

固定参考提交：`a890410710a6e483c9ba08da7f3dd5089e4b9dff`。

用于核对标准技术指标公式与测试组织，包括：OBV、MFI、CMF、ADX/DMI、CCI、Williams %R 等。本项目使用 Pandas/NumPy 重新实现，不引入运行时依赖。

### Travisun/Opptrix — Apache-2.0

固定参考提交：`9f8878415566e42f1bfd4b2f497423464112f0f8`。

其公开 RSRS Skill 采用：窗口内 `high ~ low` OLS → `beta × R²` → 滚动 z-score。本项目采用相同研究口径，并增加单元测试：完美线性样本应得到 beta=2、R²=1、raw=2。

### Super-YYQ/stock_selector — 未确认明确许可证

固定参考提交：`106cdd86edcf4c8d7215d6dd633be4457e12afbd`。

公开策略说明中包含：
- 20 日箱体收敛/逼近上沿；
- 海龟 20/60 日附近突破；
- RPS 强势筛选；
- 放量突破、缩量承接、二次启动与策略家族聚合。

由于未确认许可证，本项目只参考公开条件和策略分层思想，未复制其源码。

## 延续参考

- `simonlin1212/vibe-astock`（Apache-2.0）：硬指标不经过 AI、实际输入体检、退化数据显式显示。
- `zhangsensen/etf-rotation-strategy`（MIT）：WFO→向量化→事件驱动审计、迟滞、波动率暴露门控；历史仓库存在凭据风险，因此不在生产 ECS 自动克隆。
- `thincat75/fund-rotation-analyst`（MIT）：主题分类、数据审计、基金质量评分。
- `illusionno/fund-analysis-matrix`（MIT）：暗色看板与基金/股票详情交互。

## v0.5 落地原则

1. 新指标先成为证据，不直接成为“买入指令”。
2. RPS 是同一 ETF/LOF 池的横截面百分位，不是单标的时间序列指标。
3. RSRS 只作为市场状态和因子之一，不能单独决定仓位。
4. ETF/LOF 筹码只称“成交密集/成本分布近似”。
5. 箱体、海龟、放量突破、缩量回踩分属不同策略家族，家族内先合成，再跨家族加权，避免同类指标重复计分。
6. 消融回测必须使用相同的次日开盘执行、费用、滑点、迟滞和风险门控，只改变因子权重。
7. Mock 数据只验证工程链路；真实生产权重必须用真实 ETF/LOF 历史数据 walk-forward 重新封版。

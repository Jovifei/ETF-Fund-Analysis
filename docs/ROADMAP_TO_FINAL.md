# 从当前 main 到最终目标：剩余路线图

更新时间：2026-09-06

本路线图只列“当前仍需要做”的事。已在 v0.8.0 / v0.8.1 完成的架构收敛，不要重复重做。

---

## 0. 最终完成的判定

项目不能因为“页面能显示、CI 全绿、生产容器 healthy”就算最终完成。

真正完成至少需要同时满足：

1. 用户从板块→持仓/自选→ETF详情→14:30 的页面工作流稳定、无重复入口；
2. 同一 ETF 所有页面 current action / 指标 / 支撑压力一致；
3. 真实 14:30 point-in-time 数据完成样本外验证；
4. 1/3/5/10 forecast 的概率/区间语义经过校准验证；
5. 真实分钟线、交易费用、滑点、停牌/涨跌停/溢价等约束进入验证；
6. 至少完成一段不下单的 shadow run；
7. 人工批准后才允许把某些“研究中”标签升级。

---

## P0 — 当前最高优先级：建立真实 14:30 point-in-time 数据集

### 为什么必须先做

目前 UI、指标、预测和 14:30 工作台都已经存在，但**日线和当前快照不能证明历史 14:30 判断有效**。这是最终目标最大的证据缺口。

### 实现要求

为每个交易日/ETF 保存：

- 14:30 之前可见的所有特征；
- 至少 5m/15m 的真实分钟 OHLCV/amount；
- 14:30 当时的 VWAP/量能等 point-in-time 字段；
- 特征 cutoff timestamp；
- 14:30 后第一条真实可成交价格；
- 后续 1/3/5/10 日真实标签；
- 新闻只使用当时已经发布的内容；
- 不得把收盘后才知道的数据回填到 14:30 特征。

### 质量检查

- 数据泄漏测试；
- 每个字段 source + timestamp；
- 缺失/停牌/异常日处理；
- 单位/复权/时区统一；
- 样本数量按 ETF/年份/市场状态统计。

### 验收

`historical_1430_backtest` 仍先保持 `not_qualified`，直到 P1/P2 全完成。

---

## P1 — 真实分钟 Provider 资格与多周期 K 线闭环

### 当前状态

`MarketBar`、30m/60m API 和详情页 interval tab 已存在；生产分钟 Provider 资格仍不完整，当前设计会诚实禁用未同步周期。

### 要做

1. 在 Provider Adapter 层实现/验证真实分钟接口；
2. 记录 source timestamp、bar end time、复权和交易日；
3. 盘中增量同步和盘后校正；
4. 验证 5m/15m（用于历史 14:30 研究）与 30m/60m（用于详情展示）是否能从同一可信来源获得；
5. provider 无能力时 fail closed，不得用 1d 下采样伪造。

### 验收

- 真实 ETF 多交易日 5m/15m/30m/60m 对账；
- 时间边界在 Asia/Shanghai 正确；
- 缺数据按钮 disabled；
- provider 审计可查。

---

## P2 — Forecast 1/3/5/10 样本外校准

### 当前合同

正式研究 horizon 固定为 `1/3/5/10`。

### 要做

对每个 horizon 做 purged expanding/rolling walk-forward，避免标签重叠泄漏。

至少记录：

- direction accuracy；
- Brier Score；
- MAE；
- q10/q50/q90 pinball loss；
- 80%/90% 区间 coverage；
- interval width；
- quantile crossing；
- path-low / path-high coverage；
- support/resistance touch Brier；
- 按年份、波动状态、板块、ETF 流动性分层。

### 校准规则

- 未过门禁：`calibration_status=not_calibrated`，`p_up` 文案只能是“历史相似样本上涨占比”；
- 过门禁并人工批准：才允许 `calibrated` 和“上涨概率”文案；
- 不允许仅因为单次回测好看自动调阈值。

### 20D

20 交易日不是当前正式合同。只有用户明确再次确认，并为 h=20 单独建立 purged WFO/校准后，才能加入新运行配置。不要把 Master Plan 的 20D 计划当成当前缺陷自动实现。

---

## P3 — 14:30 策略事件驱动验证

### 输入

必须使用 P0 的 point-in-time 数据和 P2 的研究输出。

### 回测约束

至少加入：

- 手续费；
- 滑点；
- 买卖最小单位；
- 涨跌停；
- 停牌；
- QDII/LOF 溢价/折价异常；
- 交易时间；
- 可成交性；
- 最大持仓/板块集中度；
- 已有迟滞规则；
- 用户持仓成本不作为未来信息。

### 输出

不只看收益：

- 相对基准；
- 最大回撤；
- turnover；
- win/loss distribution；
- calibration vs realized；
- 不同市场状态表现；
- 决策动作转移矩阵；
- 失败案例。

### 验收

形成可审计版本报告，与上一策略版本比较；不能只挑最好的一组参数。

---

## P4 — Shadow Run（不下单）

至少连续运行 20 个交易日，建议更长。

每日记录：

- 14:30 输入快照 ID；
- current action；
- forecast；
- 支撑/压力；
- 数据资格；
- 当天之后真实走势；
- 下一交易日/3/5/10 日兑现情况；
- provider 故障；
- 用户实际是否采纳（如用户愿意记录）。

仍然**不连接券商、不自动执行**。

Shadow Run 结束后做复盘，而不是逐日追着结果改策略。

---

## P5 — UI 结构收尾（和数据验证可并行，但优先级低于 P0–P4）

### 当前技术债

- `/holdings`、`/research`、`/system` 仍复用 legacy `index.html`；
- `legacy_route.js` 根据 pathname 激活旧 tab；
- `/decision/1430` 语义已经是 Decision 二级模式，但仍有独立 HTML/JS；
- legacy dashboard/detail DOM 仍存在兼容代码。

### 目标

1. 拆出独立 Holdings 页面/组件；
2. 拆出独立 Research/News/System；
3. Decision 和 14:30 共用同一 App Shell 和同一数据组件；
4. 删除无用户入口的旧 dashboard/detail 代码；
5. 保留旧 URL 307 兼容至少一个版本；
6. 不改变 API/current action/forecast semantics。

### 验收

- 1440/1024/390 宽度浏览器检查；
- 所有 nav active 正确；
- ETF 点击统一 `/etf/{code}`；
- 浏览器 back 行为合理；
- 旧 bookmark 不落错 tab；
- 无重复一级导航。

---

## P6 — 持仓与 ETF 详情融合增强

这是用户价值很高、但不应先于 P0–P4 的增强。

### 要做

- `/etf/{code}` 如果当前用户持有该 ETF，显示份额、成本、盈亏；
- K 线叠加成本水平线；
- 支撑/压力与成本距离；
- current action 为“减仓”或过热时，在持仓页和详情页统一提醒；
- 自选→持仓→详情之间路径无重复录入。

### 边界

持仓只属于当前用户；共享 Signal/Decision 快照不能写入用户成本。

---

## P7 — 可选数据增强

不阻塞核心完成：

- Tushare 增强板块/复权精度；
- 概念板块真实涨跌家数；
- 韩国半导体 tradable proxy；
- 更多新闻 provider；
- 更完整的 CZSC 对账；
- 图表库替换评估。

任何 provider 增加都走 Adapter + audit，不在前端/业务服务写站点私有接口。

---

## 建议执行顺序

```text
P0 真实 14:30 数据
   ↓
P1 分钟 Provider 资格
   ↓
P2 Forecast OOS 校准
   ↓
P3 事件驱动验证
   ↓
P4 Shadow Run + 人工评审
   ↓
“决策可信度闭环”完成
```

UI 的 P5/P6 可以在不改变数据合同的前提下并行，但**不要再次把主要精力放在换皮/加页面，而真实 14:30 验证继续空缺。**

---

## 每个 PR 的共同门禁

最低门禁：

```bash
pytest -q
python -m compileall -q backend/app scripts
node --check <本次涉及的所有浏览器 JS>
python codex/skills/fund-research/scripts/check_no_secrets.py
```

涉及数据库：

```bash
alembic upgrade head
alembic check
```

涉及生产运行：还必须通过 Compose、镜像 build、PostgreSQL/API smoke 和可回滚验证。

涉及策略/指标/预测语义：必须升级相应版本，并提供 walk-forward/事件回测/泄漏检查/人工批准证据。

# ETF 14:30 决策模式（当前合同）

更新时间：2026-09-06

## 1. 产品定位

当前用户可见路由：

```text
/decision/1430
```

它是 **Decision 的二级尾盘研究模式**，不是和“决策 / 板块 / 持仓 / 研究”并列的一级产品。

旧 `/workbench/1430` 仅作为兼容入口重定向到 `/decision/1430`。

页面不连接券商、不创建订单、不承诺未来收益。

---

## 2. 最重要的动作合同

14:30 模式必须展示全系统 canonical current action：

```text
可加仓 / 可入场 / 可试探 / 观望 / 减仓
```

历史上曾使用：`买入候选 / 可试探 / 持有观察 / 减仓候选 / 回避`。这些词已经退休，不得恢复为第二套 current action。

14:30 可以保留 `research_score` / component score 用于排序和解释，但它不能覆盖 canonical action。

---

## 3. 输入数据

模式只读取已经落库/物化的权威数据：

- Quote / provisional observed state；
- DailyBar；
- IndicatorSnapshot；
- persisted ForecastSnapshot（1/3/5/10）；
- SupportResistanceSnapshot；
- News evidence；
- 用户 Holding（仅用于个人 context）；
- canonical current decision。

v0.8.0 后不再在每次 HTTP 请求里从全量历史重新计算另一套 MA/MACD/KDJ/RSI/SR。

---

## 4. Forecast

当前正式 horizon：

```text
1 / 3 / 5 / 10 trading sessions
```

页面可展示：

- expected return；
- q10/q50/q90；
- terminal/path price scenario；
- sample count；
- confidence；
- calibration status。

### 文案边界

- `calibration_status != calibrated`：`p_up` 只能叫“历史上涨占比/历史相似样本上涨占比”；
- 只有经过验证并标记 `calibrated` 才能叫“上涨概率”；
- 未来情景蜡烛必须明确是 non-actual scenario。

### 14:30 provisional 与日线预测

盘中 14:30 provisional OHLCV 可用于当前研究指标/grade/SR/图表，但**不能把未收盘状态直接混入以已结算日线为邻居的 EOD forecast baseline**。Forecast 页面需暴露 as-of / feature basis。

---

## 5. 支撑压力

支撑/压力读取统一 `SupportResistanceSnapshot`，与 Decision / ETF Detail 等页面同源。

每个 level/cluster 可带：

- `price`；
- `zone_low / zone_high`；
- `strength`；
- `methods`；
- `zone_basis`。

TD9 历史 setup 接近完成的真实 K 线高低点可参与价格确认；振荡器数值本身不能直接变成支撑/压力价格。

---

## 6. 研究排序

14:30 仍可从以下维度给出 research score：

- 趋势；
- 动量；
- 量能/资金；
- 结构/SR；
- forecast；
- 新闻/数据资格。

这套 score 的作用是：**说明为什么某 ETF 排在前面**。

它不是：

- 第二套交易动作；
- calibrated return probability；
- 自动下单权重。

---

## 7. 资格门控

研究态必须显式反映：

- Mock；
- timestamp 未验证；
- stale/degraded；
- 核心数据 missing；
- 当前是否处于预期 14:20–14:40 观察窗口；
- 分钟/历史 14:30 验证资格。

任何 Mock/退化都不能冒充 actionable。

---

## 8. API

底层 14:30 API 仍可保留兼容路径：

```text
GET  /api/workbench/1430/summary
GET  /api/workbench/1430/{ts_code}
POST /api/workbench/1430/generate
```

用户页面路由和 API 路由不是一回事。后续 Agent 不要因为页面改为 `/decision/1430` 就无必要重命名稳定 API。

ETF 行点击统一去：

```text
/etf/{ts_code}
```

不打开 14:30 页面自己维护的第二详情入口。

---

## 9. 历史 14:30 验证仍未完成

日线回测不能证明 14:30 策略有效。真正需要：

- 真实 5/15 分钟 point-in-time 数据；
- 特征 cutoff <= 14:30；
- 14:30 后第一条可成交价格；
- 费用/滑点；
- 停牌/涨跌停/LOF/QDII 溢价等约束；
- point-in-time 新闻；
- 最近 6–12 个月隔离 Holdout；
- purged/rolling walk-forward；
- shadow run；
- 人工批准。

在这些完成前：

```text
historical_1430_backtest = not_qualified
```

必须保持不变。

---

## 10. UI 后续收尾

当前 `/decision/1430` 已经在产品语义上降级为 Decision 二级模式，但实现仍有独立 HTML/JS。

后续 UI 重构目标是让它和 `/` 真正复用同一 App Shell/表格/ETF detail 组件，但这属于维护性和体验改进，优先级低于真实 point-in-time 验证。

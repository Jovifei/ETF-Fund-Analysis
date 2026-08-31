# ETF 14:30 决策工作台

## 目标

`/workbench/1430` 是面向个人私有研究的 ETF/LOF 午后决策页面。它在北京时间 14:20–14:40 的研究窗口内，组合已经落库的行情、日线、指标、持仓、新闻和预测，输出五类候选：

- 买入候选；
- 可试探；
- 持有 / 观察；
- 减仓候选；
- 回避。

页面不连接券商、不创建订单，也不承诺未来收益。

## 数据和计算

### 技术特征

确定性 Python 计算：MA、MACD、KDJ、RSI、ATR、布林带、TD、量比、OBV、MFI、CMF、ADX/DMI、CCI、WR、ROC、RSRS、RPS、箱体、海龟、缩量回踩和成交密集成本分布近似。

### 多期限预测

工作台在现有相似样本基线之上，按请求动态计算 1、3、5、10 个交易日：

- 上涨概率；
- 终点收益 q10/q50/q90；
- 终点价格 q10/q50/q90；
- 路径最低价 q10/q50/q90；
- 路径最高价 q10/q50/q90；
- 样本数、相似距离和置信度。

所有预测继续标记 `not_calibrated`，直到真实数据完成 rolling-origin、隔离 Holdout 和人工批准。

### 未来蜡烛

未来蜡烛是由多期限终点中位数、路径高低分位和 ATR 组合出来的条件化情景，仅用于把概率分布可视化：

```text
is_forecast=true
not_actual=true
scenario=median_conditional_path
```

它不是对未来真实 OHLC 的宣称。

## API

```text
GET  /api/workbench/1430/summary
GET  /api/workbench/1430/{ts_code}
POST /api/workbench/1430/generate
```

`generate` 只向 `reports/` 写入 JSON 研究快照。

## 评分

默认配置在 `config/etf_1430_workbench.json`：

| 维度 | 权重 |
|---|---:|
| 趋势 | 22% |
| 动量 | 20% |
| 量能与资金流 | 14% |
| 结构与支撑压力 | 18% |
| 多期限预测 | 21% |
| 新闻 | 5% |

浏览器不重新计算生产指标或信号，只展示后端结果。

## 资格门控

只有同时满足以下条件，工作台才允许 `actionable=true`：

- 非 Mock；
- 行情不是日线退化；
- 上游 source timestamp 已验证；
- 行情未超过配置时效；
- 没有 degraded reason；
- 当前处于 14:20–14:40。

任何条件缺失都保持研究态。

## 历史 14:30 数据

日线回测不能证明 14:30 决策有效。`scripts/build_1430_point_in_time_dataset.py` 用 5/15 分钟 CSV 构建特征截止、执行价格和未来标签分离的数据集。正式结论必须使用该类 point-in-time 数据。

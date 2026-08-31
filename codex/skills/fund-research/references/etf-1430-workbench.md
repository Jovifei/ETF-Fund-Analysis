# ETF 14:30 Workbench 知识边界

- 决策窗口默认 14:20–14:40，目标时刻 14:30。
- 日线可以生成研究视图，但不能证明历史 14:30 策略。
- 真实验证必须使用截至 14:30 的 5/15 分钟 point-in-time 数据。
- 预测期限为 1、3、5、10 个交易日，默认 `not_calibrated`。
- 未来蜡烛是条件化中位情景，字段必须带 `is_forecast=true` 和 `not_actual=true`。
- MACD/KDJ/RSI 只能确认价格拐点，不能直接转换成价格线。
- 支撑压力来自多方法聚类，强度不是确定性承诺。
- `chan_zone_approx` 只是价格区间重叠近似；完整缠论需用 CZSC 对账。
- ETF `volume_profile_approx` 是成交成本分布近似，不是股东筹码。
- 实时 source timestamp 未资格验证时 `actionable=false`。
- Workbench 永远不得连接券商或创建订单。

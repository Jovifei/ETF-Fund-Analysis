# 入场/离场参考与主题相对强弱

这些字段是**展示投影**，不是第二套五档、不是新的 `indicator_version`，也不是已校准预测。Python 仍是唯一计算权威；前端只读。

## 为什么加这两项（只加小集合）

MACD / KDJ / RSI / MA 已经回答“动量和超买超卖像什么”。用户日常要的是另一件事：某一只基金/ETF 现在大概在什么价格带，以及同一主题里谁相对强。

- `entry_exit_ref`：把已落库的支撑/压力**聚类区**（`zone_low`–`zone_high`）投成附近价格带。帮助扫一眼“在带内 / 跌破支撑带 / 升破压力带”，**不把振荡指标换算成价格**。
- `theme_relative_strength`：在 `theme_l1` 内按已确认 5 日收益排序。帮助主题/行业对比；缺收益的标的保持未排名，**排名不覆盖五档**。

迟滞与官方动作仍在 `signal_service`；这里不另开一套买卖开关。

## 14:30 与收盘预测

盘中 14:30 观察可以更新研究用衍生值，持久化预测仍是 `feature_basis=settled_daily_bars` 且 `intraday_provisional_used=false`。页面上的入场带/主题排名同样 `actionable=false`。

## 实现

`backend/app/utils/decision_reference.py`，由决策快照写入每行。设计吸收（不 vendor 运行）：etf-rotation-strategy 的 sleeve 内排名；SUPPORT_RESISTANCE_SEMANTICS 的价格带而不是单点。

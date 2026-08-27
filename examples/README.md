# Mock 验证产物

这些文件由 `MARKET_PROVIDER=mock` 的确定性流水线生成，仅用于核对页面、Schema、报告和回测链路：

- `mock_report.html`：暗色研究报告快照；
- `mock_forecast_validation.json`：1/5/20 日相似预测滚动验证；
- `mock_rotation_backtest.json`：收盘决策、次日开盘执行的事件驱动轮动回测。

它们不是实时市场数据，也不是投资结论。Mock 行情被显式标记为 degraded，信号不可执行，回测报告包含 `contains_mock=true`。

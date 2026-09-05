# v0.8.1 任务驱动导航收敛合同

本变更只收敛页面入口和跳转语义，不修改 canonical current decision、指标算法、Forecast 模型、持仓数据或调度策略。

## 一级任务入口

- `/`：🎯 决策
- `/boards`：🔥 板块
- `/holdings`：💼 我的持仓（兼容壳内部定位到 holdings view）
- `/research`：🔬 研究中心（默认 Signal Research；新闻使用 `/research/news`）
- `/system`：管理员系统直达入口

`14:30` 不再作为和“决策/板块/持仓/研究”同级的产品入口；它保留 `/workbench/1430` 兼容地址，但在产品语义上是“决策”的尾盘模式。

K线不再是一级入口。任何有明确 ETF 代码的点击都统一进入 `/etf/{ts_code}`。无标的上下文的历史 `/workbench/kline` 只回到 `/`。

## 兼容策略

`/legacy` 暂时保留承载 Signal Center、持仓、新闻和系统模块；新增 `legacy_route.js` 只负责根据 hash 激活对应既有 view，不复制业务计算。后续可在独立 PR 中逐步拆成真正独立的 `/holdings`、`/research`、`/system` 页面。

## 14:30 合同

14:30 页展示 canonical 五档：`可加仓 / 可入场 / 可试探 / 观望 / 减仓`。研究综合分仍只用于排序说明，不能生成第二套 current action。ETF 行点击统一进入全局详情页。

未校准 `p_up` 的页面文案为“历史上涨占比”；只有 calibrated 才允许写“上涨概率”。

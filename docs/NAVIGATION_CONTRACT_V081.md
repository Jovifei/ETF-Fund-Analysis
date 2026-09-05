# v0.8.1 任务驱动导航收敛合同

本变更只收敛页面入口和跳转语义，不修改 canonical current decision、指标算法、Forecast 模型、持仓数据或调度策略。

## 一级任务入口

- `/`：🎯 决策
- `/boards`：🔥 板块
- `/holdings`：💼 我的持仓
- `/research`：🔬 研究中心（默认信号研究）
- `/research/news`：研究中心的新闻证据视图
- `/system`：管理员系统直达入口

这些 URL 都是用户可见的一等地址，不再把正常导航重定向成 `/legacy#...`。实现上当前仍复用原综合控制台的 HTML/JS 壳，但由 `legacy_route.js` 根据 pathname 激活对应已有模块；这是兼容迁移，不复制业务计算。

`14:30` 不再作为和“决策/板块/持仓/研究”同级的产品入口。它暂时保留 `/workbench/1430` 兼容地址，但在产品语义上是“决策”的尾盘模式，只从决策页的次级入口进入。

K线不再是一级入口。任何有明确 ETF 代码的点击都统一进入 `/etf/{ts_code}`。无标的上下文的历史 `/workbench/kline` 只回到 `/`。

## 历史入口兼容

- `/legacy` -> `/research`
- `/assets/index.html` -> `/research`
- `/assets/etf_1430_workbench.html` -> `/workbench/1430`
- `/workbench/kline` -> `/`
- `/assets/kline_stabilization.html` -> `/`

旧 hash 书签仍由兼容壳识别，但新导航不再生成 `/legacy` URL。后续独立 PR 可以把 `/holdings`、`/research`、`/system` 拆成真正独立的页面组件；本 PR 先解决用户跳转心智，不冒险重写大体量 `app.js`。

## 统一 ETF 详情

决策表、板块成员、持仓、14:30 尾盘模式中的 ETF 都应进入：

```text
/etf/{ts_code}
```

不再维护 Kline 全市场页或各页面自己的第二个详情入口。

## 14:30 合同

14:30 页展示 canonical 五档：`可加仓 / 可入场 / 可试探 / 观望 / 减仓`。研究综合分仍只用于排序说明，不能生成第二套 current action。ETF 行点击统一进入全局详情页。

未校准 `p_up` 的页面文案为“历史上涨占比”；只有 calibrated 才允许写“上涨概率”。

# v0.8.1 任务驱动导航收敛合同

本变更只收敛页面入口、跳转语义与发布镜像版本漂移，不修改 canonical current decision、指标算法、Forecast 模型、持仓数据或调度策略。

## 一级任务入口

- `/`：🎯 决策
- `/boards`：🔥 板块
- `/holdings`：💼 我的持仓
- `/research`：🔬 研究中心（默认信号研究）
- `/research/news`：研究中心的新闻证据视图
- `/system`：管理员系统直达入口

这些 URL 都是用户可见的一等地址，不再把正常导航重定向成 `/legacy#...`。实现上当前仍复用原综合控制台的 HTML/JS 壳，但由 `legacy_route.js` 根据 pathname 激活对应已有模块；这是兼容迁移，不复制业务计算。

## 14:30 是决策模式，不是并列产品

14:30 的用户可见语义地址是：

```text
/decision/1430
```

它属于“决策”的尾盘研究模式，只从决策页次级入口进入，不再和“决策 / 板块 / 持仓 / 研究”并列。

历史：

```text
/workbench/1430
```

只作为兼容书签，307 到 `/decision/1430`。

## K线是 ETF 详情，不是一级入口

任何有明确 ETF 代码的点击都统一进入：

```text
/etf/{ts_code}
```

无标的上下文的历史 `/workbench/kline` 只回到 `/`，因为系统不能替用户猜要看哪一只 ETF。

## 历史入口兼容

- `/legacy` -> `/research`
- `/assets/index.html` -> `/research`
- `/workbench/1430` -> `/decision/1430`
- `/assets/etf_1430_workbench.html` -> `/decision/1430`
- `/workbench/kline` -> `/`
- `/assets/kline_stabilization.html` -> `/`

旧 hash 书签仍由兼容壳识别，但新导航不再生成 `/legacy` 或 `/workbench/*` URL。后续独立 PR 可以把 `/holdings`、`/research`、`/system` 拆成真正独立的页面组件；本 PR 先解决用户跳转心智，不冒险重写大体量 `app.js`。

## 统一 ETF 详情

决策表、板块成员、持仓、14:30 尾盘模式中的 ETF 都应进入：

```text
/etf/{ts_code}
```

不再维护 Kline 全市场页或各页面自己的第二个详情入口。

## 14:30 数据与动作合同

14:30 页展示 canonical 五档：

```text
可加仓 / 可入场 / 可试探 / 观望 / 减仓
```

`research_score` 仍只用于排序说明，不能生成第二套 current action。ETF 行点击统一进入全局详情页。

未校准 `p_up` 的页面文案为“历史上涨占比”；只有 `calibration_status=calibrated` 才允许写“上涨概率”。

## Production image 版本合同

项目版本只由 `pyproject.toml` 管理。builder 先生成当前源码对应的 wheel，runtime 再从 `/wheels` 离线安装：

```text
china-fund-decision[market]
```

Dockerfile 禁止再次硬编码：

```text
china-fund-decision[market]==<version>
```

否则发布版本提升时会出现 pyproject 与 Docker runtime 安装版本漂移。本合同由 `test_production_ops_contract.py` 自动锁定。

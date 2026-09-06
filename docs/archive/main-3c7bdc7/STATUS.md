# 工程状态

更新时间：2026-09-06
应用发行版本：`0.8.0`
当前产品/导航合同：`v0.8.1`

> 详细状态请先读 `docs/README.md`、`docs/PROJECT_HANDOFF_20260906.md`、`docs/IMPLEMENTATION_MATRIX.md` 和 `docs/ROADMAP_TO_FINAL.md`。本文件只保留接手时最重要的当前事实。

## 当前结论

系统已经从“多个历史页面/多套局部语义”收敛为个人 14:30 ETF 研究工作流：

- 决策：`/`
- 板块：`/boards`
- 持仓：`/holdings`
- 研究：`/research`
- 新闻：`/research/news`
- 系统：`/system`
- 14:30 决策二级模式：`/decision/1430`
- 全局 ETF 详情：`/etf/{code}`

旧 `/legacy`、`/workbench/1430`、`/workbench/kline` 仅做兼容，不应重新成为一级入口。

## v0.8.x 已完成的关键收敛

- 清除静态假行情回退；
- 注册 fail-closed；
- HttpOnly Cookie + CSRF，清除浏览器旧 Bearer/localStorage 路径；
- canonical current action 唯一来源；
- IndicatorSnapshot / 指标展示语义收敛；
- SupportResistanceSnapshot 单一来源；
- 支撑/压力 Zone + TD9 价格确认；
- `/etf/{code}` 全局唯一详情；
- `/boards` 一等板块页；
- 用户 watchlist；
- holdings 融合 current action、1/3/5/10 forecast、S/R；
- `market_bars` 30m/60m 底座与诚实禁用；
- 新闻 heuristic/model provenance 分层；
- 14:30 动作词收敛为 canonical 五档；
- 任务驱动导航收敛。

v0.8.0 release 记录过完整测试、生产迁移和健康状态；后续变更仍必须产生自己的 CI/部署证据。

## 当前 forecast 合同

正式研究 horizon：

```text
1 / 3 / 5 / 10 trading sessions
```

- 预测仍以研究情景为主；
- 未校准 `p_up` 只能叫“历史相似样本上涨占比”；
- 20D 不是当前运行合同；
- 策略/指标/预测版本与 app release version 分离。

## 当前最大卡点

不是缺页面，而是**真实决策有效性证据还没闭环**：

1. 真实 5/15m 14:30 point-in-time 历史数据；
2. 14:30 cutoff、第一条可成交价格、费用、滑点、涨跌停/停牌/溢价约束；
3. 1/3/5/10 forecast 样本外校准；
4. 事件驱动验证；
5. Shadow Run；
6. 人工批准。

在这些完成前：

```text
historical_1430_backtest = not_qualified
calibration_status = not_calibrated   # 对尚未通过校准的期限
```

不得被 UI 或 Agent 擅自升级。

## UI 当前技术债

- `/holdings`、`/research`、`/system` 的语义路由已正确，但底层仍复用 legacy `index.html` 大壳；
- `/decision/1430` 已是 Decision 二级模式，但仍有独立 HTML/JS；
- 后续可拆独立组件、删除兼容 DOM，但优先级低于真实 14:30 验证。

## 必须遵守

- 不自动交易；
- 不让 AI 计算指标/动作；
- Mock/stale/unverified/missing 不冒充真实；
- 日 K 不冒充分钟 K；
- UI 不创建第二套 score/action；
- 所有 ETF 详情统一 `/etf/{code}`；
- 修改策略/预测/指标先版本化、写失败测试、做完整验证。

下一步按 `docs/ROADMAP_TO_FINAL.md` 从真实 14:30 point-in-time 数据开始。

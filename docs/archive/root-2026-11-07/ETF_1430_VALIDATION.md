# ETF 14:30 最终验证清单

更新时间：2026-09-06

> 当前 `/decision/1430` 功能和页面已经存在，但**历史 14:30 策略仍未获得资格**。CI 通过、生产容器 healthy、日线预测可显示，都不能替代 point-in-time 验证。

---

## 1. 代码门禁

每次相关修改至少运行：

```bash
pytest -q
python -m compileall -q backend/app scripts
node --check backend/app/static/app.js
node --check backend/app/static/decision_board_workbuddy.js
node --check backend/app/static/etf_1430_workbench.js
node --check backend/app/static/etf_detail.js
python codex/skills/fund-research/scripts/check_no_secrets.py
```

涉及数据库时额外：

```bash
alembic upgrade head
alembic check
```

涉及生产运行还需 Compose、production image build、PostgreSQL/API smoke。

---

## 2. 浏览器门禁

至少在 1440、1024、390 像素宽度检查：

- Decision → 14:30 的入口层级正确；
- `/decision/1430` 不出现在一级业务导航中；
- 候选排名；
- canonical 五档动作；
- 1/3/5/10 日 forecast；
- “历史上涨占比”与 calibrated probability 文案边界；
- 历史与 forecast scenario 分界；
- 支撑/压力 Zone；
- 详情点击进入 `/etf/{code}`；
- MA/MACD/KDJ/RSI/TD9 等解释；
- Mock/degraded/unverified/stale 的阻断提示；
- 原 Decision / Holdings / Boards / Research 无导航回归。

---

## 3. 真实 point-in-time 数据门禁

必须有真实历史数据，至少包含：

- 5m/15m OHLCV/amount；
- 每根 bar 的 source timestamp；
- 特征 cutoff；
- 截至 14:30 的量能/VWAP/技术状态；
- 14:30 后第一条可成交价格；
- 停牌/涨跌停/异常交易日状态；
- ETF/LOF/QDII 的溢价/折价等相关字段（适用时）；
- 新闻发布时间，保证只使用当时已知新闻；
- 后续 1/3/5/10 日标签。

禁止：

- 用收盘数据回填 14:30；
- 用日 K 伪造分钟状态；
- 用当天之后发布的新闻；
- 用最终复权/后验字段造成 leakage 而不记录。

---

## 4. Forecast 验证指标

每个 horizon 单独报告：

- direction accuracy；
- Brier Score；
- MAE；
- pinball loss；
- 80%/90% coverage；
- interval width；
- quantile crossing；
- path-low/path-high coverage；
- support/resistance touch Brier。

还要分层：

- 年份；
- 波动状态；
- ETF 流动性；
- 行业/宽基/QDII 等类别；
- bullish/bearish/sideways 市场状态。

---

## 5. Walk-forward / Holdout 门禁

最低要求：

- purged expanding/rolling folds；
- horizon-aware purge，防止标签重叠；
- 最近 6–12 个月隔离 Holdout（数据量允许时）；
- 参数冻结；
- 和上一版本/简单基线比较；
- 记录所有 fold 边界和输入版本；
- 不允许根据 Holdout 反复调参数后仍称其为 Holdout。

---

## 6. 事件驱动交易约束

即使研究系统不自动下单，验证仍必须模拟真实可执行约束：

- 手续费；
- 滑点；
- 最小交易单位；
- 涨跌停；
- 停牌；
- 可成交价格；
- QDII/LOF 高溢价风险；
- 组合仓位上限；
- 板块集中度；
- 已有迟滞/换手约束；
- 市场门控。

不能只用 close-to-close 理想收益证明 14:30 有效。

---

## 7. Shadow Run 门禁

在任何“策略通过”表述前，至少完成一段真实交易日 shadow run：

- 每天 14:30 自动形成审计快照；
- 不下单；
- 不追着次日结果自动改阈值；
- 记录 provider 错误、stale、missing；
- 定期对 1/3/5/10 日预测兑现情况复盘。

建议至少 20 个交易日，最好覆盖更多市场状态。

---

## 8. 最终结论边界

只有当真实 point-in-time + forecast OOS + 事件约束 + shadow run + 人工批准都完成后，才允许：

- 把 `historical_1430_backtest` 从 `not_qualified` 升级；
- 把某一 horizon 的 `calibration_status` 升级为 `calibrated`；
- 更新相应策略/预测版本和封版记录。

在此之前，所有 14:30 输出仍是**研究提示，不是投资建议或自动交易指令**。

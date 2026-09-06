# 系统架构（v0.8.x 当前事实）

更新时间：2026-09-06  
应用发行版本：`0.8.0`  
导航/产品合同：`v0.8.1`

> 本文描述当前 main 的运行架构。历史 0.7 设计、Master Plan 的未落地项请看 `docs/README.md` 的权威层级说明。

---

## 1. 系统定位

这是个人私有的中国 ETF/LOF 研究系统，核心工作流围绕每个交易日约 14:30 的研究判断：

```text
板块发现
   ↓
自选 / 持仓
   ↓
统一 ETF 详情研判
   ↓
14:30 决策模式
   ↓
可加仓 / 可入场 / 可试探 / 观望 / 减仓
```

系统不连接券商、不自动下单。AI 不计算指标、预测、仓位或 current action。

---

## 2. 总体架构

```text
Tushare / AKShare / RSS / 其他合格公开源
                    │
             Provider Adapter
 timeout / provenance / capability / audit
                    │
                    ▼
              PostgreSQL 16
 instruments / daily bars / market_bars / quotes
 sector snapshots / market context / indicators
 forecasts / support-resistance / signals / decisions
 holdings / watchlist / news / reports / audits / tasks
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
    Scheduler                 FastAPI
  30s tick / slots       API + SSE + static UI
        │                       │
        └───────────┬───────────┘
                    ▼
                  Browser
 Decision / Boards / Holdings / Research
      /decision/1430 /etf/{code}

可选 Analysis Gateway：OpenAI-compatible / 其他人工选择主 provider
只接收证据包，只输出结构化解释，不拥有写库/网络/券商工具。
```

---

## 3. 当前用户路由合同

| 任务 | 路由 | 实现说明 |
|---|---|---|
| 决策 | `/` | WorkBuddy 信息架构演进后的统一决策总览 |
| 板块 | `/boards` | 板块 breadth + ETF 代理 |
| 持仓 | `/holdings` | 当前仍复用 legacy research shell 的 holdings 模块 |
| 研究 | `/research` | 当前仍复用 legacy research shell 的 signals 模块 |
| 新闻 | `/research/news` | research shell news 模块 |
| 系统 | `/system` | research shell system 模块 |
| 14:30 | `/decision/1430` | 决策的二级尾盘研究模式 |
| ETF 详情 | `/etf/{ts_code}` | 全系统唯一单标的详情 |

兼容旧地址：`/legacy`、`/workbench/1430`、旧静态 HTML 等只做重定向/书签兼容，新 UI 不生成这些 URL。

---

## 4. 单一 current action 架构

同一 ETF 同一时刻只能有一个 current action。页面、Signal Center、14:30 排名分都不能生成自己的第二套动作。

当前原则：

```text
已物化/当前决策快照
        ↓
canonical current action
        ↓
Decision / Boards / Holdings / Research / 14:30 / ETF Detail
```

跨页面测试必须保证 action/source/snapshot lineage 一致。

研究 score、Signal Center coefficient、14:30 component score 只用于解释/排序，不得覆写 current action。

---

## 5. 指标唯一权威

技术指标以持久化 `IndicatorSnapshot` 和统一指标状态函数为权威。

v0.8.0 已完成：

- MA/MACD/KDJ/RSI/TD9/量能展示语义统一；
- Kline/14:30 请求不再各自从全量历史重算一套指标；
- 页面只读展示后端状态；
- 指标公式或初始化改动仍需升级策略/指标版本并重新验证。

前端禁止恢复 `scoreRow` 一类二次计算来改变 official action。

---

## 6. 支撑/压力唯一权威

`SupportResistanceSnapshot` 是跨页面支撑/压力的统一存储。

核心合同：

- 同一时刻不同页面读取同一快照；
- 默认使用统一历史窗口与真实成交额输入；
- 输出为 `zone_low / zone_high / strength / methods`；
- TD9 历史反转价格可作为聚类确认；
- 振荡器数值本身不能被当成价格。

ETF 详情将 Zone 以半透明区域叠加在 K 线上。

---

## 7. Forecast 架构

当前正式研究 horizon：

```text
1 / 3 / 5 / 10 trading sessions
```

这是经过专门 `HORIZON_ALIGNMENT_20260903.md` 对齐后的代码合同。

- persisted forecast snapshot 为权威；
- 未校准时 `p_up` 只是历史相似样本上涨占比；
- 未来蜡烛/走廊是研究情景，不是未来真实 OHLC；
- 14:30 provisional 状态不能污染收盘日线邻居基准；
- 20D 不是当前运行合同，只保留历史兼容/未来研究可能性。

预测真正升级到 calibrated 之前仍需 purged walk-forward、Holdout 和人工批准。

---

## 8. 14:30 模式

当前用户可见路由：`/decision/1430`。

它消费已经落库的：

- Quote / DailyBar / IndicatorSnapshot；
- ForecastSnapshot；
- SupportResistanceSnapshot；
- News；
- 用户 Holding（只用于个人显示/研究）；
- canonical current action。

14:30 页面可以有 component research score 和排序，但动作词必须是 canonical 五档：

```text
可加仓 / 可入场 / 可试探 / 观望 / 减仓
```

历史有效性仍未获得资格：真实 5/15m point-in-time、费用/滑点、可成交价、隔离 Holdout、shadow run 完成前，`historical_1430_backtest` 必须保持 `not_qualified`。

---

## 9. 多周期 MarketBar

`market_bars` 支持分钟/日周期存储，当前详情 UI 对外关注 `30m / 60m / 1d`。

原则：

- 日 K 不冒充分钟线；
- 未同步真实分钟数据时按钮 disabled；
- Mock 可用于测试生成，但生产 Mock 必须 non-actionable；
- 真实 5/15m 数据还需要用于 14:30 历史 point-in-time 验证。

当前最大缺口不是数据表，而是真实分钟 Provider 的资格与长期数据。

---

## 10. 板块与市场上下文

### Boards
`/boards` 聚合：

- SectorSnapshot breadth；
- 板块当日变化/上涨/下跌等已知字段；
- 池内 ETF 代理及 canonical action。

必须明确：**ETF 代理不是板块指数。** 无真实 breadth 时显示 unavailable，不用成员 ETF 伪造板块行情。

### Market context
市场环境属于观察证据，不是自动行业进入条件。每项必须保存 source/time/verification。

---

## 11. Watchlist / Holdings / 用户隔离

系统全局 Universe 与用户 watchlist 分离。

- 用户可按合法 ETF 代码添加自选；
- 持仓包含 shares/cost/target weight 等用户私有字段；
- holdings API 融合 canonical action、1/3/5/10 forecast、最近 S/R；
- Holding/OCR/report/private SSE 按 user_id 隔离；
- 共享决策/信号快照不得持久化用户成本。

当前页面仍复用 legacy research shell，这是 UI 技术债，不是数据模型缺失。

---

## 12. 新闻与 AI 分层

新闻卡片必须区分：

1. 原始新闻/事实；
2. 词典/规则启发式解释；
3. 可选模型分析。

模型不能覆盖原始事实和 current action。模型 provider 失败不静默切换另一个模型。

---

## 13. OCR 数据流

```text
PNG/JPEG/WebP
  -> Pillow MIME/magic/decode/dimension/pixel checks
  -> 可选本地 OCR worker
  -> 候选 code/name/shares/cost/target weight
  -> 用户编辑 / 拒绝 / 消歧
  -> 显式确认
  -> HoldingService.upsert
```

确认前不写持仓。原图不进入普通业务数据库。生产未具备合格 OCR 模型时诚实 unavailable/503。

---

## 14. 部署与运行

- PostgreSQL 16；
- Alembic 为唯一 schema 变更方式；
- API / scheduler 独立容器；
- scheduler 30s tick 检查到期任务；
- 公网经 HTTPS 反代；
- 生产 `.env` 不入 Git；
- Mock fallback 不能在生产冒充真实；
- 先备份 → migrate → health/provider audit/smoke → 可回滚。

v0.8.0 已有生产同步/迁移/健康记录，但后续每次部署仍需重新产生本次变更对应的证据。

---

## 15. 当前最重要的未完成边界

1. 真实 14:30 point-in-time 5/15m 数据与事件回测；
2. 1/3/5/10 forecast 样本外校准；
3. 真实分钟 Provider 长期资格；
4. shadow run + 人工批准；
5. UI legacy 壳拆分和 Decision/14:30 真正组件复用。

详细顺序见 `ROADMAP_TO_FINAL.md`。

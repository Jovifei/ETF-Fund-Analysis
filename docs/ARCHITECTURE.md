# 系统架构

## 组件

```text
┌──────────────────────────────────────────────────────────────┐
│ Tushare │ AKShare │ optional RSS/Atom │ OpenAI-compatible    │
└───────────────┬──────────────────────────────────────────────┘
                │ Provider Adapter / timeout / fallback
                ▼
┌──────────────────────────────────────────────────────────────┐
│ PostgreSQL                                                   │
│ instruments / daily_bars / quotes / indicators / forecasts  │
│ signals / holdings / news / audits / tasks / events / report│
└───────────────┬──────────────────────────────────────────────┘
                │
       ┌────────┴────────┐
       ▼                 ▼
  scheduler          FastAPI
  定时任务             API + SSE + 静态看板
       │                 │
       └────────┬────────┘
                ▼
          浏览器 / HTML 报告
```

## 为什么不使用 Redis/Celery

当前目标是一台用户自有的小型阿里云 ECS 和几十只 ETF/LOF。独立 Python scheduler + PostgreSQL 已能满足：

- 3 分钟行情；
- 10～15 分钟信号；
- 30 分钟新闻；
- 跨进程事件；
- 任务审计；
- 分布式互斥。

引入 Redis/Celery 会增加端口、内存、备份和故障模式。后续当标的扩展到数百只、分钟线大规模存储或多 worker 并发时，再评估 Celery/Redis/TimescaleDB。

## 数据流

### 行情和日线

1. Provider 拉取记录。
2. 标准化代码、日期、OHLCV、成交额、复权口径和来源。
3. 保存质量哈希。
4. Composite Provider 记录主源失败和备用源命中。
5. 非实时快照显式写入 `degraded_reason`。

### 指标

由 `utils/indicators.py` 计算。指标快照保存：

- `as_of_date`；
- 指标版本；
- 技术分和风险分；
- 数据质量；
- 输入哈希；
- 完整数值 JSON。

### 新闻

1. 聚合 Tushare 和配置的 RSS/Atom。
2. 按 `source + source_id` 去重。
3. 启发式主题分类和情绪方向。
4. 可选调用 OpenAI-compatible JSON Schema。
5. 保存事实、推断、风险、主题、影响期和模型名。

LLM 不拥有工具，新闻中的提示词一律作为不可信正文。

### 预测

相似样本基线在每个历史时点只使用当时及以前的特征，并检索历史样本的未来 1/5/20 日收益。输出概率和区间，而不是一个伪精确点估计。

### 信号

```text
实际输入体检
  ↓
技术分 / 风险分 / 主题新闻 / 基金交易质量 / 预测
  ↓
市场风险状态与组合总暴露
  ↓
单基金、单主题、单次调整约束
  ↓
持仓感知标签
  ↓
状态迟滞
  ↓
SignalSnapshot + evidence + expires_at
```

没有持仓时不会产生“加仓/减仓”；数据退化、Mock、非交易时段或核心输入缺失时不会产生 actionable。

## 并发和一致性

- PostgreSQL 生产任务使用 `pg_try_advisory_xact_lock` 全局互斥。
- 本地 SQLite 使用进程锁。
- 每个任务有 `run_id`、状态、开始/结束时间、结果和错误。
- API 和 scheduler 通过数据库 `event_log` 共享 SSE 事件。
- 业务表尽量使用唯一键做幂等 upsert。

## 网络边界

- `db` 仅在 Compose 网络内。
- `api` 只映射到宿主机 `127.0.0.1`。
- `scheduler` 无入站端口。
- 公网只经过 Caddy/Nginx 的 443。
- API 使用 Bearer Token；SSE 也通过 Authorization Header，不把 Token 放查询串。

# 系统架构（0.7.0）

## 组件与边界

```text
Tushare / AKShare / RSS       OpenAI Responses (可选，单一主 provider)
          │                            │
          └── Provider Adapter ────────┘
              timeout / provenance / no silent fallback
                         │
                    PostgreSQL
 instruments / bars / quotes / context / indicators / forecasts
 signals / holdings / OCR sessions / analysis runs / audits / tasks
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
          scheduler                FastAPI
       bounded cadence          API + SSE + static UI
              │                     │
              └──────────┬──────────┘
                         ▼
                    browser / reports
```

应用/发行包版本是 `0.7.0`。策略、指标和预测版本不是发行包版本，继续由 `config/strategy.json` 提供（当前策略 `signal-v0.7.0-research`）；本次不改变指标公式、信号阈值、预测特征或回测版本。

## 分析网关

应用先构建带输入哈希、来源、时间、新鲜度、策略/指标/预测版本和证据 ID 的只读证据包。配置必须且只能选一个主 provider：默认推荐 Codex/OpenAI Responses（`OPENAI_API_KEY`、`ANALYSIS_PRIMARY_MODEL`、`ANALYSIS_CODEX_BASE_URL`、`ANALYSIS_PRIMARY_MODE=responses`）。Anthropic Messages、DeepSeek 兼容 provider 为手工切换候选；失败是明确失败，不会静默 failover。

模型只能输出事实、推断、风险、主题和置信度文本。模型没有工具、凭据、数据库写入、网络抓取、指标/预测/仓位计算或券商能力。Codex/Claude Code 运行器只在应用已生成证据包后异步产生只读 review candidate；人工明确接受才进入 review 记录。

## 行情与市场上下文

行情流程保留 `source`、来源时间、抓取时间、实时/退化/Mock 状态和输入哈希；today change 是观察卡片主字段，价格为次级字段。缺失、Mock、冲突单位或不可用来源阻断 actionable 信号。

市场上下文注册表默认六项：

1. 中国行业/板块广度与轮动；
2. S&P 500；
3. Nasdaq Composite；
4. Nasdaq-100；
5. 中国半导体可交易 ETF 代理；
6. 韩国半导体可交易 ETF 代理。

两项半导体代理的 `source_symbol`/`display_code` 默认是 null，且 disabled/unverified。只有 Provider 资格包同时证明交易所代码、日线/现货覆盖、流动性、来源时间和字段质量后才可启用；历史快照不能冒充当前观察。上下文任务默认每 15 分钟，scheduler 每 30 秒只检查任务是否到期。

## OCR 数据流

```text
PNG/JPEG/WebP upload
  -> Pillow MIME/magic/decode/dimension/pixel/trailing-data checks
  -> local Paddle worker (optional, spawn + hard timeout)
  -> candidate rows: code/name/shares/cost/target weight/note
  -> operator edit / reject / resolve ambiguity
  -> explicit confirm
  -> HoldingService.upsert
```

图片只存于独立私有临时根，成功确认/取消后清理，TTL 任务清理遗留会话；数据库不保存原图或完整原始 OCR。默认 10MiB、12,000×12,000、4,000 万像素、60 秒硬超时、15 分钟 TTL。Paddle 仅接受 Python 3.12/Linux 本地资格验证、严格 `paddle-local-v1` manifest（路径/字节数/SHA-256）和私有只读模型根；真实 Paddle 包/模型当前未资格验证。Docker 基础镜像不装重型 Paddle，缺少合格模型时返回 unavailable/503。生产 Windows fail-closed；Linux 临时根 0700、模型根私有只读。云视觉复核默认关闭、只在明确同意后可用，当前环境不出网。

## 并发、迁移与部署

- PostgreSQL 任务使用 advisory lock；SQLite 仅用于本地/测试。
- API 与 scheduler 通过事件表共享 SSE 事件；唯一键提供幂等。
- 迁移顺序固定为 `158ca7025305` → `9f1c2b3a4d5e` → `a2b3c4d5e6f7` → `b3c4d5e6f7a8` → `c4d5e6f7a8b9` → `d5e6f7a8b9c0` → `e6f7a8b9c0d1` → `f7a8b9c0d1e2` → `0a9b1c2d3e4f` → `1b2c3d4e5f6a` → `2c3d4e5f6a7b`（当前 head）。生产先备份，再 `alembic upgrade head`；回滚先隔离恢复和 hash 校验，禁止手工改库。隔离 SQLite 已完成 `upgrade head`、`downgrade base`/re-upgrade 与 `alembic check`。ORM 对齐保留既有 review/analysis hash-check 名称、opaque-session 约束和 nullable legacy calibration JSON，而不是生成会重写现有数据的迁移；真实 PostgreSQL 迁移/回滚/备份恢复仍需资格验证。
- Compose 只把 API 绑定到 `127.0.0.1:8080`，数据库不暴露宿主机端口，公网只经过 Caddy/Nginx HTTPS。OCR 应用图像上限 10MiB，Caddy/Nginx body limit 用 12MB 覆盖 multipart 开销。
- `.env` 为 0600；OCR transient root 为 0700；模型根私有且只读。生产配置在 Windows 上对 OCR fail-closed。

真实 PostgreSQL、Provider 出口/权限、OpenAI 端点、Paddle wheel/model、ECS、HTTPS 和预测校准都是部署门槛；本地测试、Mock 数据和候选报告不构成生产或投资结论。

## 研究视图分层（信号中心 vs 信号分级 vs 板块）

两层都只读，都不写持仓、不连券商、不改变生产引擎 `signal-v0.7.0-research` 的权重与阈值。

| 视图 | 版本 | 数据 | UI |
|---|---|---|---|
| 决策看板板块 | `board-catalog-v0.1.0` | 静态行业/概念目录 + 主题 ETF 代理指标分 | 东财式名称卡片；不爬东财指数 |
| 信号中心 | `signal-center-v0.1.0` | 已落库 SignalSnapshot 等；系数只改该页前排/曲线 | 机会 / 风险 / 止盈 三桶 |
| ETF 信号分级 | `signal-grade-v0.2.0` | IndicatorSnapshot + Quote + 1 日 Forecast | 单基五档彩色表 |

板块分数由量能/均线/MACD/KDJ/RSI/九转/近周系数加权。无代理 ETF 时显示未验证。市场环境六卡不是行业进入依据。预测单元格必须带「FORECAST · 非实际结果」。

## ETF 14:30 Workbench

```text
DailyBar / Quote / Indicator / Forecast / News / Holding
                    │
                    ▼
        ETF1430WorkbenchService
       ├── 1/3/5/10 similarity forecast
       ├── support_resistance clustering
       ├── research scoring / fail-closed gate
       └── forecast scenario candles
                    │
          /api/workbench/1430/*
                    │
          /workbench/1430 Canvas UI
```

历史 14:30 验证另由 5/15 分钟 point-in-time 数据集承担，不能从全天日线倒推。

# 本地真实计算到网站展示：端点盘点与范围封版（Phase A）

> 分支：`codex/local-live-to-website`  
> 基线：`0f8d16e724a5d3969172f3a565a4d87d1c7cc1c6`（基于 `f514a6e` 及 `main` tip `e722ad5`）  
> 状态：PHASE_A_FROZEN · 只读盘点与契约封版 · **未变更生产环境或业务数据**

---

## 1. 业务端点与展示域映射表（Endpoint Scope Matrix）

根据对 `frontend/src/views/`（`Overview.vue`, `Detail.vue`, `Holdings.vue`, `Matrix.vue`, `News.vue`, `Settings.vue` 等）与 `backend/app/workspace/api.py` 的逐项审查，确定端点归属与消费模式如下：

| 端点 (Endpoint) | 前端调用组件 | 数据域 (Domain) | 迁移方式 / `local-display-v2` 对应 Part | 空态 / 缺口处理策略 |
|---|---|---|---|---|
| `GET /api/workspace/overview` | `Overview.vue`, `Matrix.vue` | 公共研究展示 (Bundle) | 映射到 bundle `overview` part（含 compact rows、theme 分组、5档、1/3/5/10 预测、digest） | 缺主题返回全量；无 bundle 返回 `STALE` 历史包或结构化空态，不回退云端实时计算 |
| `GET /api/workspace/instruments/{code}` | `Detail.vue` | 公共研究展示 (Bundle) | 映射到 bundle `detail/{code}` part（指标、1/3/5/10 预测、分位、置信度、未校准标记） | 标的不在 universe 返回 `instrument_not_in_catalog` (404)；字段缺失返回 `availability=false` |
| `GET /api/workspace/instruments/{code}/chart` | `Detail.vue` (`EtfChart.vue`) | 公共研究展示 (Bundle) | 映射到 bundle `charts/{code}/{interval}` part（最多 250 根 K 线、指标、支撑阻力、均线） | 日线优先（1d）；周/月（1w/1mo）本机派生；30m/60m 暂无源返回 `unsupported_chart_interval` (422) 或空态，严禁云端兜底抓取 |
| `GET /api/workspace/instruments/{code}/chan` | `Detail.vue` (`ChanEvidenceCard.vue`) | 公共研究展示 (Bundle) | 包含在 `detail/{code}` 或独立 `chan/{code}` part（缠论中枢/分型） | 暂无缠论计算则返回 `available: false`，UI 卡片显示未启用，不阻塞详情 |
| `GET /api/workspace/sectors` | `Overview.vue` | 公共研究展示 (Bundle) | 映射到 bundle `sectors` part（行业板块强弱概览） | 数据缺口显示“板块概览暂不可用”，保留基础表格 |
| `GET /api/workspace/market-context` | `Overview.vue` | 公共研究展示 (Bundle) | 映射到 bundle `market_context` part 或保留云端历史视图 | 标记 `freshness=historical`，不自动触发云抓取 |
| `GET /api/workspace/indexes` | `Overview.vue` | 公共研究展示 (Bundle) | 映射到 bundle `indexes` part（3只代表指数） | 缺数据标明 `available: false` |
| `GET /api/workspace/research-outlook` | `Overview.vue` (`OutlookPanel.vue`) | 公共研究展示 (Bundle) | 映射到 bundle `outlook` part（1/5/20日预测总览） | 仅展示已实现 horizon，不发虚假预测 |
| `GET /api/workspace/holdings` | `Holdings.vue` | **云端私有域 (Private)** | **绝对保留在云端数据库**；现价与 P&L 借用当前代 bundle 最新 quote 计算 | 持仓与账户**绝不**离云，Producer **无权**读取云端持仓；若 quote 缺失显示“价格待更新”，不拉取行情 |
| `GET /api/workspace/watchlist` | `Watchlist.vue` | **云端私有域 (Private)** | **绝对保留在云端数据库**；自选池与本地 bundle 关联展示现价 | 仅在用户登录 Session 内授权读取 |
| `GET /api/workspace/portfolio-risk` | `Holdings.vue` | **云端私有域 (Private)** | 云端根据用户持仓和 bundle 收益率在会话中计算风险指标 | 私有数据不进入本地计算输入 |
| `GET /api/workspace/account` / `preferences` | `Profile.vue`, `Settings.vue` | **云端私有域 (Private)** | 云端认证数据库读写 | 不受数据源切换影响 |
| `GET /api/workspace/news-status` | `News.vue` | 云端公开域 | 保留既有 RSS 状态（独立于市场行情） | 不受影响 |
| `POST /api/workspace/data-jobs` | 各管理组件 | 管理操作 (Admin) | 云端市场任务（如 `prepare_history`, `recompute`）**阻断执行**（返回 `display_only_mode`） | 引导至本机 CLI `run_local_compute.py` 执行 |
| `POST /api/workspace/discovery/refresh` | `Overview.vue` | 管理操作 (Admin) | 阻断云端自动全市场抓取；标的增补改由本机配置驱动 | 保持云端目录稳定 |

---

## 2. 数据提供方准入契约（Provider Admission Contract）

经用户确认，采用 **AKShare + Tushare** 组合，严守以下规范：

| 检查项 | Tushare | AKShare |
|---|---|---|
| **接入类型** | 官方 Token HTTP API (`TushareProvider`) | 开源 Python 适配器 (`AKShareProvider`) |
| **许可状态** | 个人量化研究授权；禁止商用再分发 | 依据上游开源协议及网站访问准则；仅供个人私有工作台展示 |
| **配额与限额** | 积分级频控（如 200~500 次/分）；本地按有界 Universe 批量增量拉取 | 请求加退避与 jitter，防止 IP 封禁 |
| **复权政策** | 前复权 (`qfq`)，除权除息因子严格对齐 | 前复权 (`qfq`) |
| **量额口径** | 成交量：手（100股）；成交额：千元或元（统一转换为元） | 成交量：手；成交额：元 |
| **时间戳质量** | 日线：`trade_date` (YYYYMMDD)；分时：交易日分钟时间戳 | 日线：`date` (YYYY-MM-DD)；分时/快照：含时间字符串 |
| **实时性声明** | 盘中未收盘数据明确标记 `is_partial=true` / `quote_as_of`；盘后收盘数据标记 `settled=true`；**严禁将非实时价格标记为实时** | 同左 |
| **Mock Guard** | `research-live` 环境下 `ALLOW_MOCK_FALLBACK=false`，严禁 Mock 假数据混入真实管道 | 同左 |

---

## 3. 本机数据存储空间与路径规划（Local Budget & Paths）

用户明确将数据根目录设于 **F 盘**（当前空闲约 315 GB）：

* **专用根目录**：`F:\ETF_Data\ETF-Fund-Analysis`
* **目录结构及生命周期**：
  * `config/live.json`：标的 Universe、时区、采集时段与预算限制（非秘密）。
  * `db/research.sqlite3`：本地原始行情、指标历史、预测结果、任务审计日志（WAL 模式，单写者）。预算上限 10 GiB，剩余磁盘低于 2 GiB 自动熔断暂停采集。
  * `cache/provider/`：Provider 响应缓存（7天/1GiB 上限）。
  * `outbox/`：不可变展示包待发送队列（保存最新 3 代，上限 64 MiB）。
  * `logs/`：结构化运行日志（30天/256MiB 上限）。
  * `receipts/`：本地计算与公网发送签名回执（JSON/Hash 链）。
  * `backups/`：SQLite 在线一致性备份（最多保留 3 份，每份约 2 GiB）。

---

## 4. 首期 Universe 规划（30~40 支行业板块代表 ETF）

按用户确认，首期聚焦行业板块代表性标的（兼顾宽基探针）：

1. **端到端探针标的 (2支)**：
   * `510300.SH`（华泰柏瑞沪深300ETF - 宽基锚）
   * `512480.SH`（国联安中证全指半导体ETF - 行业科技锚）
2. **重点行业与板块代表 ETF (首期 32 支)**：
   * **科技 / 半导体 / AI**：`159995.SZ`（芯片ETF）、`512760.SH`（半导体设备）、`515050.SH`（5G通信）、`159819.SZ`（人工智能）、`562500.SH`（机器人）、`159869.SZ`（游戏）
   * **新能源 / 先进制造**：`515790.SH`（光伏ETF）、`159870.SZ`（化工ETF）、`516160.SH`（新能源ETF）、`159865.SZ`（养殖ETF）
   * **医药 / 生物 / 消费**：`512010.SH`（医药ETF）、`159928.SZ`（消费ETF）、`512690.SH`（酒ETF）、`159828.SZ`（医疗ETF）、`512170.SH`（医疗服务）
   * **金融 / 地产 / 周期**：`512880.SH`（证券ETF）、`512800.SH`（银行ETF）、`512200.SH`（房地产ETF）、`512400.SH`（有色金属）、`515220.SH`（煤炭ETF）、`516780.SH`（稀土ETF）
   * **红利 / 央企 / 稳健**：`510880.SH`（红利ETF）、`512950.SH`（央企创新ETF）、`515080.SH`（中证红利低波）
   * **大宗 / 跨境 / 黄金**：`518880.SH`（黄金ETF）、`159934.SZ`（黄金基金）、`159920.SZ`（恒生ETF）、`513050.SH`（中概互联）、`513100.SH`（纳指100）
   * **宽基代表**：`159915.SZ`（创业板ETF）、`588000.SH`（科创50ETF）、`510500.SH`（中证500ETF）

---

## 5. 云端任务迁移与退休规划（Cloud Tasks Migration Matrix）

在完成本地计算与接收端验证（Phase E）并正式切换（Phase F）后，云端调度器任务按以下矩阵退休与保留：

| 任务名称 (Task Name) | 当前状态 | 迁移后状态 | 处置方式 |
|---|---|---|---|
| `refresh_quotes` | 盘中云端拉取 | **退休 (RETIRED)** | 由云端 Worker Guard 阻断；行情由本地 bundle 同步 |
| `fetch_daily_bars` | 盘后云端拉取 | **退休 (RETIRED)** | 本机运行；云端停止向 `daily_bars` 插入新行 |
| `compute_indicators` | 云端计算指标 | **退休 (RETIRED)** | 本机运行；云端停止向 `indicator_snapshots` 写入 |
| `generate_signals` | 云端计算信号 | **退休 (RETIRED)** | 本机运行；云端停止向 `signal_snapshots` 写入 |
| `generate_forecasts` | 云端预测计算 | **退休 (RETIRED)** | 本机运行；云端停止向 `forecast_snapshots` 写入 |
| `refresh_decision_board` | 云端决策板刷新 | **退休 (RETIRED)** | 本机生成顶层快照；云端仅作为静态接收与查询展示 |
| `refresh_market_context` | 市场指数/宽度刷新 | **退休 (RETIRED)** | 由本地 bundle 汇总提供 |
| `sync_instruments` | 标的证券元数据同步 | **保留 (RETAINED)** | 仅保留基础元数据查询，降低执行频次为每周一次 |
| `refresh_news` | 财经新闻 RSS | **保留 (RETAINED)** | 独立运作，不依赖行情 Provider |
| `auth_cleanup` / 数据库维护 | 会话过期清理 | **保留 (RETAINED)** | 核心安全事务，持续运行 |
| `local_bundle_receiver` | 新增接收服务 | **激活 (ACTIVE)** | 校验 HMAC 签名、时间戳、版本及不可变包内容 |

---

## 6. 云端数据库表增长冻结清单（Cloud DB Growth Baseline）

切换完成后，以下数据表停止新增记录（行数增量必须为 0）：
1. `daily_bars`
2. `quote_snapshots`
3. `indicator_snapshots`
4. `forecast_snapshots`
5. `signal_snapshots`
6. `decision_board_snapshots`
7. `decision_board_provisional_inputs`
8. `decision_board_slot_runs`
9. `chan_research_observations` 及相关 revision 表
10. `support_resistance_snapshots` 及相关 revision 表
11. `sector_snapshots`
12. `market_context_snapshots`
13. `task_runs`（与已退休行情任务相关的记录）
14. `provider_audits`（云端行情 Provider 审计记录）

**数据留存政策**：
* 迁移验证通过后，现有历史数据在云端保留 1 个月；
* 1 个月后经 Jovi 再次明确授权，执行有界数据清理，释放云端磁盘。

---

## 7. 契约判定与 Phase A 签字（Sign-off）

* **UI 端点覆盖完整性**：15 项前端依赖全部具有明确的 Bundle Part 映射或私有域保留决策。
* **Provider 许可与单位**：AKShare + Tushare 明确为个人研究使用，单位与复权对齐。
* **本地资源预检**：F 盘具备 315 GB 可用空间，远超 10 GiB 预算红线。
* **云端私有隔离**：持仓、账号、风险计算严格留在云端，Producer 零私有读取权限。

**Phase A 结论：PASS（范围正式封版，允许进入 Phase B 实现）。**

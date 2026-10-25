# 变更记录（CHANGELOG）

本文件是本项目的版本记录入口：每次发布一节，记录版本号、日期、Git 身份、生产镜像、变更摘要、测试收据与未完成门槛。本文件只做记录，不冒充验收通过；资格与验收边界以各节引用的收据文档为准。

## 版本约定

- 版本号四处强制一致，由 `backend/tests/test_release_version.py` 锁定：`pyproject.toml`、`backend/app/core/config.py` 的 `app_version`、`frontend/package.json`、`frontend/package-lock.json`。
- 每次发布新增一节：`## [版本] — 日期`，字段含发布提交、生产镜像、schema、变更分组（后端/前端/调度与数据/文档）、测试证据、部署记录、已知未完成门槛、收据路径。
- 发布提交的精确 SHA 在部署完成后回填于当次发布收据（`docs/audits/RELEASE_*.md`），本文件引用该收据。
- 数据源策略串（如 `daily-batch-v1.0.5-audited-target-retry`）是数据口径版本，与应用版本独立，不随本文件变更。

## [1.0.12] — 2026-10-25

- **触发**：`1a4b665..8e062b7` 独立代码审查（4 项 Important、6 项 Minor）。全部先失败测试后修复；定向 61 项通过。
- **后端（读取链）**：新增展示包读取的三个单一权威——`bundle_expired` / `bundle_is_stale` / `quote_display_state`（`local_display_read.py`）。详情页与自选/持仓定价不再各用一套过期判据（此前整包 2h TTL vs 单报价 600 秒）；详情页现在也按源龄降级，`is_realtime` 不再可能为真。缺 `expires_at` 或不可解析时 fail-closed 返回 stale，不再抛 `KeyError`；`read_instrument_detail` 增加只读时钟注入（与 `read_market_context_view` 同惯例）供确定性测试。
- **后端（诚实标签）**：local_bundle 404 细分为 `local_display_generation_unavailable` / `local_bundle_unavailable` / `local_display_instrument_not_published`；持仓视图未被批次覆盖的行 grade 由「数据异常」改为「无快照」并附 `snapshot_available`；自选返回行级 `unpriced_reason`；`read_overview` 行对象逐行浅拷贝；market-context 读取显式剔除 `items` 而非 `pop`。
- **工具与治理**：`run_local_compute.py` 非零退出在 stdout 追加机器可读哨兵 `{"exit_code":N,"status":"failed"}`（`emit_exit`），防止 `| tail` 掩盖退出码；新增 `config/bundle_identity_registry.json` + `app/workspace/bundle_identity.py` + `scripts/check_bundle_identity.py`（展示包身份登记与部署门禁）；新增 `docs/BUNDLE_IDENTITY_AND_WEEKEND_RUNBOOK.md`（身份推进、周末 board-only 发布、空网站排障顺序）。
- **前端**：新增两个错误码中文文案；自选行级显示「本批次未覆盖 / 暂无报价」。
- **版本纪律**：补录 [1.0.11]/[1.0.10] 两节——此前 `docs/versions/` 有文档但 CHANGELOG 缺节，且四处置版本号停在 1.0.9。
- **发布身份**：提交 `e21bccf7ae3fd3b76156dfda0b953848297ae459`，生产镜像 `sha256:1863c32d…`（基镜像 v1.0.9），公网 health `version=1.0.12` 核验通过；展示包身份保持 `dcffa8e…/041a1286…` 并已登记。收据：`docs/audits/RELEASE_1_0_12_20261025.md`。
- **门禁实测**：全量后端 2686 通过 / 24 跳过 / 0 失败（EXIT=0）；前端 typecheck 0 错误、vitest 228 通过、构建成功；`compileall`/`node --check` 通过；部署前后身份门禁 `approved`；默认读取 `total=34`，详情与定价对同一报价返回相同状态。
- **文档记录**：版本说明 `docs/versions/V1.0.12.md`；审查记录（含逐项处置）`docs/audits/CODE_REVIEW_1A4B665_8E062B7_20261025.md`；发布收据 `docs/audits/RELEASE_1_0_12_20261025.md`；运维手册 `docs/BUNDLE_IDENTITY_AND_WEEKEND_RUNBOOK.md`。

## [1.0.11] — 2026-10-25（补录）

- **来源**：`docs/versions/V1.0.11.md`；合入 `f056c70` / `8e062b7`（动量与计算决策因子第三版：资金预算约束、逐笔账本、Purging、A3.3 影子比对、美股 ETF 实证）。
- **运行时影响**：新增 `backend/app/services/strategy_evaluation/`（contracts / momentum_engine / backtest_harness）但**无运行时调用方**；研究脚本在 `research/`；`research_only=true` / `actionable=false`。生产首次随 1.0.12 承载该目录，不改变调度、Provider 或页面数据。
- **记录缺口**：该版本当时只有版本文档，未写入 CHANGELOG、未升四处置版本号、未单独部署。

## [1.0.10] — 2026-10-25（补录）

- **来源**：`docs/versions/V1.0.10.md`；盘中临时 OHLCV 视图进入只读图表与决策读模型，结算指标仍只由收盘任务生成；数据契约 `cn-fund-shares-cny-v1.0.10-intraday-indicator-view`。
- **发布事实**：该契约与相关代码已包含在 v1.0.9 生产镜像的源码树中（`1c1a500` 树），**未单独以 1.0.10 版本号部署**。补录本节只为消除版本号与文档的断层。

## [1.0.9] — 2026-10-25

- **变更**：本地展示包模式下，自选与搜索改为只读取已批准展示包的报价；包未覆盖的标的不再显示已停更的云端报价。持仓与自选对过期包、异常源时间统一标记历史状态，禁止声称实时。持仓份额与成本没有改动。
- **发布身份**：PR57 Head `1c1a500`、main 合并 `23c20b6` 文件树相同；生产三服务镜像 `sha256:259181a5…`，schema 未变。公网健康 `ok/1.0.9`，默认展示包 34 条；备份与 v1.0.8 回滚入口已核。完整收据：`docs/audits/RELEASE_1_0_9_20261025.md`。
- **验收**：先失败测试；本机完整后端 2652 PASS/24 SKIP、前端 228 PASS、npm audit 0，固定 PR SHA 全部 CI 成功。正常认证用户与本人手机仍待验收；overlay 镜像的 Python 包元数据继承旧版，见发布收据。
- **未完成**：Jovi 暂以收藏列表维护所持基金代码；份额与成本未知，不能据此生成持仓市值或盈亏。正常认证页面与手机验收、交易日自然调度及长期观察分别记录。

## [1.0.8] — 2026-10-25

- **变更分组（后端）**：`portfolio_risk` 在 `workspace_research_source=local_bundle` 模式下不再把云端日线（云端调度停用后冻结于 2026-10-09）当作当前研究数据计算收益相关性：相关性置空、`correlations_reason=local_bundle_cloud_daily_history_stale`、`cloud_history_as_of` 报告云端历史真实截止日、`is_stale=true`、limitations 注入明确说明。database 模式行为不变。来源：2026-10-25 网站空白事件复审（Reader 验收要求 3）；先失败测试后实现（`test_portfolio_risk_local_bundle_never_presents_stale_cloud_history_as_current`）。
- **发布提交**：`7490c76d08fec0938b8e073c5d12a35d39d7ea19`，生产镜像 `sha256:8854b251…`，公网 health `version=1.0.8` 核验通过；详见 `docs/audits/RELEASE_1_0_8_20261025.md`。
- **测试证据**：`backend/tests/test_postdeploy_read_consistency.py` 5 项通过；全量后端 EXIT=0 零失败（`state/pytest_full_1025_v108.log`）；compileall/node --check 通过；部署后默认读取复验 total=34。
- **背景**：当日事件诊断确认展示包默认读取已随 `bundle_1792907023598`（code dcffa8e）恢复 34 条；持仓表为空与云端历史冻结为独立事实。收据：`docs/audits/INCIDENT_20261025_WEEKEND_BLANK_SITE.md`、`docs/audits/RELEASE_1_0_8_20261025.md`。

## [1.0.7] — 2026-10-25

- **发布提交**：`dcffa8ebac1027d174b213915ff78a7e51b99097`，生产镜像 `sha256:d85d40cd…`，公网核验通过；详见 `docs/audits/RELEASE_1_0_7_20261025.md`。基线为 `44bad9c`（= v1.0.6 发布 `6a4aa10` + 发布收据文档）。
- **Schema**：`f0e1d2c3b4a5` 未变，无迁移。

### 调度修复（收盘结算梯度重试）

- **根因（真实台账证据，2026-10-22/23）**：收盘后上游日线渐进发布——15:15 槽 0/34、16:10 槽仅 3–6/34，两个尾盘槽**每个交易日都 FAILED**，当日收盘数据只能等次日 11:40（34/34）才落地；密集快路径槽（14:45–15:00）实测约 125 秒，与 5 分钟间隔无冲突，原"容量协调"问题被数据重新定性。
- **修复**：新增 16:40 / 17:40 晚间结算重试槽（FULL 模式、600 秒截止、stability 验收合同与 closed-session quotes 例外同步扩展）；槽位守卫测试 `test_slot_sets_add_only_1140_and_evening_retries` 显式更新；调度模块 7 份测试文件全绿。
- **配套**：本机任务 Trigger1 轮询窗口 13:50 起 3 小时延至 4.5 小时（覆盖 17:40 槽；触发器起点/间隔不变）。若 16:40 成功，17:40 仍做一次全量再确认（幂等，多花约 4 分钟本机算力）。

### 依赖安全（官方最小修复）

- vitest 4.1.11 → 4.1.12（GHSA-qxg6-89mg-rqv8 / GHSA-xp26-3454-mjgp，仅测试依赖）；esbuild → 0.28.2（GHSA-g7r4-m6w7-qqqr，dev server）。`npm audit --audit-level=low` 现在 **0 漏洞**；前端 228 测试/类型/构建全绿，构建产物哈希不变（`index-YxK4jGbs.js`），对线上运行时零影响。

### 测试证据

- 本提交全量后端 `pytest -q`、`compileall`、`node --check`（收据留档）；调度相关 7 模块与版本锁定测试定向复跑通过。

### 未完成门槛

- 新槽位于周一（2026-10-26）起以真实交易日验证：16:40/17:40 首次实跑、当日结算是否当晚落地、两个真实交易日观察。
- 其余同 1.0.6：真人手机验收、自然触发累计、S8 数据资格、云盘保留策略。

## [1.0.6] — 2026-10-25

- **发布提交**：`6a4aa10b565c289a60c63ea16516f6d7f8c40844`（tree `f9d6bd5b…`），生产镜像 `sha256:69e60fef…`，公网核验通过；详见 `docs/audits/RELEASE_1_0_6_20261025.md`。
- **部署前生产实测身份**（2026-10-25 服务器核实）：API 容器运行 `etf-workspace:optional-panels-1a4b665`（即 main `1a4b665`），非仓库文档此前记载的 `9fe9fe8`；10-16 之后服务器侧已按主题镜像逐次切换（cadence-3d1ab16 → 08b7e6f → d14c12f → 1a4b665）。本版本把生产推进到 PR53/54/55 全链 + v1.0.6。
- **上一个完整发布记录基线**：`9fe9fe8`（1.0.5，2026-10-16，镜像 `93d4e295…`）。本节变更摘要相对该基线（共 43 个提交）。
- **Schema**：`f0e1d2c3b4a5` 未变，`9fe9fe8..2ae17a6` 无新增 Alembic 迁移。

### 后端（接收/展示/可靠性）

- 可信历史接收与有界固定代读取（PR53）：接收历史持久证明、固定 generation 选择器支持 64/65 位与歧义输入拒绝、总览先筛候选再完整校验（`bdf3dd0`/`f89b382`/`fdaf542`）。
- 最新指针缺失时拒绝序号重置（`ee6513a`），历史精确重传可恢复且不提升 latest/previous。
- `market_context.items` 的 `availability` 显式状态校验（PR55）：非法字典/列表在接收前拒绝，存量坏包读取为不可用而不是 500（`14c65a1`/`4476858`）。
- 展示读取按文件身份缓存已验证包，修复 2026-10-22 API OOM（`d14c12f`）。
- 可选面板发布部分市场上下文，当日可选刷新进入快路径并给出诚实原因（`1a4b665`）。
- shadow sync 仅保留约 20 个 slot 包并对旧序列重新确认（`08b7e6f`）。
- 执行身份/调度权限/覆盖证明修复链（`2a85e36`/`7e4daff`/`a537c89`/`f3ab310`/`3d1ab16`/`6fd50d9`）。

### 调度与研究口径（本机计算侧）

- 持久 slot/job 台账、漏跑恢复、同包重传、已结算基准快路径。
- 新增工作日 11:40 午间计算时段（`f197287`），修复午间 11:30 收盘行情在 11:40 时段重传被误拒（`f6839e1`）。
- 预测周期改为明日/3日/7日/一个月/3个月（1/3/7/20/60），输出预测涨幅与上涨概率（`5106ded`/`ef5e603`/`eb51aea`）。
- 官方公司行为入册：516160 合并（权益登记 2024-09-13/除权 2024-09-18）、7 只跳空截断基金历史拆分（`6becc00`/`d7e1ed4`）。

### 前端

- Vite 7.3.7 安全补丁，仅按官方公告最小升级（`e121b13`，GHSA-587h-7wmj-h5pm）。
- 主动"重新读取"不再与自动请求合并，避免读到旧代（`f89b382`）；市场上下文状态/来源时间同代传递展示（PR51/53/54）。
- 版本号升至 1.0.6。

### 文档与验收记录

- PR52 文档收敛（`6fa02a5`/`9aa1f49`）；PR53/54/55 本地验收收据与远端交接文档入册（`df2026b`）；任务台账更新至合并后状态（`2ae17a6`）。

### 测试证据

- PR55 头 `4476858`：Windows 全量 `pytest -q` 2640 PASS/24 SKIP/0 FAIL；Vue 228 PASS、类型/构建、受控认证浏览器 1 PASS、`npm audit --audit-level=high` 通过（仍余 2 moderate/1 low）；同 SHA 两组完整 GitHub CI 及合同检查全 SUCCESS。见 `docs/audits/PR55_LOCAL_ACCEPTANCE_20261024.md`。
- 本发布提交（版本联动+CHANGELOG）复检：`test_release_version.py`、`python -m compileall -q backend/app`、`node --check backend/app/static/app.js`。

### 已知未完成门槛（不因本发布关闭）

- 正常认证用户页面、本人手机/DPR2/标签叠字/不等价价格口径专项、自然定时触发与两个真实交易日、7–14 日 soak。
- 本机任务实测约 6 分 38 秒长于最密 5 分钟 slots 的容量协调。
- 数据资格保持 `UNKNOWN / actionable=false / not_calibrated`；PIT/OOS 与许可单独补证。
- 云盘约 1.13GB 旧数据保留策略未定；Hub 上报自 2026-10-11 起 WinError 10061 未发送。

## [1.0.5] — 2026-10-16（历史基线）

- 发布：`9fe9fe8`（PR48 合 main），生产镜像 `sha256:93d4e295…`（v4 切换），schema `f0e1d2c3b4a5`。
- 内容：本机优先一期——本机真实采集/确定性计算→签名公网 HTTPS 接收→有界展示包消费；R1–R11 修复；最终全量 2241 PASS/23 SKIP。
- 收据：`docs/audits/PHASE1_RELEASE_20261016.md`。
- 后续更正（2026-10-25 核实）：10-16 之后服务器侧已按主题镜像逐次推进至 `1a4b665`，仓库状态文档当时未同步记载。

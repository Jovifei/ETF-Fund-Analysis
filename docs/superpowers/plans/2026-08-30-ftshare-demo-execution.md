# FTShare 接入与安全演示模式实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. 每完成一个任务都要保留测试输出和审查记录；不要把 Mock、候选结果或本地验证写成生产证据。

**Goal:** 在不污染生产数据、不泄漏凭证的前提下，接入受资格门控的 FTShare 只读行情源，并提供完全隔离、可重复验证指标与分级的 DEMO 模式。

**Architecture:** Python/FastAPI 是业务权威。FTShare MCP/Skill 只供 Codex Agent 查询；业务 API 仅通过固定 URL、严格边界和标准 Provider Adapter 访问。FTShare 默认关闭，只有显式启用且资格为 `qualified` 才能进入 AKShare/Tushare 备用链。DEMO 使用进程内 `SQLite + StaticPool` 和专用执行策略，禁止正式数据库、ProviderAudit、TaskRun、Holding、正式报告目录及外网访问。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy、Alembic、Pydantic Settings、httpx (`MockTransport`)、SQLite/PostgreSQL、原生 HTML/CSS/JavaScript、Playwright/webapp-testing、Codex MCP/Skill。

---

## 0. 执行边界与接力状态

**工作目录：** `E:\Claude_allow\Download\ETF-Fund-Analysis-worktrees\ftshare-demo-integration`

**目标分支：** `codex/ftshare-demo-integration`

**主目录：** `E:\project\ETF-Fund-Analysis`。主目录的暂存/脏改动属于 Jovi，不得 reset、clean、stash、覆盖或提交。

**必须先读：** `AGENTS.md`、`STATUS.md`、`HANDOFF.md`、`tasks/lessons.md`、本计划、`docs/superpowers/specs/2026-08-30-ftshare-demo-integration-design.md`，以及对应测试。

**绝对禁止：** 读取或回显任意 `.env`、Token、Cookie、密码、账户号、签名 URL；直接连接或写入生产 PostgreSQL；把第三方 Skill 脚本放进 API 容器；让 LLM/MCP 执行 Shell、数据库写入、行情写入或交易动作。

- [ ] **Step 0.1：确认工作树和 Python，不修改文件。**

```powershell
Set-Location E:\Claude_allow\Download\ETF-Fund-Analysis-worktrees\ftshare-demo-integration
git status --short
git branch --show-current
& E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe --version
```

Expected: 当前分支为 `codex/ftshare-demo-integration`，Python 为 3.12.x；未知数据库、凭证、截图、缓存或其他 Agent 正在修改的文件必须停止并记录。

- [ ] **Step 0.2：先跑聚焦基线。**

```powershell
& E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe -m pytest -q backend/tests/test_ftshare_provider.py backend/tests/test_market_settings.py backend/tests/test_demo_service.py backend/tests/test_demo_mode_js.py backend/tests/test_migration_schema_parity.py
```

Expected: 当前快照的聚焦测试无失败。遇到 Windows SQLite 锁时查明持有 PID，不能删库或杀无关进程。

- [ ] **Step 0.3：在 `tasks/todo.md` 登记本计划链接、Agent、时间和每个命令的真实 exit。** 不记录任何凭证值。

## Task 1：配置 Codex 侧 FTShare MCP 和固定 Skill

**Files:** `C:\Users\Admin\.codex\config.toml`（备份后最小修改）、`C:\Users\Admin\.codex\skills\ftshare-market-data\`、`E:\AI_Tools\Codex\Codex\config\config.toml.before-ftshare-20260830-155554.bak`、`THIRD_PARTY_NOTICES.md`、`docs/FTSHARE_PROVIDER.md`、`tasks/todo.md`。

- [ ] **Step 1.1：备份并只增加固定 MCP 配置。**

```toml
[mcp_servers.ftshare]
url = "https://market.ft.tech/gateway/mcp"
```

Expected: 备份在 `E:\AI_Tools\Codex\Codex\config\`；配置不含 Token。

- [ ] **Step 1.2：验证 MCP 元数据。**

```powershell
codex mcp get ftshare
```

Expected: `enabled: true`、`transport: streamable_http`、URL 精确匹配、无 bearer 环境变量。新开 Codex 任务再验证 `initialize`、`tools/list`、ETF 列表、基础信息、`510300.SH` 日线和现价；每个失败只记录脱敏状态、错误类别、耗时和记录数，不能把 initialize 成功当行情资格。

- [ ] **Step 1.3：安装并固定 Skill。** 使用 `skill-installer` 从真实仓库 `FTShare-Lab/FTShare-skill` 安装 `ftshare-market-data`，固定 commit `cbcfb6283e075fbaa65487a2cb1a75b70c5d4308`。安装前审查 `SKILL.md`、`run.py`、ETF 子路由、域名、下载行为和许可证；不使用 README 中不一致的复数仓库名。

Expected: `C:\Users\Admin\.codex\skills\ftshare-market-data\SKILL.md` 存在；Skill 不进入 API 镜像/业务数据库；代码许可证和 FTShare 数据服务条款分开记录。

- [ ] **Step 1.4：记录工具边界。** MCP/Skill 只有 Agent 查询权限，没有数据库、指标、持仓、交易或 Shell 权限；不得把工具响应写入业务库。

## Task 2：受资格门控的 FTShareProvider

**Files:** `backend/app/providers/ftshare.py`、`backend/app/providers/base.py`、`backend/app/providers/factory.py`、`backend/app/providers/composite.py`、`backend/app/providers/__init__.py`、`backend/app/core/config.py`、`backend/tests/test_ftshare_provider.py`、`scripts/qualify_ftshare.py`、`backend/tests/test_qualify_ftshare.py`、`docs/FTSHARE_PROVIDER.md`、`THIRD_PARTY_NOTICES.md`。

- [ ] **Step 2.1：先写 RED 契约测试。** 使用 `httpx.MockTransport` 固定响应并覆盖：

  - `.XSHG/.XSHE/.XBSE` 映射为 `.SH/.SZ/.BJ`；可选响应代码存在时必须精确匹配请求代码；
  - Skill 的 `etf-ohlcs` 行可无 `symbol/ts_code`、无 `trade_date`，绑定请求代码并从已校验的北京时间 `open_ts_ms/close_ts_ms` 推导同日交易日；可选代码/日期出现时严格核对；
  - `etf-prices` 行可无代码，但必须逐代码请求，多代码不得按返回顺序猜归属；
  - OHLC、正价格、整数有界 shares、非负金额、未来时间、重复日期、日期跨度、页数、记录数、响应字节和截断状态 fail closed；
  - provenance 固定为 `ftshare:list_instruments`、`ftshare:fetch_daily_bars` 或 `ftshare:fetch_spot_quotes`；未资格的 quote 始终 `is_realtime=false` 并带退化原因；
  - `error.code == "UPSTREAM_REJECTED"` 只能通过 allowlisted `safe_code` 进入报告，原始异常不可持久化；
  - `public_composite` 为 `AKShare → FTShare`，`composite` 为 `Tushare → AKShare → FTShare`；新链路永不自动加入 Mock。

Run:

```powershell
& E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe -m pytest -q backend/tests/test_ftshare_provider.py backend/tests/test_qualify_ftshare.py
```

Expected RED：至少有一组新契约输入失败，证明测试先于实现。

- [ ] **Step 2.2：实现固定端点和边界。** 只访问 `/api/v1/market/data/etf-description-all`、`/api/v1/market/data/daec/history/ohlcs`、`/api/v1/market/data/daec/history/prices`；默认地址为 `https://market.ft.tech/gateway`，生产禁止任意 URL；请求带 `Accept: application/json` 与 `X-Client-Name: ft-claw`。流式读取后再 JSON 解析，限制 `FTSHARE_MAX_PAGES`、`FTSHARE_MAX_ROWS`、日期跨度和 `FTSHARE_MAX_RESPONSE_BYTES`。

- [ ] **Step 2.3：实现配置和资格门控。** 默认配置为：

```text
FTSHARE_ENABLED=false
FTSHARE_QUALIFICATION=unverified
FTSHARE_BASE_URL=https://market.ft.tech/gateway
FTSHARE_ALLOW_CUSTOM_BASE_URL=false
FTSHARE_TIMEOUT_SECONDS=20
FTSHARE_MAX_PAGES=10
FTSHARE_MAX_ROWS=10000
FTSHARE_MAX_DATE_SPAN_DAYS=366
FTSHARE_MAX_RESPONSE_BYTES=2000000
```

`build_provider()` 对 direct `ftshare`、`public_composite`、`composite` 都要求 `enabled=true` 且 `qualification=qualified` 才加入 FTShare；无合格 FTShare 时免费档为 AKShare，完整档无 Token 走公开链；不允许 Mock 静默兜底。

- [ ] **Step 2.4：实现资格脚本。** 只读探测 ETF 列表、日线、现价，输出 schema/source/records/延迟/边界/错误类别。失败时 schema、单位、时间戳为 `null/unverified`；只有成功且字段通过校验才记录单位。错误码只能来自结构化 `safe_code`，不得正则扫描异常文本。

Run:

```powershell
& E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe -m pytest -q backend/tests/test_ftshare_provider.py backend/tests/test_qualify_ftshare.py
```

Expected GREEN；Task 2 的规格审查和质量审查均 PASS 后才能进入 Task 3。

## Task 3：隔离 DEMO、状态语义与 120 天根因修复

**Files:** `backend/app/services/demo_service.py`、`backend/app/services/execution_policy.py`、`backend/app/services/task_service.py`、`backend/app/services/market_service.py`、`backend/app/services/market_context_service.py`、`backend/app/services/news_service.py`、`backend/app/main.py`、`backend/app/api/router.py`、`backend/app/api/schemas.py`、`backend/app/scheduler.py`、`backend/app/static/app.js`、`backend/tests/test_demo_service.py`。

- [ ] **Step 3.1：先写隔离和状态 RED 测试。** 断言：

  - 加载前是 `待初始化`；30 个自然日少于 30 根交易日且指标创建为 0；120 天可生成指标；
  - 每个启用标的至少 420 根日线且都有最新有效 IndicatorSnapshot；
  - Provider/抓取失败为 `数据源不可用`，日线不足为 `历史数据不足`，核心指标失败为 `数据异常`，四者互斥；
  - 顶层和嵌套结果均有 `demo=true`、`is_mock=true`、`research_only=true`、`actionable=false`；
  - 生产库 Instruments/Bars/Indicators/Quotes/Signals/Forecasts/ProviderAudit/TaskRun/Holding 行数前后不变，Demo 库 ProviderAudit/TaskRun 为 0；
  - monkeypatch 所有 httpx 请求后 Demo 仍零出网；reset、重复 reset、应用 shutdown 释放 engine/provider 且幂等。

- [ ] **Step 3.2：实现专用执行策略。** Demo 使用 `create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})` 和独立 `Base.metadata.create_all()`；强制 `market_provider="mock"`，关闭 Analysis/LLM、Tushare、FTShare、RSS、OCR、正式报告。正式 `TaskService` 默认继续写 TaskRun/ProviderAudit，只有显式 Demo policy 禁止这些审计行，不能写入后删除。

- [ ] **Step 3.3：实现三个私有 Demo API。**

```text
POST /api/demo/load
GET  /api/demo/bootstrap
POST /api/demo/reset
```

请求体使用 `extra="forbid"` 空模型，不接受 provider URL、工具名、Shell、命令或路径。响应兼容正式 Dashboard，始终带非 actionable 标记；`DemoService.close()` 必须接入 FastAPI lifespan shutdown。

- [ ] **Step 3.4：修复所有默认回看入口。** 普通 `refresh_bars`、UI 等价请求和 scheduler 使用 120 天；完整流水线保持 900 天。用测试锁住，防止任何入口回到 30 天。

Run:

```powershell
& E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe -m pytest -q backend/tests/test_demo_service.py backend/tests/test_market_context.py
```

Expected GREEN，Demo 分级中 `数据异常` 为 0；Task 3 规格/质量审查均 PASS 后才能进入 Task 4。

## Task 4：系统页三档、来源徽标与切换并发安全

**Files:** `backend/app/static/index.html`、`backend/app/static/app.js`、`backend/app/static/app.css`、`backend/app/api/router.py`、`backend/app/api/schemas.py`、`backend/app/services/runtime_service.py`、`backend/tests/test_market_settings.py`、`backend/tests/test_demo_mode_js.py`。

- [ ] **Step 4.1：先写 API/UI RED 测试。** `/api/settings` 只返回 FTShare enabled/qualification/ready/latest probe，不返回 URL/Token/原始错误；`/api/settings/market-probe` 每行包含 `provider/operation/ok/status/records/latency/failure_class/qualification`，请求模型拒绝 URL/tool/Shell。Node 行为测试覆盖 enter/reset/exit、正式写请求在途、SSE、来源徽标。

- [ ] **Step 4.2：实现三档页面和 Token 边界。** 演示=隔离 Mock；免费=AKShare 主、合格 FTShare 备；完整=Tushare 主、公开源和合格 FTShare 备。Token 只进密码框/服务器环境或 runtime secret store，不回显；演示档不修改正式设置。

- [ ] **Step 4.3：实现切换互斥。** 用 `modeGeneration` 丢弃过期响应，`modeTransition` 从点击开始锁正式 mutation；`api()` 追踪所有非 GET、非 `/api/demo/*` 请求的 `formalMutationCount`，在途写请求存在时拒绝进入 Demo；切换时 abort bootstrap/settings/detail/SSE/OCR；进入失败恢复正式轮询/SSE，退出成功只重连一次。成功进入 Demo 后不得被 `finally` 清回正式态。

- [ ] **Step 4.4：实现来源/状态显示和写保护。** 当前 quote 单一来源显示 `AKShare`/`FTShare`/`Tushare`，多个当前成功来源显示 `fallback`，没有当前成功 provenance 显示 `不可用`；正式 Mock 不冒充隔离 DEMO。DEMO 横幅固定显示隔离边界；Demo/切换期间阻断正式任务、持仓、OCR、板块、报告、设置和详情写入；所有 API 数据插入 HTML 前 `escapeHtml()`。

Run:

```powershell
& E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe -m pytest -q backend/tests/test_market_settings.py backend/tests/test_demo_mode_js.py
node --check backend/app/static/app.js
```

Expected GREEN；行为测试必须实际模拟成功、失败、Abort 和并发，不能只检查字符串。

## Task 5：迁移 parity、文档和第三方声明

**Files:** `backend/app/models/entities.py`、`backend/tests/test_migration_schema_parity.py`、`backend/alembic/versions/*.py`（先检查再决定是否修改）、`README.md`、`QUICKSTART.md`、`HANDOFF.md`、`STATUS.md`、`docs/ARCHITECTURE.md`、`docs/IMPLEMENTATION_MATRIX.md`、`docs/FTSHARE_PROVIDER.md`、`THIRD_PARTY_NOTICES.md`、`deploy/.env.local.docker.example`、`deploy/.env.production.example`、`docs/ftshare-qualification-YYYY-MM-DD.json`。

- [ ] **Step 5.1：复现 Alembic 漂移。** 使用工作树内新的临时 SQLite，不触碰生产库：

```powershell
$env:DATABASE_URL='sqlite:///E:/Claude_allow/Download/ETF-Fund-Analysis-worktrees/ftshare-demo-integration/alembic-plan.sqlite3'
& E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe -m alembic upgrade head
& E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe -m alembic current
& E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe -m alembic check
```

Expected: head 为 `2c3d4e5f6a7b`（历史链保留 `d5e6f7a8b9c0`）；若有操作，逐项记录约束、索引、nullable 差异，不得关闭比较器掩盖。

- [ ] **Step 5.2：用最低风险方式修复。** 如果历史迁移语义正确而 ORM 漂移，优先对齐 ORM：保留历史 analysis/review hash constraint 名称、独立 opaque session check、legacy nullable calibration JSON、唯一 `candidate_id` 约束及其查询索引；不要添加只为改名而重写生产数据的新迁移。若真实数据库结构确有差异，才新增可回滚 revision，并覆盖 SQLite/PostgreSQL、旧数据回填和 downgrade。

- [ ] **Step 5.3：补齐文档和报告。** 全部文档统一当前 head `2c3d4e5f6a7b`，并保留 `d5e6f7a8b9c0` 的历史链上下文；说明固定 FTShare endpoint、资格门控、`FTSHARE_MAX_RESPONSE_BYTES`、live probe 当前结果、独立数据服务条款、DEMO 零外网/零正式写入、120 天默认、四种状态文案和 Tushare 明文 Token 债务。失败接口的 schema/单位/时间戳为 `null/unverified`；错误码只能来自结构化 allowlist，不能追写旧证据。

- [ ] **Step 5.4：验证并清理临时库。** 只删除确认位于工作树内且无进程占用的 `alembic-plan.sqlite3`，随后运行：

```powershell
& E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe -m pytest -q backend/tests/test_migration_schema_parity.py
```

Expected: upgrade → downgrade base → re-upgrade → `alembic check` 均 exit 0。

## Task 6：最终验证、资格证据与浏览器 smoke

**Files:** 只允许更新 `tasks/todo.md` 和脱敏 `docs/ftshare-qualification-YYYY-MM-DD.json`；不得修改 `.env`、生产数据库、Token、reports/backups。

- [ ] **Step 6.1：分层验证，避免重复全量。**

```powershell
& E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe -m pytest -q backend/tests/test_ftshare_provider.py backend/tests/test_qualify_ftshare.py backend/tests/test_market_settings.py backend/tests/test_demo_service.py backend/tests/test_demo_mode_js.py backend/tests/test_migration_schema_parity.py
& E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe -m pytest -q
& E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe -m compileall -q backend/app scripts/qualify_ftshare.py
node --check backend/app/static/app.js
git diff --check
& E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe codex/skills/fund-research/scripts/check_no_secrets.py .
```

Expected: focused/full pytest exit 0（允许已有平台 skip），其余命令 exit 0。scanner 命中测试样例时改为短的非凭证值并重跑，不得加白名单掩盖真实值。

- [ ] **Step 6.2：只读 live qualification。**

```powershell
& E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe scripts/qualify_ftshare.py
```

将脱敏 stdout 保存为当天报告；stderr/报告不得包含请求参数、响应原文、Token 或本机路径。若接口拒绝，预期 exit 1、`status=unqualified`、FTShare 仍 disabled/unverified；不准用 Mock 冒充成功。错误码只写精确结构化 `safe_code`。

- [ ] **Step 6.3：隔离浏览器 smoke。** 使用 `webapp-testing`/Playwright，在 `APP_ENV=test`、`MARKET_PROVIDER=mock`、`SCHEDULER_ENABLED=false`、临时 SQLite 和独立端口（例如 18988）启动。先用 `/healthz` 确认身份，再验证 DEMO 横幅、420+ 日线、来源徽标、正式任务/持仓锁定、FTShare 状态、reset/exit 恢复和零外部请求。只清理自己确认的 PID、端口和临时文件。

- [ ] **Step 6.4：双重审查。** 执行 Agent 完成后，派独立规格审查 Agent 和质量/安全审查 Agent；两者均 PASS/APPROVED 才能交付。父 Agent 必须自己复看最终 diff、测试输出和文件边界，不能只接受口头“完成”。

## Task 7：提交和推送（仅在 Jovi 明确授权后）

- [ ] **Step 7.1：提交前边界检查。**

```powershell
git status --short
git diff --stat
git diff --name-only
git ls-files --others --exclude-standard
```

Expected: 只有源码、测试、文档和脱敏报告；没有 `.env`、数据库、日志、截图、缓存、Token 或浏览器 artifacts。

- [ ] **Step 7.2：提交当前功能分支。** 审查后只 add 确认文件，使用：

```powershell
git add -u
git add backend/app/providers/ftshare.py backend/app/services/board_service.py backend/app/services/demo_service.py backend/app/services/execution_policy.py backend/app/services/signal_grade_service.py backend/tests/test_board_service.py backend/tests/test_demo_mode_js.py backend/tests/test_demo_service.py backend/tests/test_ftshare_provider.py backend/tests/test_market_settings.py backend/tests/test_migration_schema_parity.py backend/tests/test_qualify_ftshare.py backend/tests/test_signal_grade.py config/board_catalog.json docs/FTSHARE_PROVIDER.md docs/USER_GUIDE.md docs/ftshare-qualification-2026-08-30.json docs/superpowers/specs/2026-08-30-ftshare-demo-integration-design.md docs/superpowers/specs/2026-08-30-etf-signal-grade-design.md docs/superpowers/plans/2026-08-30-ftshare-demo-execution.md scripts/qualify_ftshare.py tasks/lessons.md
git commit -m "feat: add FTShare provider and isolated demo mode"
```

提交后重新运行最小 smoke，并记录 `git show --stat --oneline HEAD`。不得在主目录提交。

- [ ] **Step 7.3：推送当前分支。**

```powershell
git remote -v
git branch --show-current
git push -u origin codex/ftshare-demo-integration
```

只允许推送当前功能分支；禁止 force-push、主分支推送或把第三方 Skill 源码放进业务仓库。记录远端分支和 commit SHA，不记录凭证。

## 父 Agent 审核清单

1. 查看完整 diff 和未跟踪文件，确认没有 `.env`/DB/Token。
2. 阅读 Provider、factory、DemoService、execution policy、runtime settings、JS mode state machine、migration parity test 的真实实现。
3. 复跑聚焦和全量 pytest、compileall、Node、diff、secret scan；记录 exit/skip 数。
4. 复跑临时 SQLite `upgrade/current/check`，确认没有通过禁用比较器。
5. 检查资格报告失败字段是否保持 `null/unverified`、错误码是否来自结构化 allowlist。
6. 检查 Demo 无 TaskRun/ProviderAudit/外网/正式 Holding/报告写入，并检查 reset/shutdown 资源释放。
7. 检查来源徽标是否基于当前 quote provenance，Demo 切换竞态是否有 Node 行为测试。
8. 规格和质量审查均通过，且 Jovi 授权后才 commit/push；真实 PostgreSQL/Tushare/Paddle/ECS 证据缺失时交付状态写 `PARTIAL`，不能写生产就绪。

## 最终交接输出格式

```text
Implementation: 写 PASS 或 PARTIAL，并说明未获得的真实环境证据
Worktree: E:\Claude_allow\Download\ETF-Fund-Analysis-worktrees\ftshare-demo-integration
Branch: codex/ftshare-demo-integration
Tests: 逐条列出实际命令、通过/跳过/失败数量和 exit code
Alembic: 写当前 head，以及 upgrade/current/check 的实际结果
FTShare live qualification: 写 qualified 或 unqualified、报告绝对路径和 exit code
Demo smoke: 写 PASS 或 PARTIAL、zero-network 结果和生产行数前后差值
Reviews: 写 specification PASS/问题清单和 quality APPROVED/问题清单
Secrets/production writes: 写 not read/not written，或列出具体问题
Commit/push: 写未授权，或写 commit SHA 与远端分支
Open gates: 列出真实 PostgreSQL/Tushare/Paddle/ECS 等尚未取得的证据
```

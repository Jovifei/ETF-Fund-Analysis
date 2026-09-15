# ETF-Fund-Analysis 项目验收与发布测试标准

## 目标和当前状态

目标是把“提交前、合并前、部署前、生产观察后”的验证变成可重复的门禁。任何一层失败都必须停止后续层，先记录失败证据、定位原因、补测试和修复，再从失败层重新执行。

当前事实：v106 固定应用 `c219185e608dc95e4d3e82e8142c08a9590eca94` 已本地复测并部署；scheduler OOM→137 已通过 c219 的阶段顺序和内存释放修复稳定下来。生产数据资格仍未通过，严格 gate 当前退出 3；缺量额、历史断点、目标日指标/预测缺失和非实时报价不能被测试“改绿”。

## 结果状态定义

- `PASS`：命令真实退出 0，报告/计数与预期一致，且没有隐藏 skip。
- `FAIL`：断言失败、退出非 0、版本/来源/日期不一致、资源重启或资格门禁失败。
- `BLOCKED_DATA`：程序按合同拒绝不合格数据；这是安全失败，不是通过。
- `SKIPPED_ENV`：环境条件缺失，例如 Docker、专用 PostgreSQL、Windows symlink privilege；必须写明原因和替代证据，不能归入 PASS。
- `UNKNOWN`：当前证据不存在；不得用旧收据、健康 200 或容器 Up 推断。

## Gate 0：提交身份与工作区保护

目的：确保测试对象就是将要提交/部署的代码。

1. 在独立 worktree 中核对 `git rev-parse HEAD`、`git rev-parse HEAD^{tree}`、基线祖先关系和远端指针。
2. `git status --short --branch` 必须只包含本次明确范围；原工程脏改动、私有配置、数据库、报告不得出现在候选 worktree。
3. 生成 source SHA/tree、前端产物 hash、依赖 inventory；不以 `APP_VERSION` 代替源码身份。
4. 预期：固定 SHA/tree、worktree clean、main/tag 不变。
5. 失败：停止，不 reset/clean/stash/强推，不用旧 ZIP 或旧生产目录替代。

## Gate 1：依赖、静态和安全检查

每个提交必须执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,market,archive]" "duckdb==1.4.5"
\.venv\Scripts\python.exe -m pip freeze > <evidence>\pip-freeze.txt
npm ci --prefix frontend
\.venv\Scripts\python.exe -m compileall -q backend/app scripts
node --check backend/app/static/app.js
\.venv\Scripts\python.exe codex\skills\fund-research\scripts\check_no_secrets.py .
git diff --check
```

Node 版本必须满足 `frontend/package.json` 的 `>=22.18.0`。依赖版本和审计输出进入 evidence；`npm audit --audit-level=high` 必须退出 0，low/moderate 需记录包、路径和是否开发依赖，不执行未经批准的 `--force` 升级。

## Gate 2：后端单元、契约和任务状态

隔离环境必须显式设置 `APP_ENV=test`、专用临时 SQLite、`AUTH_ENABLED=false`、`MARKET_PROVIDER=mock`；测试不得读取生产 `.env` 或真实数据库。

```powershell
\.venv\Scripts\python.exe -m pytest -q --junitxml=<evidence>\pytest-full.xml
\.venv\Scripts\python.exe -m pytest backend/tests/test_postdeploy*.py -q --junitxml=<evidence>\postdeploy.xml
node --test backend/app/static/*.test.js
```

通过条件：0 failures/errors；所有 skip 有明确定义。重点断言：

- TaskRun 的 `succeeded/partial/failed/cancelled` 与结果覆盖一致；失败下游可重试。
- 目标交易日、日期时区、未来源时间和 snapshot/config/schema/input hash 一致。
- 指标/预测缺失为 null/blocked，不转换成 0，不生成平坦未来蜡烛。
- 决策板 `数据异常` 是独立分组，分组总数等于 rows，actionable 仍为 false。
- scheduler 收盘顺序先完成核心决策板/报告，再执行慢的可选板块；阶段摘要不泄漏环境、凭据和原始异常。
- 完整历史 hash 与序列化旧合同一致，不能裁成 250/600 根来伪造内存优化。

## Gate 3：数据源、字段、目标日和资格

数据测试分成“可以展示”与“可以发布/可操作”两套，二者不能混为一谈。

### 3.1 Provider 合同

- 每次调用记录 provider、operation、source time、fetch time、耗时、记录数、失败原因。
- Provider fixture 覆盖东财成功、Sina 价格回退、Tushare unsupported、超时和空响应。
- OHLC 必须有限且满足 `low <= open/close <= high`。
- `volume/amount` 未经单位合同认证时保持 NULL；禁止填 0、乘系数或用均价比值认证绝对单位。
- `adjust`、复权/公司行动和价格基准必须明确；未知或混用直接阻断。

### 3.2 目标交易日覆盖

以实际启用 ETF/LOF 集合为分母，不硬编码 35。每个标的检查：

| 层 | 必须通过 |
|---|---|
| 日线 | 目标日存在、源日期非未来、OHLC 合法 |
| 量额 | 发布 gate 要求量额完整；price-only 只能 research |
| 指标 | 目标日、版本、config hash、feature schema、input hash 一致 |
| 预测 | 1/3/5/10 每个期限目标日覆盖，空结果不可补齐 |
| 报价 | source time、fetched_at 分离；实时 gate 要求 realtime + timestamp_verified |
| 决策板 | 生成时间晚于本次输入链路，snapshot freshness/target 合同一致 |

执行只读生产 freshness gate：

```powershell
\.venv\Scripts\python.exe scripts/production_data_gate.py `
  --input <freshness_by_instrument.json> `
  --output <gate-result.json> `
  --require-realtime
```

退出 0 才能标记 release data gate 通过；退出 3 表示实际数据阻断，必须保留阻断清单并停止发布。退出 3 不能靠重试、刷新页面、修改版本标签或删除异常行消除。

### 3.3 真实副本审计

在已备份副本执行：

```powershell
\.venv\Scripts\python.exe scripts/audit_research_inputs.py `
  --codes 510300.SH 512480.SH 588200.SH `
  --output <new-evidence>\audit_research_inputs.json `
  --fail-on-blockers
```

退出 3 是可预期的数据阻断；必须检查每个标的的 blockers、indicator blockers、source、target date、单位、断点和完整 hash。不得把旧副本结果当当前生产事实，也不得直接改生产数据库。

## Gate 4：数据库和迁移

```powershell
$env:DATABASE_URL="sqlite:///...\\migration.sqlite3"
\.venv\Scripts\python.exe -m alembic upgrade head
\.venv\Scripts\python.exe -m alembic check
\.venv\Scripts\python.exe -m alembic current
```

必须得到唯一 head `d40609090002`，并保存退出码。专用 PostgreSQL 16 使用一次性测试库和 `TEST_POSTGRES_URL`；缺少 Docker/URL 时记录 `SKIPPED_ENV`，不能用生产库恢复或 HTTP 200 代替。

## Gate 5：前端、页面和响应式

```powershell
npm run test --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
npm audit --audit-level=high --prefix frontend
```

普通和认证 Playwright 必须使用目标 venv 的 Python webServer：

```powershell
$env:PATH="$PWD\\..\\.venv\\Scripts;$env:PATH"
npx playwright test --config playwright.config.ts
npx playwright test --config playwright.auth.config.ts
```

视口矩阵：390×844、430×932、768×1024、1024×768、1440×1050、1920×1080、3840×1920。每个页面检查：

- `body.scrollWidth <= viewport.width`；允许横向滚动的宽表必须限制在自己的 `.table-scroll`，不能把整页撑宽。
- 侧栏在桌面/平板/手机分别为展开、紧凑或抽屉；抽屉可打开、关闭、Esc 关闭、焦点不丢失。
- 主内容宽度随视口伸缩，不能因固定 `max-width` 在超宽屏留下大片空白。
- 搜索框、工具栏、标题按钮在 390/430 宽度换行且不遮挡。
- K 线容器宽度、浏览器 zoom、全屏、Esc、滚轮缩放和拖拽后都触发 chart resize；缺分钟线仍回退日线并显示原因。
- Matrix 在手机保留代码/名称、核心状态、价格、当日涨跌和数据状态；完整指标通过详情页查看。
- 数据异常行必须能看到 `data_status` 与 `grade_reason`，不只显示无解释的“数据异常”。
- 普通/认证页面 API、缓存、导航、持仓预览、研究候选和退出登录回归通过；页面不调用模型、不自动写持仓。

## Gate 6：Windows/E 盘归档和 Bridge

必须实际运行：

```powershell
\.venv\Scripts\python.exe scripts/archive_local.py --help
\.venv\Scripts\python.exe -m pytest backend/tests/test_postdeploy_archive.py -q
```

一次性私有 scratch 目录验证 `request → JSONL/Parquet → respond → verify`。检查 NTFS ACL、symlink/junction 拒绝、大小/压缩/JSON 重复键、manifest/hash、NULL 量额和过期 nonce。签名只证明字节/密钥持有，不证明行情单位、复权、新鲜度或资格。禁止开放 E 盘目录、同步运行 SQLite、自动删除云端历史。

Bridge/ACL 测试不能替代本人真实登录；未知 Codex 版本、未配对、未确认费用或无真实产物保持未通过。

## Gate 7：部署前和部署后

部署前必须同时具备：

1. 固定 SHA/tree、前端产物 hash、依赖 inventory、迁移 head。
2. 数据库 gzip 备份 SHA-256、权限 600、恢复路径和旧 Compose 回滚文件。
3. API/worker/scheduler 三者源码挂载、镜像 ID、开关和数据库目标一致。
4. 全量测试、条件测试跳过原因和 release data gate 状态。
5. 变更范围、停止条件和回滚命令已写入收据。

部署后只读检查：

- API/worker/scheduler healthy，scheduler 观察至少覆盖一次核心批次；restart/oom 不增长。
- `/api/health`、根页面、静态 JS/CSS、认证边界返回预期。
- TaskRun、provider audit、目标日期覆盖和决策 snapshot_id 与部署 SHA/数据库 head 对齐。
- 任一健康、资源、数据、页面或回滚检查失败立即回滚，不能静默降级。

## 每次提交的固定顺序

1. 读取 `AGENTS.md`、`STATUS.md`、`HANDOFF.md` 和本标准。
2. 创建隔离 worktree，记录 base/HEAD/tree，保护原工程。
3. 先写失败测试并确认 RED；再做最小代码改动。
4. 执行受影响聚焦测试，再执行 Gate 1–6；保存退出码/JUnit/截图/manifest。
5. `git diff --check`、密钥扫描、工作区范围检查；未通过禁止 commit。
6. commit 后重新运行受影响 gate；推送前核对 commit/tree/远端指针。
7. 部署前必须得到独立备份和回滚证据；生产切换后再跑 Gate 7。
8. 任一 `FAIL`、`BLOCKED_DATA` 或 `UNKNOWN` 未有批准处置时，状态为 `blocked`，不得标记完成。

## 停止条件

- 源码、镜像、前端或数据库不一致。
- scheduler OOM/137/restart 增长，或没有足够事件证据。
- 目标日覆盖、单位、复权、量额、指标、预测或报价资格缺失。
- 普通/认证浏览器、迁移、密钥扫描、数据 gate 任一失败。
- 条件测试被跳过却没有独立证据。
- 需要修改生产数据库、猜单位、删除异常、降低资格门禁、调用付费模型或强行应用被拦截写入。

## 证据命名

每轮使用新的私有目录 `E:\Claude_allow\Download\<project>-evidence-YYYYMMDD[-n]`，至少包含：`PLAN.md`、`pip-freeze.txt`、JUnit、Playwright summary/截图、migration current/check、data gate、source manifest、部署/回滚收据和最终 `DECISION.md`。不保存凭据、Cookie、签名 URL、完整环境变量或真实持仓。

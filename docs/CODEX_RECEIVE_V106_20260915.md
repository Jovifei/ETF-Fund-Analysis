# 本地 Codex 接收 Prompt：v106 后续修复

你接收的是 ETF-Fund-Analysis 现有工作站的增量修复，不是重建产品。先阅读本文件和固定验收收据，再执行隔离接收与本机验证。生产服务器、main、标签和付费 AI 不在本次接收授权内。

## 1. 固定身份与事实边界

- 仓库：`https://github.com/Jovifei/ETF-Fund-Analysis.git`
- 分支：`fix/v106-postdeploy-20260914`
- 现有 PR：#34，目标 `fix/v105-audit-blockers-20260912`。
- 本轮接续基线：`e44e9deb085579f2fe69c3461fda53d0f4ffbe93`。
- 固定接收提交：`c219185e608dc95e4d3e82e8142c08a9590eca94`。
- 固定源码树：`c5d13ef4f92d850e58840e66f7447f3d4247ec0c`。
- 应用/前端版本仍是 `1.0.5`；v106 是分支批次名，不能当作已发布 v1.0.6。
- Alembic 唯一 head 仍为 `d40609090002`，本轮没有新增迁移。
- 用户 2026-09-14 生产收据对应 `c87cfa1df906eee902c1e37509c63cf847d29209`；不要推定本轮代码已经上线。

原工程 `E:\project\ETF-Fund-Analysis` 可能有用户脏修改。原接收目录 `E:\Claude_allow\Download\ETF-Fund-Analysis-v105-audit-receive-20260913` 和原私有配置、数据库、账户、持仓、自选、报告全部保留。本次用全新的独立目录。

## 2. 接收规则

只读盘点原工程路径、remote、HEAD 和脏文件名，不输出 .env 或凭据内容。禁止 reset、clean、stash、强推、覆盖已有目录或原数据库。以下是新目录示例；路径存在时停止并选另一个全新目录，不清空。

```powershell
$ErrorActionPreference = 'Stop'
$Repo = 'https://github.com/Jovifei/ETF-Fund-Analysis.git'
$Branch = 'fix/v106-postdeploy-20260914'
$Commit = 'c219185e608dc95e4d3e82e8142c08a9590eca94'
$Base = 'e44e9deb085579f2fe69c3461fda53d0f4ffbe93'
$Receive = 'E:\Claude_allow\Download\ETF-Fund-Analysis-v106-receive-20260915'
if (Test-Path -LiteralPath $Receive) { throw '接收目录已存在，禁止覆盖' }
git clone --branch $Branch --single-branch $Repo $Receive
if ($LASTEXITCODE -ne 0) { throw 'clone 失败' }
git -C $Receive cat-file -e "${Commit}^{commit}"
if ($LASTEXITCODE -ne 0) { throw '固定提交不存在' }
git -C $Receive merge-base --is-ancestor $Base $Commit
if ($LASTEXITCODE -ne 0) { throw '基线祖先关系不符' }
git -C $Receive switch --detach $Commit
if ($LASTEXITCODE -ne 0) { throw '固定提交接收失败' }
$Tree = (git -C $Receive rev-parse 'HEAD^{tree}').Trim()
if ($Tree -ne 'c5d13ef4f92d850e58840e66f7447f3d4247ec0c') { throw '源码树不符' }
git -C $Receive status --short
```

后续文档提交不改变被验收应用。若远端分支已继续前进，先阅读差异，不把后来的应用代码算作本次已通过。文档可以从对应文档提交只读查看，不将整分支覆盖固定代码。

阅读顺序：AGENTS.md → 本次 POSTDEPLOY_ACCEPTANCE_20260915.md → POSTDEPLOY_CLOSURE_20260915.md → 本 Prompt → 原审核报告。STATUS/HANDOFF 中更早日期的状态按历史记录理解。

## 3. 环境与隔离复测

用独立 Python 3.12 环境和 Node 22.18+；按锁文件 `npm ci`，不要随意升级依赖。常规 Python 依赖不是完整锁定清单，必须保存实际 pip inventory；Parquet 复核使用明确验证过的 DuckDB 1.4.5。

所有测试使用一次性 scratch/ci 数据库。先检查环境目标，任何 pytest/seed/Alembic 降级都不能连真实库。真实私有配置不得为了方便整体导入测试进程。数据库 URL、Token、Cookie、主密钥、模型登录文件均不得回显。

```powershell
Set-Location $Receive
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'venv 创建失败' }
$Python = Join-Path $Receive '.venv\Scripts\python.exe'
& $Python -m pip install -e '.[dev,market,archive]' 'duckdb==1.4.5'
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败；按实际平台记录，禁止降级门禁' }
```

在仓库外新建本人私有证据目录；为测试进程显式选择 APP_ENV=test、MARKET_PROVIDER=mock 和专用临时 SQLite。AUTH_ENABLED=false 仅用于这套隔离测试，不得写入正式配置。随后按当前 .github/workflows 执行并逐条保存退出码：

- 后端全量 pytest，产生 JUnit；新增 `test_postdeploy*.py` 单独复跑，归档测试必须有实际 DuckDB。
- compileall；所有现有 JS 语法检查；旧 JS 测试；新增 `decision_board_embed.test.js`。
- Vue test、typecheck、build、npm audit 高危门禁。
- 临时 SQLite Alembic upgrade/check/current；不得把真实库迁移当作条件测试的替代。
- 普通真实 HTTP Playwright、独立认证 Playwright，两套都要执行。webServer 使用目标 venv，不用系统 Python 误跑。
- 专用 PostgreSQL 16：沿用 audit-platforms.yml 的临时库、TEST_POSTGRES_URL 和测试命令；不得指向生产或含真实数据的恢复库。
- Windows：既有 Bridge/ACL 以及新增归档 NTFS/Parquet 测试。云端 Windows 通过不能证明用户 E 盘实际 ACL 合格。
- git diff --check、密钥扫描、构建产物与依赖 inventory。

Docker、PostgreSQL、ShellCheck/WSL 或浏览器依赖不可用时，明确记录未执行；保留已获得的其他结果，不写成“全平台通过”。不要删除断言或增加重试隐藏失败。

## 4. 必须复核的行为

1. 上游日线/指标/预测完成后，独立失败的决策板与报告仍会被补跑；新输入在同一天到达能使下游完成凭证失效。资格受阻的标的仍应出现在新的受限研究快照中。
2. 各期限 API 都包含数据异常 counts，总分组数等于 rows。空预测不生成平坦未来蜡烛，预测日期不匹配不重新锚定到最新价格。
3. 新抓取的旧源报价不能成为今日实时。总览、详情分别展示日线、指标、预测、决策板的日期；旧版本/config/schema 不作为当前有效结果。
4. 支撑压力静态 self 错误已修复；读取不能因缺快照偷偷写库。未知量额不填零后宣称完整；原始价格展示不升级资格。
5. 月度价格研究拒绝未知价格基准和未解释断点；历史同日修订或配置改变会让旧缓存失效。价格-only 研究不强制补造量额。该缓存不等于经过 OOS 校准。
6. lower_break 不算上破；null/空串/布尔值不当作 KDJ/RSI 的零值；真实数值 0 仍可显示。有缓存并请求失败时同时保留旧数据和连接异常。
7. 数据健康页按目标交易日显示覆盖数/缺口，失败摘要不泄漏原始错误。注意下面的两个未提交接线点，不能把健康页通过算作全部 worker 摘要完成。
8. 流式 history digest 必须与旧序列化字节哈希一致；400/600 根以前的历史修改仍能改变完整输入哈希。不得用裁成 250 根替代内存优化。

## 5. 真实数据与 runtime 验收

先备份原数据库和私有报告，并恢复到副本验证完整性。现有账户不得 init 或重新 bootstrap 管理员。加载副本的私有配置后运行既有只读 `audit_research_inputs.py`，保持结果不覆盖旧报告：退出 3 是确有阻断，不是应该无条件重试的错误；退出 0 也不授予交易资格。

对 510300.SH、512480.SH、588200.SH 记录来源、目标日期、单位、价格断点、缺量额、指标版本以及完整输入 lineage。真实来源认证和拆分调整序列仍未完成；禁止猜系数、删异常记录或手改版本标签。

scheduler 的退出 137/重启 80 次属于 9 月 14 日现场记录，本轮没有重登生产核实根因。已有合法主机只读权限时，可对明确的 ETF 容器名使用 `scripts/runtime_diagnostics.py --container <name>`，并对齐 stage 日志、OOMKilled、cgroup/峰值 RSS、实际内存限制与宿主机事件。无授权时保持“现场待验”。不要采集含环境变量/凭据的完整 docker inspect，不关闭 OOM/安全限制来制造通过。

本地持久副本服务只监听回环地址、继续数据库认证、同代码同库；生产开关、采集预算与服务切换需另行授权。没有授权时仅用隔离时钟和 Provider 夹具验证收盘恢复。

## 6. E 盘归档范围

已提交 `archive_protocol.py`、`archive_store.py`、`archive_parquet.py`、`scripts/archive_local.py`。先运行 `--help` 并执行隔离样本：request → JSONL/Parquet 筛选 → respond → verify。根目录和输入文件必须私有；已有宽 ACL 目录会被拒绝，不会自动修权。

归档请求有单标的、日期范围、最多 5000 行、到期时间、nonce；包保留 source/adjust/NULL，有压缩及解压大小限制。签名只证明字节与密钥持有，不证明来源单位/复权/行情新鲜度。`qualification=not_asserted`、`actionable=false` 不变。

只使用隔离一次性测试密钥运行测试；不得把测试示例密钥用于真实包。真实归档密钥必须独立私有配置，不读取/复制 Codex auth.json、AI API 主密钥或行情 Token。

尚未开发在线 owner 请求队列、本地主动 HTTPS 轮询、服务器消费回执/防重放账本、TTL 缓存和图表按需回取。不能把离线验证器当作线上防重放模块，不能开放 E 盘目录，不能自动搬走/删除云端日线。

## 7. 未提交点及禁止混用

本轮针对 worker.py 与 workspace/api.py 的整文件 GitHub 写入被平台安全检查拦截，未绕过；两个文件在固定远端提交保持基线内容。没有在交接包中提供自动应用这些被拦截修改的脚本。

- worker 的 bounded_step_summary 还未接入新 task_summary；工作站 TaskProgress 的 ETF 失败原因仍可能被省略，尽管 data-health 已直接使用新摘要。
- research-outlook 路由尚未显式传入依赖注入 settings；read 的默认 get_settings 保持工作，但依赖覆盖环境的配置一致性需另行审查。

这些是待审问题，不能当作已经修好；不通过其他 API、编码、CI 写仓库或运行时替换规避拦截。先独立审查与适当授权，再决定后续变更。远端固定提交的验证收据是本次接收权威，不能用本地包含待审改动的中间测试结果替代。

## 8. 交付本地结果

输出固定 SHA/tree、远端是否前进、每条命令及退出码、各套测试计数/跳过理由、原库副本审核、必要的只读 runtime 证据、前后端日期对照、E 盘归档 NTFS 结果、本地 URL 和所有未完成项。若产生后续修复，单独分支/小提交/完整复测，不自动合并 main、改标签或部署公网。

# R1 接收验收与下一阶段交接（2026-09-22）

## 0. 交付边界与固定身份

本次交付是已提交的 R1 单位证据绑定修复及其验收，不是用户提出的五个方向全部完成，也不是生产部署批准。本文件后续于应用提交，属于纯文档；运行/复测固定应用 SHA，不用文档分支头替代。

- 仓库：Jovifei/ETF-Fund-Analysis。
- 接收分支：codex/v106-scheduler-oom-fix。
- 固定应用：bb54d0e2813e7c5f17ae0d65e94f1b87ee04914c。
- 固定应用树：2cdb7f855ba89567c4c153664fc2bf7268a48dd3。
- 直接父提交/本次读取的 main：825767cdd5e73343eede52f1306d549074f68e03。
- 迁移 head：e609200001；R1 无新增迁移。
- 源码中的 Python/前端包版本均为 1.0.5；不要用生产回执中的 1.0.8、数据契约的 1.0.10 或 API_VERSION 判断源码身份。
- 已下载固定应用的 CI 源码归档，重建 Git tree，结果与上述树一致。
- 本次续接未读取当前生产数据库、未登录服务器、未修改 main、未部署、未调用模型。

根 STATUS.md/HANDOFF.md 仍有旧部署和旧迁移描述；历史事实不能当当前事实。上述身份以实际提交、CI manifest 和本次读取为依据。用户本机/服务器最近状态以新的现场证据核实，本文件不将其聊天回执当成独立复测。

## 1. R1 已修复内容

应用提交主要修改 backend/app/services/unit_evidence_service.py，并新增 backend/tests/test_review_unit_binding.py。

1. 原来的重新计算路径未保留已存证据的拒绝状态，可能把记录时已拒绝的证据重新判为认证；现在显式拒绝 stored_evidence_rejected。
2. 读取时不再只信任 quality_hash。实际来源、收盘价、成交量和成交额仍须与证据绑定；即使导入程序漏更新 hash，也会拒绝不匹配数据。
3. 记录和读取均检查标的身份，另一只 ETF 的相同数值不能复用认证。
4. 统一整数/浮点及转换后数值的证据哈希表达，减少数据库 Float 往返造成的误拒绝。
5. 缺主源、缺同日独立源、Provider 失败、范围错误或认证拒绝，明确进入失败摘要；零认证不再返回 succeeded。

R1 不生成新行情，不修改原始 OHLCV，不补零，不推断单位，不授予实时或 actionable 资格。旧证据被重新判为不合格时，必须保留原因；不能更新 certified、hash 或理由字段把旧记录重新刷绿。需要新证据时走另行获批的采集/重算任务。

## 2. 已核验测试证据（同一应用 SHA）

| 项目 | 结果与依据 |
| --- | --- |
| CI 全量后端 | JUnit 1203 项，1200 通过，3 条条件跳过，0 failures/errors；CI 安装 dev,market，未使用之前本地的单例 deselect |
| R1 新回归 | test_review_unit_binding.py 的 7 个参数化/独立用例均通过 |
| 工作站后端 | JUnit 267 项，266 通过，1 条 Windows 条件跳过 |
| 响应式 | responsive-results.json：16 expected，0 unexpected、0 skipped、0 flaky |
| Vue/typecheck/build、普通/认证 HTTP | workspace-ci 对应步骤均 completed/success；此处不拿旧版本计数替代新日志 |
| Windows/专用 PostgreSQL | audit-platforms 的 windows-bridge、postgres-contracts 对应步骤均 success |
| DuckDB/Windows 归档 | postdeploy-ci 的 followup-contracts、windows-archive 均 success |
| 编译、JS、扫描、Alembic、ShellCheck、Compose、镜像和 smoke | ci 全部对应步骤 success，无把 skipped 当通过 |
| 本次续接本地复核 | 从远端归档提取的固定树重新执行 test_review_unit_binding.py + test_unit_evidence_store.py，12/12；compileall 和密钥扫描通过 |

全量中的三条跳过分别为 Windows NTFS、未配置 TEST_POSTGRES_URL、未安装可选 DuckDB；独立平台任务有对应路径证据，但不能说用户 Windows/生产库已复测。本次本地 12 项使用预装依赖的隔离环境，不是重新跑完整 CI；初次 venv 缺 pytest 的环境失败保留在本地证据中。

同 SHA 工作流：

- ci #739：https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/35672732775
- workspace-ci #262：https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/35672732804
- audit-platforms #129：https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/35672732786
- postdeploy-ci：https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/35672732771
- acceptance-tooling #5：https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/35672732782

已检查的归档：workspace artifact 10671627392，SHA-256 a2089b45afa95f5261f635a757d5c87a8362d03591ac7c9d7957cdad431c2722；CI artifact 10671024978，SHA-256 2c5f4102d5252ce657c0765fec8a5bb7603595212bb6f1fec97c6fc74c9794b2。

release-inventory.json 仍为 registry_image_digest=null、release_inventory_complete=false、data_qualification=not_asserted、production_deployed=false。成功构建的 CI 镜像不是已经发布到生产的镜像。

## 3. 本地 Codex：先接收，不继续扩大改动

本批目标：固定树核验、隔离复测、经授权的数据副本重新审核、输出接收决定。不要自动合并 main 或部署；不要把本批误称为详情、决策和缠论已修好。

### 3.1 保护与接收

原工作区据用户回执已经 clean；本次仍用新目录，避免覆盖之后的修改。不复制 .env，不执行 reset/clean/stash，不开启 Provider/付费模型。

PowerShell 示例（每步非零立即停止并保留日志）：

```powershell
$ErrorActionPreference = 'Stop'
$App = 'bb54d0e2813e7c5f17ae0d65e94f1b87ee04914c'
$Base = '825767cdd5e73343eede52f1306d549074f68e03'
$Tree = '2cdb7f855ba89567c4c153664fc2bf7268a48dd3'
$Root = 'E:\Claude_allow\Download\ETF-R1-receive-20260922'
$Evidence = 'E:\Claude_allow\Download\ETF-R1-evidence-20260922'
if ((Test-Path $Root) -or (Test-Path $Evidence)) { throw 'Use fresh directories; do not overwrite.' }
New-Item -ItemType Directory -Path $Evidence | Out-Null
git -c core.autocrlf=false clone --no-checkout --branch codex/v106-scheduler-oom-fix https://github.com/Jovifei/ETF-Fund-Analysis.git $Root
if ($LASTEXITCODE -ne 0) { throw 'clone failed' }
Set-Location $Root
git config core.autocrlf false
git switch --detach $App
if ($LASTEXITCODE -ne 0) { throw 'checkout failed' }
if ((git rev-parse HEAD).Trim() -ne $App) { throw 'SHA mismatch' }
if ((git rev-parse 'HEAD^{tree}').Trim() -ne $Tree) { throw 'tree mismatch' }
git merge-base --is-ancestor $Base $App
if ($LASTEXITCODE -ne 0) { throw 'ancestor mismatch' }
git status --short --branch
git diff --check
```

接收从附件或文档提交读取本文件；切换固定应用后本文件不存在是正常的。应用提交与文档提交分开。

### 3.2 隔离依赖和自动验收

Python 3.12、Node >=22.18.0；记录实际版本与依赖。按锁文件安装，不执行 audit fix --force。所有测试只指向本批临时数据库，不读取原私有配置。

```powershell
py -3.12 -m venv .venv
$Py = Join-Path $Root '.venv\Scripts\python.exe'
& $Py -m pip install -e '.[dev,market,archive]'
npm ci --ignore-scripts --prefix frontend
& $Py -m pytest backend/tests/test_review_unit_binding.py backend/tests/test_unit_evidence_store.py -q "--junitxml=$Evidence\r1.xml"
& $Py -m pytest -q "--junitxml=$Evidence\pytest-full.xml"
& $Py -m compileall -q backend/app scripts
& $Py codex/skills/fund-research/scripts/check_no_secrets.py
node --test backend/app/static/*.test.js
npm run test --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
npm audit --audit-level=high --prefix frontend
git diff --check
```

以上各命令须逐条核对退出码，不可整段最后一条成功掩盖前面失败。低/中危依赖风险也须记录包和使用路径。Playwright 的 webServer 必须使用本批 venv Python，先把其 Scripts 目录放入当前子会话 PATH，再于 frontend 顺序运行普通、认证、responsive 三份配置。安装浏览器失败为环境阻断，不能删除用例；浏览器用临时账户/模拟行情，不使用生产会话。

专用 SQLite 执行 Alembic upgrade/check/current；head 应为 e609200001。Windows/归档和 PostgreSQL 条件测试按仓库 workflow 实际命令执行；没有 Docker/专用测试库就写 SKIPPED_ENV 和同 SHA 替代证据，禁止借用生产库。

### 3.3 真数据副本审核

自动测试与真实资格分开记录。需要真实副本的访问授权与只读连接后，逐标的重跑 certify_stored_history/read-only audit，记录 accepted/rejected/unknown 的数量及理由。比较 R1 前后证据判定，不修改 certified/hash，不把“上轮140条认证”当新版本结论。

旧证据字段或哈希不匹配，保留拒绝并安排受审计重新采集；本批不自行调用 Provider。旧 freshness JSON 没有新合同字段时记录 UNKNOWN，不补造 metadata。生产访问/采集/重算不在本次默认授权中。

### 3.4 接收输出

输出 RECEIPT_R1_20260922.md 和 DECISION.md，包含完整 SHA/tree、每套测试计数及跳过、首次失败与重跑、依赖差异、证据拒绝差异、未完成清单。结论分别为：代码接收、真实数据资格、生产部署；不得用一个 PASS 覆盖三者。临时服务退出后不把其地址写成持久可用预览。

## 4. 后续五个方向（未完成，不纳入 R1 通过范围）

### R2：更新及时性与盘中/收盘一致性，优先级 P0

位置：frontend/src/views/Detail.vue、frontend/src/lib/query.ts、backend/app/workspace/read_model.py::instrument_detail/chart_data、DecisionBoardService::_provisional_status，以及 scheduler 的阶段记录。

已静态确认：Overview 有60秒可见页刷新，Detail/useQuery 没有等价定时刷新；详情直接相信旧决策行中的 provisional.used_for_derived_values，而图表重新按当前时间校验；chart_data 将临时K线直接追加，未在追加点防止同一交易日与正式K线并存。

待实现/验收：共享只读刷新生命周期；旧请求取消；后台暂停/回到页面更新；源时间、抓取时间、指标基准日、发布时刻分列；临时记录过期、跨日、同日正式记录已入库时不继续冒充当前指标；固定时钟负例验证。上述静态风险尚未逐项完成生产复现，不宣称已经修复。

### R3：基金详情无数据与决策可解释性，优先级 P0/P1

位置：workspace/api.py 的 instruments/{code} 与 chart 路由、read_model、Detail.vue、OriginalDecisionBoard.vue、HistoryLoader.vue。

先逐一记录点击代码、HTTP 状态、enabled/kind、持久记录数量和返回原因；未提供的新截图不能被当作已读到。区分目录未同步、无历史、无分钟线、计算资格受阻和真实服务错误，避免统一空白或统一“数据异常”。现有研究 grade 应显示依据、失效条件、数据日期、支撑压力及与上次变化，和 actionable=false 同时明确展示；不以打开操作开关解决“没有决策”。

验收：35只当前池按实际分母逐页检查；池外目录项、空库、缺分钟、401/404/5xx、无预测分别覆盖；无数据有明确原因和安全的恢复入口；GET 不触发抓取/模型/数据库写入。

### R4：统一支撑压力与缠论绘图，优先级 P1

位置：workspace/candle_periods.py::transform_chart/chart_studies、SupportResistanceService、utils/support_resistance.py、EtfChart.vue。

已静态确认：read_model 日K使用研究序列计算指标、原始序列展示；transform_chart 周/月线从返回的原始 candles 重新计算。transform_chart 还以 chart_studies 替换 support_resistance，和声称唯一快照服务的路径并存。需要验证拆分前后的周期指标和价格线坐标是否一致，不能先美化图再忽略价格基准。

现有 chan_zone_approx 明确是区间重叠近似，不是完整分型/笔/线段/中枢。仓库引用 waditu/czsc 供对账；用户所说具体 Skill 尚未核实，不宣称已安装/移植。先核实仓库、许可证、固定版本、输入/输出和确认时点，再独立适配。Skill 可指导本地 Codex 制作图层，数值与结构由可复现代码计算，禁止模型臆造点位。

验收：原始/研究价位基准显式分离；不把日K线套在周/月周期；支撑/压力价格标签、范围和依据可见；分型/笔/线段/中枢单独开关；未确认结构和已确认结构区分；320/390/430px与桌面、缩放/全屏下复核；未来K线不改变已经声明当时可知的结构。

### R5：网站接本地 Codex，优先级 P1

复用 bridge/etf_agent_bridge.py、workspace bridge 队列与 docs/LOCAL_CODEX_BRIDGE.md，不另造一个直接远程执行 Shell 的网页接口。当前桥接已存在，但真人接入不等于 doctor 通过。

先展示未配对/离线/待本人登录/待费用批准/执行中/候选待审核；使用出站连接、独立私有根目录和一次性配对。现有桥接钉死CLI 0.149.0，实际安装版本不同要独立兼容审查，不能删除版本守卫。先离线测试，再由本人完成登录、一次受控任务和候选审核；重传不得再次调用模型。不得修改被平台明确拦截的写入或通过另一通道强行应用。

### R6：剩余证据与发布

R1只接收，不将未完成R2-R5排除在验收外。每阶段独立提交、固定 SHA 复测、证据与截图保留。需要部署时另行取得明确授权，备份/恢复演练、同源镜像/前端/库、真实数据覆盖、资源观察、回滚方案分别通过。行情资格、预测校准和14:30 PIT/OOS仍需独立证据；页面正常或CI绿色都不授予交易资格。

## 5. 外部参考的边界

OpenAI官方非交互模式文档支持以 codex exec 运行有界任务：https://developers.openai.com/zh-Hans/docs/non-interactive-mode 。这只是后续接口核对依据，不证明本仓库固定CLI版本已经完成现场登录/兼容验收。本次没有安装第三方缠论 Skill，也没有导入新的交易框架。

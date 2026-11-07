# Codex 接收与实地验收 Prompt：审核修复固定提交

你现在接收 ETF-Fund-Analysis 的审核整改代码，并完成本地复测、真实数据只读对账和受批准的 Bridge 验收。这是实际执行任务，不再重做产品，不把启动 Mock 当落地完成。

## 0. 固定代码、授权与安全边界

- 仓库：https://github.com/Jovifei/ETF-Fund-Analysis.git
- 现有修复分支：`fix/v105-audit-blockers-20260912`
- PR：#33，目标分支 `codex/v105-handoff-local-20260910`。
- 基线：`6d09ddb6cfde39d9d8e6a30783f9bdee838bc379`。
- **固定应用提交：`c87cfa1df906eee902c1e37509c63cf847d29209`**。
- 固定应用树：`a2a33b528af26725cd70a0fde252f48d8bdc813c`。
- 应用/前端/锁文件版本：1.0.5；这不是新建或已移动的发布标签。
- 后续只含文档的收据提交可单独阅读，不擅自改变被验收的运行代码 SHA。

允许独立 clone/worktree、安装锁定依赖、临时数据库测试、备份后副本演练、原私有配置的安全加载、诊断及小范围明确授权的采集。保护原工程脏改动；不 reset/clean/stash/强推，不覆盖现有数据库、账户、持仓和报告。不自动合并 main、移动标签或部署服务器。

对生产只读连接也要先确认目标及访问授权；没有授权在本地副本完成。任何可能清库的测试只能使用专用 test/scratch/ci 数据库。不要回显 .env、Token、Cookie、登录文件、数据库 URL、个人持仓或签名地址。不要从聊天或 Git 历史恢复凭据。真实模型调用必须本人逐任务批准，本任务本身不等于费用授权。

## 1. 接收、阅读、保存基线证据

先只读检查 remote、分支、HEAD、脏文件名，然后在独立目录接收：

```powershell
git fetch origin fix/v105-audit-blockers-20260912
git cat-file -e 'c87cfa1df906eee902c1e37509c63cf847d29209^{commit}'
git merge-base --is-ancestor 6d09ddb6cfde39d9d8e6a30783f9bdee838bc379 c87cfa1df906eee902c1e37509c63cf847d29209
```

使用 Git worktree 的新路径或独立 clone checkout 固定提交，不切换原脏工作树。远端有更新时先审 diff；不能把新提交算作本轮已通过。保留必要修复到单独本地分支，另行记录并复测。

先读：AGENTS.md、STATUS.md、HANDOFF.md、docs/README.md、docs/CODE_AUDIT_BLOCKERS_20260912.md、docs/audits/CLOSURE_20260913.md、docs/audits/ACCEPTANCE_20260913.md、docs/audits/REFERENCES_20260913.md、docs/versions/V1.0.5.md。收据与本 Prompt 若不在固定应用提交，从远端只读取得，不覆盖应用。

原审核报告 SHA256 为 `ef267273f30261247e3748a6c4fe983862c409555b07c18b03acc07d73885f77`，保留其原文和当时结论。把每个 P1/P2 分别记录为：代码防线已实现、回归结果、现场证据、尚未获得的资格。不能把四列压成一个“完成”。

## 2. 复跑测试，不借历史成功替代

Python 3.12 独立环境，Node 满足 frontend/package.json engines；npm ci，不任意升级锁文件。先看 .github/workflows/ci.yml、workspace-ci.yml、audit-platforms.yml 的实际命令，并逐条记录退出码：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,market]"
.\.venv\Scripts\python.exe -m pytest -q --junitxml=<私有证据目录>\pytest.xml
.\.venv\Scripts\python.exe -m compileall -q backend/app scripts
npm ci --ignore-scripts --prefix frontend
npm run test --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
npm audit --audit-level=high --prefix frontend
node --test backend/app/static/decision_board_workbuddy.test.js backend/app/static/legacy_route.test.js backend/app/static/decision_refresh.test.js
git diff --check
```

再执行旧 JS 语法、密钥扫描、临时 SQLite Alembic upgrade/check、普通 HTTP Playwright 及独立认证 Playwright。普通浏览器和认证浏览器是两套，不漏掉后者；不能拿组件图片代替 HTTP 操作。

使用专用 PostgreSQL 16 临时库，显式 TEST_POSTGRES_URL、APP_ENV=test、ALLOW_DESTRUCTIVE_TEST_DATABASE=1，复跑 audit-platforms.yml 中的 PostgreSQL 并发/迁移测试。不得指向生产或带真实持仓的恢复库。Windows 上实际执行 NTFS ACL 测试，不以 Linux 的 Windows-only skipped 代表通过。Docker 缺失则明确列阻塞，不声称镜像验证通过。

## 3. 原持久库只读审核——先找到问题，不先改数据

确认 API、worker、scheduler 实際加载同一份私有配置、同一有效数据库，且没有旧源码挂载遮住新文件。备份数据库和用户报告，恢复副本，验证完整性；既有库不得 init 或重置管理员。DATABASE_URL 只从私有配置安全加载，任何自动化不打印明文。

运行下面命令，输出使用仓库外、当前用户私有 ACL 的新文件：

```powershell
.\.venv\Scripts\python.exe scripts/audit_research_inputs.py --codes 510300.SH 512480.SH 588200.SH --output E:\ETF_Private\audit-before-20260913.json --fail-on-blockers
```

退出语义必须正确处理：0 表示报告成功且本次未发现列出的 blocker，不授予资格；3 表示报告成功且存在历史或指标 blocker；2 表示工具/IO失败。不要将退出3按临时错误无限重试，也不要删掉阻断字段。读取 items[].blockers 和 indicator_blockers；blocked 总数现在包含“仅指标版本/日期缺口”，不会双计同时有两类问题的标的。

工具不调用 Provider、不写 SQL、不创建表；每次最多50代码、单标的最多20000根，超过上限明确是不完整审核。该报告的逐基金 history hash 不是原面板计算 hash，二者不应直接作相等断言。

## 4. P1-1/P1-2：单位、价格断点与复权

新浪 amount/volume 接近 close、容差5%或10%、两个字段同乘100、字段非空，均不是绝对单位证明。当前 Sina v101/v102 保持未认证。固定 SDK/端点版本、官方字段单位、同一标的同日独立量/额/价和拆分口径，记录证据；没有独立依据就保持阻断，不能换 source 标签、批量乘100或取消检查。核对指定日期，避免把累计成交量和某根成交量比较。

对588200.SH，独立查验2026-07-20/21的原始价量及拆分结果。本次额外找到管理人公告（权益登记7月20、除权7月21、1:3拆分），它不证明数据库3.539/1.349记录正确。保留原始显示序列；研究需要独立、有证据和版本的调整/总收益序列，不能以全库价格乘3“修复”。35%断点阈值只是异常筛查，不证明小断点没有分红。

任何可信重抓/重算先在副本、限定标的、保留前后清单和原始证据。无法补齐的单位或公司行动记录列为真实阻塞。本轮没有完整公司行动自动重建器；需要新增实现时另列审阅任务，不说填配置即可完成。严格检查后更多标的进入缺口组是可能的，不能为减少异常而降低门禁。

## 5. P1-3/P1-4 与调度：按目标交易日，不按执行日期

运行既有测试并在隔离环境注入时钟/Provider验证：15:01不把昨日称为今日；15:16请求当日目标；源延迟仅返回昨日时partial/failed，间隔后仍能补抓；重启不丢目标；次日补漏；上游成功后下游失败可独立恢复。不要调生产系统时钟。

逐层核对 Provider → MarketService → Indicator/Forecast → TaskRun → worker/scheduler → API/页面：requested、valid/inserted、skipped、failures、missing、target_trade_date、latest_data_date及终态。同一任务所有层的状态一致；输入记录数不能充当输出成功数。全部跳过、缺少结果、未知状态、错误计数不能成功。

确认指数 OHLC 已进入必需盘后任务，不依赖 BALANCED_REFRESH_ENABLED；指数观察点位与指数日线分别验收。仅启用一套调度，先手动跑通小样本再开低频计划。SQLite 使用 backend/app/db/task_lock.py 的流水线跨进程锁及短事务，不是任意SQL多写者锁；不在网络盘共享SQLite。有多主机/持续写需求改为既有PostgreSQL路径。

## 6. P1-7/P1-8、P2：资格与展示复核

周六、未来报价、错误交易日、未验证源时间、缺结算历史、旧指标/config/schema都必须拒绝14:30资格。当前最终 actionable 固定false：历史PIT/OOS批准未完成。input_ready、realtime标志、异常组0都不是操作授权。

缺 volume 与缺 amount 分别测试。价格类诊断可保留，MFI/CMF等按依赖窗口输出null，不能fillna(0)取得虚假coverage。前值限定同算法/config/schema、紧邻日期；不可比要显示而非硬算差值。修改400/600根以前的实际输入仍应改变输入hash。逐期校准，不能一期calibrated传染其他期。

浏览器核对原WorkBuddy模板仍在同一总览；均线箭头始终表示价格相对均线，不暗换为斜率；数据异常counts存在且各组之和等于rows；旧壳刷新按task_id收敛失败/离线/重试。用受控延迟加载原表脚本，握手前输入禁用、握手后筛选不丢；不要删除故意慢脚本用例。

## 7. Codex 真实接入——子进程登录、一次批准、先本地后公网

先在 Windows E盘独立私有目录检查文件系统、owner、protected DACL、继承权限与二进制版本。允许当前用户及受信系统SID，拒绝宽权限；云端Windows测试通过不证明你的E盘权限正确。保留真实用户HOME，不修改父PowerShell HOME/USERPROFILE，不复制全局auth.json。

当前仅审核 codex-cli 0.149.0；本地安装版本不同则隔离安装已审版本或另行建立版本评审，不能直接放宽。doctor 不检查真正模型登录。

先查看 --help；下列命令从工程根运行，PATH/binary按实际安装路径解析：

```powershell
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root E:\AI_Tools\Other\ETF-Agent-Bridge doctor
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root E:\AI_Tools\Other\ETF-Agent-Bridge login --binary <已审Codex二进制>
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root E:\AI_Tools\Other\ETF-Agent-Bridge pair --origin <明确批准的本地或HTTPS站点origin>
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root E:\AI_Tools\Other\ETF-Agent-Bridge claim
```

服务端启用Bridge属于配置写入，先本地/隔离环境；生产开关和公网配对必须另行批准。配对码由本人安全输入。领取不调用模型；展示job_id/input_hash/证据日期和选用模型，完成本人费用确认后仅对这一任务执行：

```powershell
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root E:\AI_Tools\Other\ETF-Agent-Bridge run-codex <实际job_id> --binary <已审二进制> --model <本次批准模型> --approve-execution
```

核对同一私有runner目录、实际MCP为空、工具禁用、时限与输出预算、无Shell/数据库/自由网络。一次批准不得自动重跑。8000token参数与600秒不等于货币硬封顶；不假设Codex订阅令外部API免费。

合法已有result仅网络提交失败，使用 submit 重传，不再跑模型；损坏JSON、错hash、未知证据引用显式失败。验收候选报告→人工批准/拒绝、撤销、过期、重启、有效结果断网重传；负面场景使用假运行器，不额外付费。日志不含凭据与私人证据正文。

## 8. 单一发布证据与收尾

核实1.0.5后端/前端/锁文件与实际workspace footer/API相同。迁移head d40609090002。保留完整构建、依赖和运行镜像证据，使用 scripts/release_manifest.py --help 生成新收据；填写真实源码SHA、前端hash、运行时包、镜像ID/仓库digest、迁移。仓库digest未知就保持missing/incomplete，不以镜像ID冒充，也不要只改APP_VERSION。

若本地补了代码，原c87测试收据不再覆盖新提交，需重新跑相应全量与云端检查。公开docs只存净化摘要；原私有数据、备份、密钥留在仓库外。新部署/新验收使用新文件，不覆盖旧失败记录。

交付：固定代码SHA、本地URL、原数据保留证明、每个P1/P2的代码/测试/现场状态、3种数据库/权限环境结果、真实源目标日期/量额/复权证据、任务完整周期、页面/API一致性、Bridge有无真人成功及费用次数、发布清单missing、回滚方式与剩余阻塞。

不要将未执行的真人或生产动作写成成功。完整复权自动重建、真实14:30历史资格、自动训练、支付订阅、完整缠论和自动云地同步仍不是本轮已完成能力。先完成本地交付，生产发布另行批准。

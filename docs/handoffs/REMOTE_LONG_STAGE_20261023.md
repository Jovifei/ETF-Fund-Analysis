# 2026-10-23 远端大阶段接力

状态：交接输入。Jovi 已于 2026-10-23 授权第五节所述完整阶段、独立 GitHub 分支提交，以及仅在 `Jovifei/ETF-Fund-Analysis` 使用已安装 GitHub 插件；生产部署、策略和私有数据等排除项不在授权内。以下区分已在当前 Git 核实的事实、旧会话观察和待验收事项。

## 一、五项接力信息

1. **最终目标**：交付个人、低频的 ETF/LOF 研究工作台。本机采集真实数据并做确定性计算，网站消费有界结果包，清楚展示来源、时点、缺口、研究结论与失效条件；私有账户和持仓受隔离。数据、PIT/OOS 与校准合格后才讨论操作级资格；系统不连接券商、不自动交易。以 `docs/PROJECT_MASTER_ROADMAP.md` 为总目标。
2. **已完成**：2026-10-23 本地 `main`、`origin/main` 与 GitHub `main` 均为 `1a4b6652f49c412145d12812fa02820ba0a80991`。近期合入 11:40 时段、1/3/7/20/60 期限预测、公司行为记录、展示包历史重传与保留、已验证展示包缓存、可选市场上下文状态。10-16 调度台账/漏槽恢复代码已是当前 HEAD 的祖先。10-16 发布收据证明 `9fe9fe87adbc216f2db5d77248f990a48e79abad` 的本地真实34只计算、签名接收及 API Reader 核验；它不证明其后 `main` 已部署。
3. **当前卡点**：旧会话在 10-23 报告正常登录后的总览决策快照、板块和市场上下文请求取消或超时，重试未恢复；收盘 K 线刷新亦失败。这是待当前版本复现、定位的观察，不能仅凭前端统一的 20 秒超时文案判断根因。线上同批消费、自然触发、两个真实交易日观察和当前生产 SHA 未在本轮重新验收。真实数据的许可、量额单位、来源时间、PIT/OOS 与预测校准仍须独立证据，维持 `UNKNOWN / actionable=false / not_calibrated`。
4. **关键文件**：`AGENTS.md`、`docs/PROJECT_MASTER_ROADMAP.md`、`docs/REMOTE_LOCAL_RELAY.md`、`docs/PROJECT_PROGRESS.json`、`STATUS.md`、`HANDOFF.md`；`frontend/src/lib/api.ts`、`frontend/src/views/Overview.vue`、`backend/app/workspace/api.py`、`backend/app/workspace/local_display_read.py`、`backend/app/workspace/local_compute.py`、`backend/app/workspace/local_schedule.py`、`scripts/run_local_compute.py`、`config/strategy.json`；相关 `backend/tests/test_local_display_bundle_cache.py`、`test_optional_panels.py`、`test_cadence_cli.py` 与前端测试。S8 输入为 `docs/planning/S8_F0_DATA_FEASIBILITY_SPIKE.md`、`docs/audits/S8_F0_SOURCE_MATRIX_20261002.md`、`backend/app/services/pit_oos_harness.py`。`STATUS.md`/`HANDOFF.md` 仍描述 10-16，`PROJECT_PROGRESS.json` 仍为 10-06 台账，必须与当前代码对账后更新，不能直接照抄旧“下一步”。
5. **下一步**：远端在**同一阶段任务**内审核 10-20 至 10-23 的现有实现和可验证故障，先修复审查确认的真实回归，再读总路线、进度、关键数据资格和可借鉴开源项目，选择一个与现阶段最匹配、可完整交付的下一阶段，独立实现、测试、复审并提交 GitHub 固定 SHA。优先评估 S8 数据可信度/PIT-OOS 研究闭环；若当前证据显示线上消费或调度可靠性是更高前置，应说明取舍并完成同等规模的可靠性阶段。最终由本地 Codex 接收该 SHA，独立编译、测试和实际页面验证。

## 二、交给远端的一次完整阶段合同

本轮不是让远端只写计划、单点建议或帮助文件。以 GitHub 当前 `main` 固定基线开始，先核 `AGENTS.md` 和版本/数据源合同，然后交付以下完整链条：

1. **审查和复现**：审查最近集成的真实调用链、同包读取、缓存/内存、超时与失败状态、调度来源与回执；明确哪些旧问题已解决。给出故障复现或失败测试，区分用户页面、API、生产资源和数据缺失，不把合成或 HTTP 200 算作正常登录验收。
2. **简洁修复**：只修确认的根因，补正反测试，不放宽超时/资格/隔离门禁来掩盖故障。若故障位于仓库外（例如邮件补发模板），提供可审计归属和独立边界，勿猜测或修改无关代码。
3. **自主选择并执行下一阶段**：读 S0–S9 最终目标、当前代码/台账、S8-F0 来源矩阵及测试，考察可借鉴的开源实现及许可证/NOTICE，选一个可在本阶段做完、能提升最终目标的连续工作包。提交选择依据、退出条件，再实际实现；不将“寻找方向”当阶段完成。保持当前策略/数据版本约束，若改公式、特征、阈值、门控、组合或字段口径则升级对应版本。无合格来源、许可或真人权限时，只完成可合法验证的工程部分并保留 `UNKNOWN`，不伪造资格。
4. **验证与复审**：失败测试先行；按影响面跑后端/前端/类型/构建/真实浏览器或受控回放。策略改动至少跑 `pytest -q`、`python -m compileall -q backend/app`、`node --check backend/app/static/app.js`，并遵守 walk-forward、事件驱动回测、上一版本和基准比较、泄漏检查及人工批准门槛。审查最终 diff、权限/隐私、回滚与版本边界；修复发现的问题后重新验证。
5. **GitHub 固定交付**：先确认本网页会话是否有 `Jovifei/ETF-Fund-Analysis` 的真实写入途径。若具备，使用独立 `codex/` 分支提交实际源码、测试、必要收据和 `docs/handoffs/` 阶段交接，给出 base/head SHA、tree、改动文件、实际测试与未运行原因、未完成门槛及 PR/提交链接，供本地按 SHA 接收。若只有只读连接，明确报告缺少的写能力；不能把规划文字、连接成功或未推送本地文件声称为 GitHub 完成。

## 三、授权及执行边界

- Jovi 要求**本轮相关代码改动前征询授权**。远端先给出完整阶段方案和拟修改范围；本地向 Jovi 核对一次。获授权后在同一远端任务中连续完成审核修复、下一阶段实施和 GitHub 提交，不拆成多个快速聊天任务。文档梳理与只读检查可以先行。
- 不读取、复制或输出 `.env`、凭据、账户/持仓明细、私有数据库、签名 URL；不动生产库、用户数据、备份、回滚资产。生产使用 composite 且不允许 Mock fallback；Mock 仅供测试/演示，阻断 actionable。
- GitHub 提交、CI、部署、真实来源资格、正常认证用户、手机和两交易日观察分层记账。生产切换、数据购买/授权、自动交易与真人验收不由本交接自动放行。
- 本地接收前先核 GitHub 远端 ref 与固定 SHA，保护当前工作树；独立测试/页面证据与远端收据分开，失败集中回传同一远端阶段继续修复。不要将旧会话的已解决项重新立项。

## 四、本次交接的证据边界

- 2026-10-23 当前仓库核对：`git status` 在写本文档前为干净 `main`；`git ls-remote origin refs/heads/main` 返回 `1a4b6652f49c412145d12812fa02820ba0a80991`。本文档、`tasks/todo.md` 和 `tasks/lessons.md` 是本轮文档改动，尚非远端基线。
- 网页超时、收盘刷新和观察任务状态来自旧会话的 10-23 记录，须在当前运行环境重验。最新生产部署身份未在本轮核对；10-16 收据只证明当时固定版本。
- 本轮尚未修改业务代码、部署或运行全量测试。验收状态不得从旧文档、模拟、已接收包或 ChatGPT 文本推断。

## 五、远端只读审核提出的阶段方案（待 Jovi 授权）

同一“基金决策”聊天的 `c2c_a7f2` 在核对当前源码后选择“发布结果可信接收与有界消费闭环”。这是一份**待复现、待授权的方案**，不是已完成修复：

- `shadow_api.py` 与 `local_display_read.py` 的旧序号重传路径需要先写负例，证明同序号不同身份、从未接收的旧包不得返回 `already_accepted`；合法精确旧包恢复仍不提升 latest/previous。当前代码可见按序号判历史、目标文件缺失时结构校验后写入的路径，尚未有持久的“该精确包曾接收”证明。
- `LocalDisplayStore.load_bundle(generation)` 当前逐个解析 `bundle_*.json` 后才判断代号；在多代、并发固定代读取下须测试解析次数及无关文件读取次数，再实现先定位候选文件、后验证内容的有界读取。不能仅扩大缓存或延长前端超时。
- 可选市场上下文的生产状态经 Reader/API 到网页可能丢失；请求失败、未发布、采集失败、沿用同日旧结果应分别展示。网站只读模式下不可用的指数图/历史准备入口须按实际能力调整；取消、超时和切代竞态以失败测试判定，不推测根因。

授权范围上界：`backend/app/workspace/{local_display_read.py,shadow_api.py,local_display_contract.py,api.py,local_compute.py}`、`backend/app/api/router.py`，如确有必要新增 `local_display_receipts.py`；`frontend/src/lib/{api.ts,query.ts,types.ts}`、`frontend/src/views/{Overview.vue,Detail.vue}`、`frontend/src/components/{OriginalDecisionBoard.vue,HistoryLoader.vue}`；对应后端、前端、受控认证浏览器测试，以及当前状态/进度与阶段收据文档。只改审查后证明确需改动的文件，保持实现简洁；`config/strategy.json`、Provider 接入、生产部署/数据库/账户持仓与受保护资产均不在本轮范围。完整验收按第二节合同及远端聊天中的文件级表执行。

远端已实际验证读取身份为 `ETF-Fund-Analysis main@1a4b665`。Jovi 授权后，“基金决策”项目指令已改为允许远端仅对本仓库使用 GitHub 插件。远端已在独立分支 `codex/c2c-a7f2-trusted-consumption-20261023` 提交阶段实现、两项本地审查修复和容量夹具回归；当前 Draft PR53 head 固定为 `fdaf5426585d64800dbff60656797cd75306f19e`，tree `6c2450558b2f862e4fc5fbd6929a1999c6ae7d33`，未合并或部署。GitHub 完整 `ci` SUCCESS，但 `workspace-ci` 的既有依赖安全门 FAIL；本地 149 项后端聚焦、Vue 218 项及受控认证浏览器 1 项通过，完整本地 pytest 中断。按 [本地独立接收记录](../audits/PR53_LOCAL_ACCEPTANCE_20261024.md) 保持 **CHANGES_REQUIRED**，不把部分通过或分支提交当作所有门槛完成。

# 当前接手入口：R4C M3 已推送，等待远端复核（2026-09-29）

## 本轮交接

- 当前隔离分支：`codex/r4c-m3-persistence`，已推送到 GitHub。M3 实现提交 `ce0aa9b899b6d04ea682581b90343fa2973394ce`，基线为远端确认 M2 PASS 的 `641759eb467ef743f35c142edd50a8208bb2cfa7` / tree `9b4c934c4d8d562ace876f5c5f49c5b0042b4bc1`。Owner 工作区保持独立且未改动。
- 远端迭代 60 判定 M2 `PASS`，保留 CZSC `1.0.1` + observed-revision 路线，并给出 M3 持久化发布核心计划。本地先 RED 后完成 migration/models/publisher 与专项验收。收据见 [R4C M3 persistence acceptance](docs/audits/R4C_M3_PERSISTENCE_ACCEPTANCE_20260929.md)。
- M3 限于不可变观测证据、结构修订、状态转移、当前 stream head 和单事务发布；只用合成数据与隔离 SQLite/PostgreSQL 测试库。远端原计划标记 `M3_GO=false` 等待独立授权；Jovi 已授权持续 C2C 执行循环，本轮按该授权推进。
- 本阶段完成后继续“测试 → GitHub 推送 → 远端审核 → 下一阶段计划”。项目最终人工验收不是当前停止条件；只有明确需要 Jovi 决策的门禁在对应步骤等待。

## 下一步

将当前推送分支的精确 tip 与 [验收收据](docs/audits/R4C_M3_PERSISTENCE_ACCEPTANCE_20260929.md) 交远端复核，请其对照原计划评估新增的数据库不可变性和流内序号设计。远端复核后按审核结论和下一阶段计划继续。全量 pytest 停在 27% 长时间无进展后中断，详细状态在收据中；定向 decision-board 队列测试单项通过。

人工验收是产品最终阶段的门，不是当前停止条件。该协作循环持续到项目目标完成；生产部署或真实数据资格仍需各自独立门禁。

---

# 历史接手入口：R4B 本地接受完成，C2D 文档对账（2026-09-28）

## 先读

1. [R4B final acceptance](docs/audits/R4B_FINAL_ACCEPTANCE_20260928.md)
2. [R2–R4B reconciliation](docs/audits/R2_R4B_RECONCILIATION_20260927.md)
3. [R4B 实现与最终 addendum](docs/09-RPT-R4B箱体与支撑压力验收.md)
4. 本页与 `AGENTS.md`

## 两个必须分开的身份

### 当前运行生产

- SHA `0dbd3fee58a3f5e080aacbcd8eae8d5964aec54f`
- tree `f8607b3de8decde6065ccc559c5c26b0262b8e6b`
- Alembic `e609200001`
- 生产状态未被本阶段改变。

### 已接受但未部署的本地 R2–R4B

- SHA `43bfbf6929a70f520c216b759edbaa433e920e91`
- tree `12d217af3edbe34c67bc36e75b4395ab4917b001`
- 候选 Alembic `g8b9c0d1e2f3`
- `R4B=ACCEPTED_LOCAL`; `M0_TECHNICAL_GATE=PASS`; `M0_FINAL_STATUS=PENDING_C2D_RECONCILIATION`
- 真实数据资格 `UNKNOWN`；`actionable=false`；canonical action unchanged。

C2D 需完成文档、收据和入口对账，并交远端复核。R4C M1 只能从上述精确候选继续；不能把生产 head 改成候选 head，也不能把本地接受写成已部署。

## 保护边界

继续保留原生产备份、认证、真实数据、Provider、PIT/OOS、人工批准和部署门禁。不要 reset/clean/stash 主工作区，不读取或回显凭据，不执行生产迁移。

---
# 当前接手入口：R4B 日线结构本地实现分支（2026-09-27）

当前分支 `codex/r4b-price-structure`，从 R2–R4A 文档提交 `4d8fa1a4b7c5fc8dc3d0066c74dc86cd9092df18`（tree `6400437180c62052936f443f423910fd2a841ac6`）继续。R4B 应用最终 SHA `8a5b575904c4cbc5a2d63e53a8521076c80904e1`，tree `1fc3d4657dba7f9e0f0ec5d06875eaaa45c98d83`。读取[R4B实现与测试收据](docs/09-RPT-R4B箱体与支撑压力验收.md)和[逐页状态矩阵](docs/10-TST-R4B逐页状态验收矩阵.md)。

日线结构在统一研究价格序列上计算，按实测 ATR、交易日历、独立触碰和状态事件确认；图表只读已保存快照，临时盘中越界不持久化。无迁移；不改变预测校准或操作资格。

最终本地验收：后端 1269 项中 1255 通过、14 条件跳过；Vitest 63/63；普通/认证/响应式浏览器 26/5/18；前端类型检查/构建、compileall、Node 39/39、安全扫描通过。真实 Provider、真实数据资格、PostgreSQL 条件和生产部署未验收；资格保持 UNKNOWN。

本地分支尚未推送或合并。下一步按发布门禁核对 remote/main 与 CI，再决定 main 集成、镜像、备份恢复演练及部署；生产仍未检查或修改。R4C 完整缠论排在发布/验收之后。

## 上一阶段：R2–R4A 本地接收（2026-09-26）

本地代码在隔离 worktree 分支 `codex/r2-freshness-lifecycle`，基线 `c63f669095e6eb44e1e9c185deecf0f7af02b27c`。R2–R4A 应用代码提交 `8b52d39d22ebb21a41e269ab9ce9863b85dd3b83`，tree `d7ce9c857f48a99e130cf6060700974213c4e9c0`；前端补充状态测试提交 `f4286d590fd6f9565192754e40c553048286823d`。读取[实现收据](docs/R2_R3_R4A_IMPLEMENTATION_RECEIPT_20260926.md)和[路由验收矩阵](docs/ROUTE_ACCEPTANCE_R2_R4A_20260926.md)查看本机命令、首轮失败、最终通过与条件跳过。

`main` 仍是 `c63f669`，本地分支未推送/合并/部署；真实数据资格仍 UNKNOWN。无需继续修改已关闭的 60 秒可见刷新。本阶段后续路线为 R4B 箱体/结构位 → R4C 缠论 → N1 新闻证据 → R5 Bridge → R6 数据资格和样本外研究。部署要使用新 SHA 对应的完整 CI 镜像，并先完成独立的备份/恢复和运行验收。

## 2026-09-23 接收与生产背景

先读 `AGENTS.md`、本页、`STATUS.md`、[本次生产收据](docs/PRODUCTION_DEPLOYMENT_RECEIPT_AU_20260923.md)、[A-U1–A-U3 接收合同](docs/UI_ACCOUNT_HANDOFF_20260923.md)。当前部署源码固定为 `0dbd3fee58a3f5e080aacbcd8eae8d5964aec54f`，tree 为 `f8607b3de8decde6065ccc559c5c26b0262b8e6b`，镜像 ID 为 `sha256:251a0623c694b07525bd398b52f41eecc17ec3d1216912c6d593b704fc8ae81a`；API/worker/scheduler 同镜像，数据库 head `e609200001`。R1 在此前已合并；本次 A-U1–A-U3 与构建/运维脚本修复随后快进到 `main`。

本次没读取或修改生产业务行，没有刷新真实 Provider，也没有重标 certified/hash/原始 OHLCV。真实数据资格保持 **UNKNOWN**，不能从健康检查或 CI 通过推导交易资格。接下来按顺序完成 R2 更新及时性、R3 详情空态/决策解释、R4 价格研究基准和完整缠论、R5 真人本地 Codex；真实数据复审和后续发布作为 R6 单独授权。账户邮箱/短信/微信验证、找回和永久删除仍未实现；当前账户关闭只停止登录并保留数据。

## 原有数据保护与回滚合同

## 认证与数据保护合同

正式服务必须保持 AUTH_ENABLED=true，DATABASE_URL 从仓库外私有配置读取，AUTO_CREATE_SCHEMA=false，通过 Alembic 迁移。正式 HTTPS 使用 AUTH_COOKIE_SECURE=true；本地回环 HTTP 的 Cookie 例外不得复制到生产。浏览器使用数据库账户/会话，不复活旧 Bearer 认证。auth-bootstrap-admin 仅限已确认的新空库，由本人安全输入；原库不得重新初始化或重置已有管理员。任何 pytest/seed/清库工具不得指向真实持仓数据库。

独立 clone/worktree 接收，保留原工程脏改动；不 reset/clean/stash，不强推。备份原库和私有报告，先恢复到副本演练。只读诊断：

```powershell
.\.venv\Scripts\python.exe scripts/audit_research_inputs.py --codes 510300.SH 512480.SH 588200.SH --output E:\ETF_Private\audit-new.json
```

必须先安全加载指向副本的 DATABASE_URL。输出文件不能已存在。此命令没有 Provider 调用、SQL 写入或资格提升；退出0仍需检查 items[].blockers 和 indicator_blockers。Windows 输出目录ACL由本地接收者先检查。

## 验收顺序

第二真实源 bounded probe → 同日量额/单位对账 → 按目标交易日抓取和衍生任务 → PIT/OOS walk-forward → 14:30 前瞻观察 → 人工批准。日线截止统一 15:15，不把 15:01 取得的昨日数据记成今日完成。指数 OHLC 与实时观察是不同数据路径。

当前 FTShare 的 Skill 路由实测为 `etf-ohlcs=404`、`etf-candlesticks=405`；应用内固定 Provider 对五只 ETF 的列表、日线、现价探测均为 `CapabilityUnavailable`。不得手工把 `FTSHARE_QUALIFICATION` 改成 `qualified`。资格脚本修复后，即使三项接口都有记录，只要缺独立单位或 operational-grade 时间证据，顶层状态仍必须是 `unqualified`。

API/worker/scheduler须同版本、同有效库，SQLite通过现有文件锁串行流水线及短事务；不把WAL称为无限并发写入或网络文件共享方案。旧路径的写入者必须停止重复调度。优先利用专用PostgreSQL测试与实际部署策略。

Bridge 登录使用 bridge/etf_agent_bridge.py 的 login 子命令；不要改父PowerShell的 HOME/USERPROFILE。CLI仍严格固定0.149.0，未知版本需独立审阅，不能删除门禁。启用、本人登录、费用确认与最多一次work在现场完成。合法已生成产物重传不得再跑模型，损坏结果显式失败，不修改lease来重付费。醒后逐步清单见 [docs/LOCAL_CODEX_BRIDGE.md](docs/LOCAL_CODEX_BRIDGE.md)；pytest/`doctor` 退出 0 不是登录、配对或付费成功。

不直接按系数修改新浪量额或原始价格。已登记的官方基金份额拆分事件（见 `docs/audits/CORPORATE_ACTIONS_20260920.md`）只允许在内存研究序列中按证据生成复权视图；公告证据、端点单位合同、原始记录与独立研究序列必须分开。没有完整证据仍维持研究阻断。新版本会使部分“看起来正常”的旧数据暴露缺口，这是安全修正而不是让接手者清掉异常。

## 回滚与范围

无生产部署授权时，只做本地/隔离验收。需要上线另行批准；任何数据迁移先备份和恢复演练。不要把恢复旧数据/旧代码用来绕过新资格门禁。恢复备份前保护其后新增的持仓、自选、复盘与审阅写入。模型API主密钥、账户凭据、行情Token不得进入Git、聊天或截图。

[旧交接全文](docs/archive/pre-audit-close-20260913/HANDOFF.md)仅保留历史，不覆盖以上规则。完整缠论、自动训练、支付订阅、自动云地同步仍未实现。

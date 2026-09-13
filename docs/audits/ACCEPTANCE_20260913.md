# 审核修复固定提交验收收据（2026-09-13）

## 1. 本收据证明什么

修复分支 `fix/v105-audit-blockers-20260912`，PR #33，基线 `6d09ddb6cfde39d9d8e6a30783f9bdee838bc379`。固定应用提交 **`c87cfa1df906eee902c1e37509c63cf847d29209`**，应用树 `a2a33b528af26725cd70a0fde252f48d8bdc813c`。

这是累计代码整改与隔离测试收据，不是生产升级、全部数据获得资格或真人模型接入成功的声明。未合并main、未移动标签、未修改生产配置/数据库/账户、未调用付费模型。原WorkBuddy模板、统一总览及ETF详情保留。

原审核文档不变：`docs/CODE_AUDIT_BLOCKERS_20260912.md`，SHA256 `ef267273f30261247e3748a6c4fe983862c409555b07c18b03acc07d73885f77`。旧失败及当时现场事实不因本次通过被抹掉。

## 2. 同一固定提交的云端结果

三套流水线均 completed/success，2026-09-13重新读取并下载JUnit/浏览器报告核对：

| 流水线 | 固定运行 | 实际证据 |
|---|---|---|
| ci #629 | https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/34757153742 | 全量980项，978通过、2平台条件跳过，0失败；compileall、旧JS、安全扫描、Alembic、ShellCheck、Compose、生产镜像构建及PostgreSQL容器smoke通过；产物inventory已生成。 |
| workspace-ci #152 | https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/34757153715 | 后端专项258项，257通过、1 Windows-only跳过；TypeScript、Vitest、build、npm高危审计通过；真实HTTP Chromium普通18/18、独立认证2/2，0失败/0重试飘过。 |
| audit-platforms #20 | https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/34757153732 | 真实Windows17/17，含NTFS受保护DACL/宽权限拒绝与父/子HOME；专用PostgreSQL16套件23/23，含原条件并发/迁移测试，迁移check通过。无模型调用。 |

全量中的两个跳过分别是实际Windows ACL与显式TEST_POSTGRES_URL的测试；不是消失了，而是上表独立平台任务确实执行通过。不能说Linux全量执行过这两个平台用例，也不能说Windows CI替用户E盘现场权限认证。

PR工作流checkout的是合并验证提交 `c26130328c6b8e26150c582584e3b5cea3a98662`，其源码树与固定应用提交完全相同，为 `a2a33b528af26725cd70a0fde252f48d8bdc813c`。应用接收仍锁定c87，不把临时PR merge SHA当发布分支。

## 3. 可复核产物

| 产物ID | 归属 | 下载ZIP SHA256 |
|---|---|---|
| 10317294435 | ci-34757153742，JUnit与release-inventory | c8cc5d0f0dfba6aac5ff0e26977c51750e0a879c6a6a67e3aa272e9bec5141aa |
| 10317532320 | workspace-34757153715，源码tar/JUnit/普通与认证Playwright报告 | 16e6c80c60d0ab435ebb08b8be0798c5b4678cef00163294f345d886dad60bc9 |
| 10317423685 | postgres-34757153732，JUnit | 54b6405a587f33f32dea90a7b8a23c3861cca181f54e30132c3fff646edbc881 |
| 10317293821 | windows-34757153732，JUnit | a44cb17f0901fee01953672e0664c88faa927448db66dda3ccf58082f0c475cb |

GitHub产物会按工作流保留策略过期，本地接收者应保存净化证据，而不是将临时签名下载URL写进仓库。

CI实际构建镜像ID：`sha256:3bc5d43daff3be77dc03f0cc79f215519f6a72e66a55325841a35e92e99b98ac`。前端构建树hash：`10386e9ab02bd4206a776ecc909207feda48662df986c67ea45efc712a927b05`。运行时包hash：`5db59382bb03eebbc3f109271ca682db8492868f4c7a7403a7a9303cdd6d9a02`。应用/前端/锁均1.0.5，迁移head为d40609090002。

**镜像未发布到registry，registry digest仍为null，release_inventory_complete=false，missing为published_image_digest_missing。** 构建和smoke通过不是生产发布完成；部署者须对最终实际运行镜像重新生成收据，不伪造digest或仅改APP_VERSION。data_qualification=not_asserted、production_deployed=false继续保留。

## 4. 本次最后接续及本地验证

重连首先核实d6928ae及既有修复/三套测试，保留其累积工作，不从旧main覆盖。进一步发现只读审核摘要原先只数历史blockers，会漏掉仅indicator版本/日期不一致。提交c87增加history_blocked、indicator_blocked及并集blocked，并添加--fail-on-blockers。新4条测试先全部失败，修复后加既有只读测试共8条通过，失败日志保留。

本隔离容器Python3.13：最终全量980项、978通过/2平台跳过/0失败，退出0；旧JS24条通过；专项80通过/1Windows跳过。首次venv缺pytest和源码tar不含.git导致发布自检失败，按环境问题修复后重跑，不删除断言。源码tar与远端git tree已对账；为本地release测试建立的合成Git提交不等于远端SHA，不能作为部署版本。

前序真实失败也保留：旧测试import路径错误、严格新浪/空结果资格断言修正、Windows中文文件cp1252读取失败、原模板慢脚本握手丢输入，以及pandas attrs重复deepcopy导致全量慢跑。处理为对应源码/UTF-8/握手/元数据大小修复，未关闭数据门禁、删测试或增加重试掩盖问题。

## 5. 原审核逐项关闭边界

详见[关闭矩阵](CLOSURE_20260913.md)，保留原P1/P2编号。已实现的是：单位资格冻结、未解释断点拒绝、原输入缺失mask、全历史hash/同版本前值、统一目标日/任务终态、指数必需盘后任务、跨进程流水线锁、14:30失败关闭、子进程登录/ACL/合法结果无重复计费重传、发布inventory以及表格状态一致性。

尚须现场或后续开发：新浪绝对量额的独立同日认证；588200历史价格与公司行动/独立复权序列重建；连续真实交易日收盘与上游延迟观察；用户E盘权限及实际CLI二进制隔离；本人官方登录、一次明确费用批准、实际origin配对与回传/审核/撤销。完整公司行动自动调整器和真实14:30历史PIT/OOS批准没有因测试通过而完成。

35%只用于异常筛查。行情可显示、工具退出0、任务成功、异常组0都不等于交易资格；最终14:30 actionable仍false。原库不直接乘100或价格乘3，不删除不合格原记录，不把旧快照改版本标签充作重算。

## 6. 交接

按[本地Codex Prompt](../CODEX_RECEIVE_AUDIT_20260913.md)接收固定应用SHA；后续只有文档的提交单独记录。先保护原数据，在副本只读审核，再做限定采集和测试。当前仅批准本地/隔离验收，生产上线另行确认。完整缠论、自动训练、支付订阅、自动云地同步和完整场外目录仍是范围外未实现能力。

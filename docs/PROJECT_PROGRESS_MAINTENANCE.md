# 项目进度维护契约

由 Jovi 于2026-10-02授权，远端ChatGPT制定总路线图并修订计数口径。本地Codex负责台账、生成视图及每轮维护。

## 文件角色

- `PROJECT_MASTER_ROADMAP.md`：稳定的大阶段目标、旧编号映射、实施步骤与退出条件。
- `PROJECT_PROGRESS.json`：唯一可编辑进度数据源；S0–S9及子任务五维状态、当前发布清单、精确版本、卡点和变更记录。
- `PROJECT_PROGRESS.md` / `.html`：由脚本生成的可读总览和进度条。HTML为本地文档，无网络请求或业务数据访问。
- `scripts/update_project_progress.py`：验证台账并生成总览；不用安装第三方依赖。

## 每次有实质项目更新时必须执行

1. 读取最新checkpoint、阶段计划、执行收据和STATUS/HANDOFF，确定受影响的Sx-Uyy。
2. 在JSON更新代码、测试、远端审核、部署、线上验收五维状态；每项PASS绑定证据，N/A写适用范围原因。演练和Mock只能作为相应测试证据。
3. 更新上海时间 `updated_at`、当前阶段/iteration、已部署代码与tree、发布证据基线、Alembic、当前下一动作与卡点。
4. 在 `events` 追加变更及证据；已通过项发现缺陷则REOPENED，计数随之减少。
5. 正式计划确认完整验收范围、逐项证据映射及适用维度后，才能设置 `counter_frozen=true` 和 `freeze_evidence`。普通想法不进入正式分母。
6. 运行以下命令生成并检查，再同步STATUS/HANDOFF和任务清单；同次文档提交推送台账与生成视图。

```powershell
python scripts/update_project_progress.py
python scripts/update_project_progress.py --check
```

发布、审查、测试失败、依赖阻塞、计划范围变更均触发更新。仅轮询且状态不变不改日期、不制造进展、不重复提交。通知仍只在实质进展、失败或需要用户决定时发送。

## 五维完成与进度计算

适用维度全部PASS或有理由的N/A，且绑定证据，才可计单元完整通过。代码完成、HTTP200、平台健康、模拟/本地演练，均不能替代需要的真实用户线上验收。

阶段进度条 = 已完整通过的冻结验收单元 / 已冻结总数。分母未冻结显示待核对，不给整体百分比。真实数据资格单列，不能由功能进度、部署或回归测试推导。

目前iteration71固定发布清单R1–R12拆分R9为平台/私有，共13项，9项PASS；R11READY不计PASS。这是发布清单闭环，不是S3或全项目工作量完成率。首稿17/20已被远端撤销。

当前S3私有读取代码侧已通过而线上验收未闭环；台账代码/测试/审核PASS来自已审核范围，Live必须PENDING。当前未激活Chan，不自动交易。

## R10收据要求

正常登录已经完成后，围绕同一次私有Chan GET立即记录T0和T1八项聚合计数：四张Chan证据表、总任务、queued/running任务、ProviderAudit、chan_structures任务。不能使用登录前后或旧部署快照的计数替代。R9-private/R10完成后先推送最终收据，再交远端R12复核。

## 工作区和Git同步

Jovi查看入口位于 `E:\project\ETF-Fund-Analysis\docs`。原阶段工作区 `.local\etf-r4c-m3bc` 已有独立文档提交，GitHub原审核分支同时收到外部代码推进；本轮总规划在项目内 `.local\etf-project-roadmap` / `codex/project-master-roadmap-20261002` 交付，以远端候选e0fcb17为基线。同步只包含本契约明确的路线图/台账/生成器/任务记录，不把Owner main既有脏修改或执行目录旧计划改动混入。

2026-10-02接收线索：原远端分支有图表研究层、简化结构/prior-range及ETF流量/份额Provider/schema新代码，尚未独立审查/验证。后续先记录并核对这些候选的路线和证据，不把旧聊天M4未开工推成“仓库没有实现”，也不把提交存在推成测试或线上PASS。任何候选部署另走正式门禁。

后续接力在执行分支更新台账、生成视图和提交后，将这组文档复制到根目录docs供Jovi查看；不得只更新隔离目录却留下根目录旧进度。每轮先核对现有文件是否被人修改，有分歧先讨论再同步，禁止无条件覆盖人工修改。

准确DOCS_HEAD通过 `git log -1 -- docs/PROJECT_MASTER_ROADMAP.md docs/PROJECT_PROGRESS.json` 查询，避免把自身commit SHA写进自身内容产生循环。发布证据基线、部署代码SHA、总览文档提交各自记录。

## 远端讨论和路线更新

技术路线和验收口径出现分歧时，把有界问题发回同一绑定远端聊天讨论；远端修订后在事件与总路线图记录原因。本轮远端已修正17/20误计、R10登录前后误比、普通单元测试套PIT/OOS等问题。正式实施仍沿用已授权的阶段计划，路线图本身不更改生产或策略资格。

# 本机计算到网站展示：2026-10-23验收与文档精简

状态：LOCAL_GENERATION_AND_RECEIPT_OBSERVED / AUTHENTICATED_CONSUMER_BLOCKED。本批不是部署收据。

## 当前实际证据

- 基线main/origin main：`1a4b6652f49c412145d12812fa02820ba0a80991`；原目录后续新增任务/交接文档不覆盖。
- 本机数据根F:\ETF_Data\ETF-Fund-Analysis，研究库和调度库分离；正式任务固定1a4b665。
- 13:55、14:20、14:30、14:45、14:50、14:55、15:00均有1a4b665 DELIVERED。11:40由d7e1ed4运行，不混作同SHA。
- 最新包generation1792738850091，15:00:27.202311上海生成，15:03:25.322810 accepted。
- bundle/manifest ID：653164fba9d1ad580478e7211dfddf3f53639a21c27699a37f4fa6395c95fe66；本地manifest和所有parts哈希均与回执/清单一致。
- 34只日线均截至10月22日。包17:00:27.202311到期，晚间核验已过期，不能说新鲜。
- 15:15两attempt failed，bars完成0/34；16:10两attempt partial，仅3/34、6/34，未导出新包。原始失败保留。
- Jovi正常登录后，决策板、板块、上下文均显示请求取消或超时；只读重新读取未恢复。/api/health200不证明消费通过。
- 两日观察任务Disabled，尾盘120秒未通过；生产镜像/DB/配置和另一AI服务器搬迁/备份范围未触碰。
- codex-with-chatgpt最初连接失败，后在不更改系统网络/权限的情况下恢复；已向同一ETF普通Chat发送本阶段核验请求，等待项目读取和最终复审，不冒称通过。

## 当前授权与修复边界

Jovi本轮明确确认：独立分支先测后修网站读超时和收盘刷新，不自动部署。业务在codex/local-chain-repair-20261023处理；文档在codex/docs-consolidation-20261023处理。
网页缓存扫描放大与日线目标日期缺失正在独立复现，最终修复/测试以业务分支固定提交收据为准；本文件不预先签发PASS。

## 文档归纳与精确清理

Jovi已确认“归纳后删除中间文档”。精华收进README/QUICKSTART/STATUS/HANDOFF/ARCHITECTURE/产品路线；专业合同和正式进度JSON保留。
下列20份均先核实当前内容等于基线Git blob，且路径在独立工作树内，为普通已提交Markdown；删除前记录路径、bytes、blob与SHA256。未整目录递归删除。

| 删除的旧路径 | 精华/替代入口 |
| --- | --- |
| docs/superpowers/plans/2026-08-28-dashboard-integration.md | README / ARCHITECTURE / HISTORY |
| docs/superpowers/plans/2026-08-28-market-context.md | README / ARCHITECTURE / HISTORY |
| docs/superpowers/plans/2026-08-28-portfolio-ocr.md | README / ARCHITECTURE / HISTORY |
| docs/superpowers/plans/2026-08-30-ftshare-demo-execution.md | README / ARCHITECTURE / HISTORY |
| docs/archive/pre-v103/docs-README.md | START_HERE / HANDOFF / 文档地图 / HISTORY |
| docs/archive/pre-audit-close-20260913/docs-README.md | START_HERE / HANDOFF / 文档地图 / HISTORY |
| docs/archive/pre-audit-close-20260913/README.md | START_HERE / HANDOFF / 文档地图 / HISTORY |
| docs/archive/project-simplification-20261002/START_HERE.md | START_HERE / HANDOFF / 文档地图 / HISTORY |
| docs/archive/project-simplification-20261002/SELF_SUBMIT.md | START_HERE / HANDOFF / 文档地图 / HISTORY |
| docs/archive/project-simplification-20261002/docs__README.md | START_HERE / HANDOFF / 文档地图 / HISTORY |
| docs/archive/project-simplification-20261002/LOCAL_AGENT_PROMPT_ETF_1430.md | START_HERE / HANDOFF / 文档地图 / HISTORY |
| docs/archive/main-3c7bdc7/README.md | START_HERE / HANDOFF / 文档地图 / HISTORY |
| docs/archive/main-3c7bdc7/docs/README.md | START_HERE / HANDOFF / 文档地图 / HISTORY |
| tasks/plans/2026-09-02-cli-report-consistency.md | README / ARCHITECTURE / HISTORY |
| tasks/plans/2026-10-02-main-consolidation-cleanup.md | README / ARCHITECTURE / HISTORY |
| tasks/plans/2026-10-02-project-macro-roadmap.md | README / ARCHITECTURE / HISTORY |
| tasks/plans/2026-10-14-main-consolidation.md | README / ARCHITECTURE / HISTORY |
| docs/R4C_IMPLEMENTATION_PLAN_20260927.md | README / ARCHITECTURE / HISTORY |
| docs/LOCAL_AGENT_PROMPT_WORKBUDDY_BOARD.md | START_HERE / HANDOFF / 文档地图 / HISTORY |
| docs/SELF_SUBMIT_V101.md | START_HERE / HANDOFF / 文档地图 / HISTORY |

旧提交恢复：`git show 1a4b6652f49c412145d12812fa02820ba0a80991:原路径`。原始清单保存在E:\Claude_allow\Download\ETF-chain-fix-20261023\documentation-deletion-manifest.json；Git历史不清理。
保留audit、真实失败/发布/回滚证据、第三方NOTICE、contracts、progress JSON及脚本生成视图、运行/测试引用路径、有效测试和非Markdown历史manifest。
修复SELF_SUBMIT和LOCAL_AGENT_PROMPT_ETF_1430旧归档入口；保留旧manifest声明其只属于原交付快照，不改历史哈希。

## 验证

- 删除前文档兼容检查3项PASS（独立工作树原始基线），不是整项目测试。
- 最终文档/期限/时间口径/浏览器认证/1430路径合同：43通过、0失败/错误/跳过。
- 精确删除清单20份、104967字节；保留Markdown到删除目标的链接0项，修改文档新坏链接0项。
- 进度生成及--check通过，git diff --check通过；独立文档复审PASS，逐项核对清单、Git blob/CRLF字节哈希、链接、阶段字典与JUnit。
- 所有阶段/子任务/历史release gate状态保持原值，不因文档精简晋升。

## 未完成与下一动作

网站实际消费、收盘刷新、固定SHA完整测试、网页GPT最终复审、自然两日/手机与数据资格分别未闭环。主分支业务合并和服务器部署不由本次清理自动放行。

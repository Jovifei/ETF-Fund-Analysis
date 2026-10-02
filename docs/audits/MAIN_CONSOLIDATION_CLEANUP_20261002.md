# main收尾与项目简化收据

用户授权：合并有效分支、提交main、整理旧文档和废弃产物，为新工程接手。

## 已接收工作

本轮开始暂存区为空；2份未暂存状态文件和10份未跟踪路线/进度文件已留存本地快照及SHA256，并提交main。快照目录 `.local/consolidation-20261002/pending-before`，不含凭据或业务数据库。

- 正常合并 `codex/project-master-roadmap-20261002` 和 `docs/main-tip-r4c-chart-flow-20261002`。
- STATUS/HANDOFF冲突保留现场核实的v2状态，补齐main-tip的其他架构/数据合同文档。
- 17条早期交付历史用Git ours策略归并；保留全部父提交，当前树不恢复其旧实现。这是历史已吸收/替代的收尾，不是重新交付17份新功能。

## 历史归并理由

| 历史组 | 依据与处理 |
| --- | --- |
| 旧Cursor图层 | git cherry确认补丁等价，当前已含修订版本 |
| 旧flow/share | 4份核心文件与813b198同内容；旧迁移接e609，当前接h9，禁止倒退挂靠 |
| Vue/P0–P4 | DELIVERY_P0_P4已记录吸收7adfbc0，main9a0ca18后继续修改 |
| v1.0.1 | 旧静态readiness/初始化已由224b59f与workspace/data_sources.py审计路径替代 |
| unified-shell | 旧静态账户/0.8.4戳由Vue及A-U1–U3替代 |
| 导航修复 | 主线3a8f97f/11fb295收敛，不恢复旧壳 |
| v102–v106 | 主要为历史验收、交接、一次性工作流；保留历史，不恢复临时工作流 |
| etf-next-stage | 同名对账已被最终接受更新，旧文档会把M0倒回未验收 |

17个refs：codex/etf-next-stage、codex/v1.0.1、cursor/chart-research-layers-5ad7、cursor/etf-flow-share-free-data-fe2d、docs/etf-workspace-vnext-20260906、docs/project-handoff-20260906、feat/etf-workspace-vue-20260906、feat/unified-shell、feat/workspace-p0-p4-20260906、fix/task-driven-navigation-20260905、fix/v080-navigation-simplification、fix/v081-navigation-compat、fix/v1.0.2-overview-integration、fix/v102-home-template-20260908、fix/v103-history-research-20260909、fix/v105-data-paths-ui-20260910、fix/v106-postdeploy-20260914。

历史归并后git diff确认backend/frontend/bridge/config/scripts运行代码未改变。该判断不把“git cherry +”误当遗漏功能；移植、重写与迁移挂靠必须按内容和合同核对。

## 文档与目录简化

- README/START_HERE/STATUS/HANDOFF/docs地图收拢为当前入口；旧长账本原文归档。
- 9份旧根交付说明/manifest/覆盖删除清单及历史校验脚本移入 `docs/archive/project-simplification-20261002/legacy-delivery`。旧manifest不再作为当前源码验证入口。
- CODEX_DEPLOYMENT_TASKS改为当前简洁检查清单，保留数据库浏览器认证合同；旧原文归档。
- 旧SELF_SUBMIT和14:30接收原文归档，原位置保留当前引导；更新旧handoff相对链接。
- 清除backend再生Python缓存和根pytest缓存，删除4份哈希一致的docs-dump重复副本。

保留fund_decision.sqlite3、backups/reports/deployment_reports、evidence、发布镜像及恢复证明、所有NOTICE/许可证、开发依赖和含未提交文件的旧工作区。项目外C盘工作区不在本轮递归清理范围。

## 验证

进度生成/一致性检查通过。最终合并树的后端回归、compileall、Node检查、前端验证与GitHubmain核对结果待本轮验证后追加；本轮未部署生产或进行数据资格探测。

## 最终检查结果

全量收集1425：初次1393通过、22条件跳过、10测试路径阻挡。默认C盘临时目录权限失败的初始尝试已中断；项目内临时目录又正确触发仓外私有文件安全合同。改用明确可写的仓外合成临时目录专项复验13项：12通过、1Windows条件跳过；其中原10项9通过，1项POSIX权限检查按平台跳过。最终唯一覆盖为1402通过、23条件跳过。未改业务代码或测试断言，也不把初次报告写成单次全量PASS。

前端71/71；typecheck、build、compileall、legacy Node语法、进度一致性检查通过。构建仅有既存Login动态/静态导入提示。测试Python3.13.14，非新一轮Windows/Linux CZSC语义资格。XML与摘要保存在.local/consolidation-20261002。

## 保留的清理边界

两个本轮合成测试目录pytest-temp-bridge-check与pytest-temp-main-final被Windows拒绝访问，原生删除与当前用户权限恢复均未成功，因此保留在.local/consolidation-20261002，未扩大所有权或系统权限。仓外合成临时目录已删除，编译后14个Python缓存目录已再次清除。XML与改动快照保留。开发依赖、用户数据库、备份/报告、发布镜像及含未提交文件的旧工作区均不删除。

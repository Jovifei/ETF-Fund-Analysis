# 当前任务

## 2026-10-11 本地真实计算→网站展示（本轮仅规划）

- [x] 核现有Mock-only与云端consumer缺口；保护Owner文件。
- [x] 阅读主源开源参考，确定SQLite/现有Adapter/Windows优先，不新增重型平台。
- [x] 网页端独立提案→Codex详细草案→网页实际复议，合并三个合同及迁移顺序。
- [x] v2最终复核、保存共同方案和执行Agent prompt交Jovi；网页结论APPROVED_FOR_EXECUTION_HANDOFF，未实施。
- [ ] 另一个执行Agent按A–G实施并真实公网/网站验收；本轮不执行。

方案：tasks/plans/2026-10-11-local-live-to-website.md；接力：docs/handoffs/LOCAL_LIVE_TO_WEBSITE_EXECUTOR_20261011.md。旧源码测试不是本计划新实现验收。

最终目标与全部阶段任务保留在[总路线](../docs/PROJECT_MASTER_ROADMAP.md)和[进度台账](../docs/PROJECT_PROGRESS.json)；本文件只列当前交付及尚未完成的关键门槛。

## 图表方向与价格口径

- [x] 用同一kind/type精确三态方向解析连接画线、图例和依据；未知不推断方向。
- [x] 在原始/研究价格不匹配时移除研究趋势线，保留原始数值、成交量、成本及合法研究/同口径趋势线。
- [x] 保存RED/GREEN、196前端、1762后端/11跳过、独立138项/30投影边界及类型/构建证据。
- [x] 精简状态文档；保持全部实现、测试和本批审计字节，JSON生成MD/HTML。
- [x] 必要前端依赖安全更新：Vue3.5.42/Vitest4.1.11/source-map-js1.2.2，隔离196前端/类型/构建通过，audit0高危/严重/中危。
- [ ] 原分支新候选非强制发布与精确三项CI（包括完整浏览器门槛）。
- [ ] 趋势修复的新浏览器截图及实际交互验收，不继承方向显示两例旧浏览器证据。
- [ ] 当前部署身份/回退条件核验、部署和正常线上验收。

证据：[方向显示](../docs/audits/S4_U08_SR_DIRECTION_DISPLAY_20261005.md)、[趋势价格口径](../docs/audits/S4_U09_TREND_PRICE_BASIS_20261005.md)。

## 持续关键路径

- [ ] S8-F0真实5m/15m访问权限、存储许可、量额单位、时间/PIT与有界可行性验证。
- [ ] 正常私有读取/R10及实体手机验收；平台健康、Mock或桌面模拟不能替代。
- [ ] 当前实现与历史阶段证据映射；131个任务五维状态与13项历史发布清单不自动晋升。
- [ ] 方向形成后按总路线安排S4补缺与S5–S7价值顺序，不因一次修复扩大范围。

资格保持UNKNOWN、actionable=false、calibration_status=not_calibrated；自动交易和运行时激活保持关闭。未修改业务数据或历史Git提交。
# Owner-authorized local execution with remote review —2026-10-11
Jovi explicitly authorizes local code implementation/tests; webGPT reviews actual fixed GitHub source and decides next stages. Previous receive-only rule replaced for this stage. Root/other AI work preserved; independent codex/local-execution-20261011 from e722ad5. No live providers, private data, production deployment or automatic trading here.
- [x] Isolate source and clarify single writer to remote Chat.
- [x] Failure-first sector evidence cutoff/mock/unit/source/freshness contract repair; old core/sector contract summary blocking.
- [x] Disabled shadow local compute/export + bounded content-addressed atomic sync + scoped HMAC auth + expiry/replay/order gates + Windows scheduling implementation.
- [x] Primary-source open-source assessment and existing-code reuse mapping; preserve licenses.
- [x] Independent review and affected regression/static/frontend checks; inspect aggregate diff. Final fullf514 backend1851 PASS/23 SKIP/0 FAIL;198 Vue and exact PR-event CI workflows PASS.
- [x] Commit phased actual source; GitHub PR45 delivery; webpage review accepts disabled1d boundary, no deploy recommendation.
- [x] Publish final consolidated test receipt and fixed-SHA receiver instructions after final full test result.
- [ ] Separately qualify long-lived scheduled jobs, public staging HTTPS and real provider/data rights before production cutover.
Current tests frome722 baseline are55backend+197frontend PASS, not reused as new candidate result. Source transport6908544 is docs-only and not merged here.

Review: fixed implementationf514a6e/treeba18dbfe, owner state preserved; one-time Windows offline task and actual local TLS/restart replay proof passed. Full120 affected backend and198 Vue passed, full1595 backend1825/23 recorded by exact identity. Detailed result boundaries and preserved failures: docs/audits/LOCAL_COMPUTE_IMPLEMENTATION_20261011.md. New architecture remains default disabled, Mock-only,1d-only; no production claim.

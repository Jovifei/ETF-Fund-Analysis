# ETF 项目接力 — 2026-10-03

## 1. 最终目标
个人中国 ETF/LOF 研究工作台：交易日14:30输出同一冻结证据支持的结论、结构位、新闻和成立/失效条件；明确时间、来源与缺口。有效预测须经真实PIT、样本外与人工审查；不连接券商、不自动交易。资格不足保持 UNKNOWN / actionable=false / not_calibrated。

## 2. 已完成
- 本轮已读AGENTS、STATUS、HANDOFF、两旧会话及Obsidian项目进度；Obsidian仍是2026-09-27历史记录，不用作当前验收。
- S2九模块可用性面板：abae131；2026-10-02发布收据记录三服务镜像38c2c13c、schema f0；完整pytest退出0、1432收集、前端73等为旧收据证据，本轮未重跑或现场查生产。
- F0 fixture校验和离线编排已有实现；真实上游探测NOT_RUN。
- 远端最新候选587b13611ed4e37e8cf20200c80ac67d4611ed00包含F0离线编排、CI性能、Chan日历坐标与前端构建fixture修正。以当前新候选为接收对象，不重复已完成实现。

## 3. 当前卡点
- 当前main 489e4aa；隔离执行分支已按Jovi本轮授权快进至587b136；本轮fetch确认远端分支已到587b136，已接收代码。本轮用户要求后续新增代码变更前另行授权，不能沿用旧实现授权。
- 本轮GitHub官方API已核实587b136三工作流success：ci 37049326501、workspace-ci 37049326743、audit-platforms 37049326639；不可变镜像与本地接收仍需核实。
- S2正常账户私有详情、实体手机、R10同次GET零副作用及最终验收仍待证据。
- F0项目ETF分钟访问权限、许可/存储条件、时间/PIT语义待确认；官方文档能力不等于项目权限。不要索取凭据。
- 上次发布磁盘97%为历史收据，未现场复核；不自动清理备份/回滚镜像。

## 4. 关键文件
根契约与路线：AGENTS.md、STATUS.md、HANDOFF.md、docs/PROJECT_MASTER_ROADMAP.md、docs/PROJECT_PROGRESS.json、docs/REMOTE_LOCAL_RELAY.md。
隔离路径：E:/project/ETF-Fund-Analysis/.local/remote-stage-acceptance。
S2：backend/app/workspace/detail_availability.py、read_model.py、frontend/src/components/AvailabilityMatrix.vue、frontend/src/views/Detail.vue；docs/audits/S2_AVAILABILITY_RELEASE_20261002.md。
F0：backend/app/providers/f0_minute_probe.py、远端新增f0_minute_probe_runner.py及相关测试；docs/audits/S8_F0_TUSHARE_EVIDENCE_20261002.md、S8_F0_SOURCE_MATRIX_20261002.md、S8_F0_OFFLINE_ORCHESTRATION_20261002.md。
新候选：frontend/src/lib/chartAdapter.ts、frontend/tests/fixtures/chan_chart_projection.json；docs/audits/WU2_CHAN_CALENDAR_PROJECTION_20261003.md、CI_PRICE_STRUCTURE_PERFORMANCE_20261003.md。

## 5. 下一步（待远端制定）
请远端先确认连接workspace_info为本项目，读取本文件、当前Git树和远端587b136收据，给少量明确执行项：优先精确候选CI/源码接收与风险适配验证，再安排已部署私有/手机验收及F0访问证据。分别列出无需修改代码可立即执行项、需Jovi授权的具体文件/代码范围、数据权限或人工门槛。
远端本轮仅规划/审查，不提交代码；本地执行已授权的只读验证和文档。任何代码修改/接收新代码先征询Jovi，保持改动简洁。不部署、不采购、不读秘密、不写生产库、不晋升资格。

来源：两指定会话、2026-10-03当前Git fetch及文件读取；历史测试/发布明确继承自2026-10-02/03收据。本轮新测试NOT_RUN。远端方案PENDING_REMOTE_PLANNING。



本轮本地接收验证：587b136工作树干净；F0 fixture/runner、Chan overlay、price structure四文件pytest退出0；前端102项PASS，typecheck PASS；compileall、Node语法、进度生成一致性PASS。完整后端1484/11为GitHub证据，本地全量NOT_RUN。

本輪补充：前端build PASS；GitHub精确CI生产镜像artifact 11247265158（production-image-37049326501）存在且未过期，未下载/未部署。候选可交本地接收不等于生产验收。

## 远端方案与执行结果（iteration72）
方案聊天：https://chatgpt.com/g/g-p-6a8f03c9d1408191a10f13a02b09ce43-ji-jin-jue-ce/c/6ac07d80-2080-83e9-a405-080b766e57fc
远端确认本项目、隔离分支587b136及实际快进记录；本批次以接收/证据为主，不重复实现。
1. RO1精确候选接收：Jovi后续明确授权拉取，已ff-only接收；工作树干净，tree 1856fee055dd17da81054325d4039a036ff0c6f3。全文件清单CANDIDATE_587b136_MANIFEST.txt。三CI及完整CI逐步骤（含镜像构建/smoke/inventory/export）成功，本地前端102/聚焦后端/静态检查通过。镜像产物存在；内容内的源码tree/image/schema/version尚未下载核验，G1完整产物绑定仍PENDING，不标发布PASS。
2. RO2私有/手机：当前可见内置浏览器只有规划聊天，无既有生产已登录页面。正常账户详情、同GET八聚合计数R10、实体手机NOT_RUN；需要正常登录和设备证据，不绕过鉴权、不取凭据。
3. RO3数据证据：本轮重读官方etf_mins文档，文档仅称trade_time交易时间；未取得项目实际权限、适用存储/许可、bar闭合/发布时间/PIT保证。真实请求NOT_RUN，UNKNOWN/actionable=false；不采购，不启用Provider。
后续代码修改必须具体列文件并先获Jovi授权；本轮拉取授权已执行，不重复征询。主目录main未整合候选，生产未部署。

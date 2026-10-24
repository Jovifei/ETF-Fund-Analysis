# 2026-10-24 下一远端大阶段输入：可信消费与安全门整合

状态：Jovi 已于 2026-10-24 授权本文所述**完整整合阶段**及限仓库 GitHub 独立分支提交。本文是只读对账后的阶段输入；授权不包括合并 `main`、生产切换或修改私有数据。

## 五项精简接力

1. **最终目标**：个人 ETF/LOF 研究网站，本机真实采集与确定性计算，网站读取有界、可追溯、同批的研究结果；来源/时间/许可/PIT/OOS/校准未合格时保持研究用途，人工决定行动，不接券商、不自动交易。总路线见 `docs/PROJECT_MASTER_ROADMAP.md`。
2. **已经完成**：`main` 仍为 `1a4b6652f49c412145d12812fa02820ba0a80991`。Draft [PR53](https://github.com/Jovifei/ETF-Fund-Analysis/pull/53) 在独立分支提交可信历史接收、有界固定代读取、页面同代与失败状态，经过两轮本地复审后固定 head `fdaf5426585d64800dbff60656797cd75306f19e`、tree `6c2450558b2f862e4fc5fbd6929a1999c6ae7d33`。同 SHA 的完整 `ci`、audit-platforms、postdeploy-ci 成功；本地受影响八个后端模块149/149、Vue218/218、类型/构建和受控认证浏览器1/1通过。证据见 `docs/audits/PR53_LOCAL_ACCEPTANCE_20261024.md`。
3. **现在卡在哪里**：PR53 的 `workspace-ci` 仍因 Vite 7.3.5 所在依赖安全门失败，后续前端/浏览器 CI 跳过；本地全量 pytest 两次进程中断，没有本地全量 PASS。Draft [PR51](https://github.com/Jovifei/ETF-Fund-Analysis/pull/51) 的 `e121b13` 将 Vite 精确升至 7.3.7，安全门已越过，但其最新整合 head `f6d0d332ab8bd27f34cb573b31a141f32cc57bac` 在受控认证浏览器的 `market-context-status` 断言失败；它已合入 PR53 的 `f89b382`，**尚不包含** PR53 后续 `fdaf542` 的容量夹具修复。两份候选不能直接宣布组合通过。[GitHub 官方安全公告](https://github.com/advisories/GHSA-587h-7wmj-h5pm)列 Vite 7.3.6 及以下受影响、7.3.7 为修复版。Draft PR52 是文档整理分支，基于较早的 `e121b13`，须独立保护。
4. **关键文件/证据**：`AGENTS.md`、`docs/REMOTE_LOCAL_RELAY.md`、`docs/handoffs/REMOTE_LONG_STAGE_20261023.md`、`docs/audits/PR53_LOCAL_ACCEPTANCE_20261024.md`；PR53 的 `backend/app/workspace/{local_display_read.py,api.py}`、`frontend/src/{lib/query.ts,views/Overview.vue}`、`backend/tests/test_display_cache_rolling.py`、`frontend/e2e-auth/local-display-consumption.spec.ts`；PR51 的 `frontend/package.json`/`package-lock.json`、`frontend/src/components/ContextReadStatus.vue`、市场上下文展示与收盘日线修复及其测试。[PR51 `workspace-ci` 失败 job](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/39989623066/job/120537697920)已越过 npm 高危门，失败在受控认证页的 `market-context-status` 断言。源码对账显示：PR51 的 `Overview.vue:110` 仅在市场上下文响应含 `read_contract` 时渲染该状态，而当前模拟响应缺此字段；修正后还须处理测试第29行仍点击指数历史入口的问题，因为 `indexHistoryAvailable` 在 `local_bundle` 模式为 false。先用失败测试验证是否只需更新夹具，勿直接改正确的只读产品门槛。
5. **下一步**：远端在**一次完整阶段**中独立审查 PR51/PR53/PR52 与当前 `main` 的实际提交链，保留已有修复，选择独立整合分支（不重写其他 Agent 分支）；在精确源码上合入 PR53 的最终 `fdaf542` 变化及 Vite 7.3.7 安全修补，失败测试先行定位并修复认证浏览器合同，完成前后端/构建/安全门/浏览器/全量 CI、自审与固定 GitHub SHA/tree 交接。PR51 的 `test_display_cache_rolling.py` 已包含 `max_generations=3` 与 `os.replace` 原子写入瞬间峰值检查，**不可用 PR53 的整文件覆盖**；需保留更强断言并吸收必要的容量/hold 覆盖。本地再按新 SHA 独立接收。真实生产登录、收盘采集、自然调度和数据资格单列，不能从 CI 推断通过。

## 已授权的边界与交付

- 允许范围建议：独立 `codex/` 整合分支中的 `frontend/package.json`、`frontend/package-lock.json`；PR51/PR53 重叠的展示 Reader/API/市场上下文与相关前端状态/只读操作；受控认证浏览器断言及对应后端/前端回归；必要的阶段审计和交接文档。以最小差异完成组合，不新增 Provider、不动 `config/strategy.json`、生产配置、账户持仓或数据库。
- 开始前先核对 GitHub 三个 PR 的**最新** head、base、tree 和并行更新；若 PR51/52 已被他人推进，以新证据调整方案，绝不 force-push 或整文件覆盖。第三方 NOTICE 保留，依赖仅做经官方公告证明的必要安全修补。
- 完成条件是实际 GitHub 独立分支/PR 的固定 SHA/tree、差异审查、同一源码的完整 `pytest -q`、`compileall`、静态 JS、Vue 单测/类型/构建、`npm audit --audit-level=high`、受控认证浏览器及精确 CI 全部留痕。失败和 NOT_RUN 明列；不得用 PR51 或 PR53 各自的绿灯拼成组合通过。生产部署、正常真实账户网页、实体手机、两个真实交易日及 S8 来源/PIT/OOS/校准不在自动验收范围。
- 如平台的远端写入、CI、依赖安全门或文件权限受阻，记录具体动作和证据，在同一任务内恢复；不要把计划、文档或测试绿灯称作已提交实现。每次交付至少给 base/head SHA、tree、PR、改动文件、实际检查、未过门槛和本地接收指令。

## 本阶段完成收据（2026-10-24）

远端在独立 Draft [PR54](https://github.com/Jovifei/ETF-Fund-Analysis/pull/54) 完成跨 PR 整合、受控浏览器合同修复及后续 Windows OCR 测试隔离整合。固定 head `b98d68390072f31591b983ed54fb1d8bf29d7c4d`、tree `9f533cfb18be657fdb5cef54b8c458b1a0952322`；双父为本任务 `0b63ce4` 与 PR52 `109253e8`。`main` 仍 `1a4b6652f49c412145d12812fa02820ba0a80991`，PR 未合并、未部署。相对前一候选 `0b63ce4`，生产 `backend/app`、`frontend/src`、前端锁文件无改动；新增源码仅为 Windows OCR 测试目标及其引用，另有审计文档。

同 head 的两组完整 `ci`、两组 workspace 合同及跨平台/后续测试 GitHub 检查全部 SUCCESS。本地 Windows 全量 `pytest -q` 退出码 0，JUnit 2,614 PASS / 24 SKIP / 0 FAIL / 0 ERROR；Vue 228 PASS、类型/构建、受控认证浏览器 1 PASS。精确日志、旧候选与新候选界限见 `docs/audits/PR54_LOCAL_ACCEPTANCE_20261024.md`。PR 正文顶部已补最终固定 SHA 与本地收据并经插件读回；较早 `0b63ce4` 内容为历史。

代码整合阶段可接收；生产正常登录、实体手机、真实收盘及自然两个交易日、来源许可/单位/时间/PIT/OOS/校准仍须独立验收。`UNKNOWN`、`actionable=false`、`not_calibrated` 不变；后续代码范围须由 Jovi 再授权。

# PR53 本地独立接收记录

状态：**CHANGES_REQUIRED**。本记录核对远端 Draft PR53 的候选 `bdf3dd0caa07b37c9bdda3ddc02c5bda1e9a2f02`，不是部署或合并批准。远端修复提交出现后须重新绑定新 SHA 与测试。

## 固定身份与保护范围

- GitHub PR：[可信历史接收与有界同代消费](https://github.com/Jovifei/ETF-Fund-Analysis/pull/53)，Draft、未合并。base `1a4b6652f49c412145d12812fa02820ba0a80991`；候选 head `bdf3dd0caa07b37c9bdda3ddc02c5bda1e9a2f02`；tree `a00e620cd0ccb8578853795f3eb42a5033c97b94`。本地 Git 对象和 E 盘隔离接收树均已核同一身份。
- 隔离检出：`E:\project\ETF-Fund-Analysis\.local\c2c-a7f2-acceptance-20261023`，detached HEAD。根 `main` 的 `tasks/todo.md`、`tasks/lessons.md` 和本轮未跟踪交接文档保留；旧 `.local/remote-stage-acceptance` 中未跟踪的网页证据未触碰。
- 远端首个 `8ee2daacb2066fb541cddd3524c0cb99b825ad3b` 只新增失败复现测试；`bdf3dd0` 才是首轮实现候选。

## 本地实际运行

| 检查 | 结果 | 边界 |
| --- | --- | --- |
| `pytest -q` 五个模块：`test_local_display_consumer_contract.py`、`test_receiver_safety.py`、`test_local_display_bundle_cache.py`、`test_optional_panels.py`、`test_cadence_cli.py` | PASS，进程退出 0 | 聚焦回归，不代表全量 |
| `pytest -q backend/tests/test_display_cache_rolling.py` | **1 PASS / 2 FAIL** | 两个容量滚动用例均在 `_budget_plan` 抛 `store capacity exceeded`，本机独立复现 CI |
| `npm --prefix frontend test` | **26 files / 210 tests PASS** | 使用原项目同锁文件的现有 `node_modules` Junction；未下载新依赖 |
| `npm --prefix frontend run typecheck`、`npm --prefix frontend run build` | PASS | 编译产物仅在隔离树 |
| `python -m compileall -q backend/app`、`node --check backend/app/static/app.js`、`git diff --check base head` | PASS | 静态检查 |

## 独立审查发现

1. **P2：合法大序列的固定代读取失败。** `backend/app/workspace/local_display_read.py` 的新选择器对 64 位纯数字优先按完整哈希匹配，对超过 64 位的数字拒绝；`local_display_contract.py` 发布校验只要求正整数。于是可接收的包能在无参数总览显示，却不能由子面板用该 generation 固定读取。需统一发布与读取边界，并给 64 位、65 位及歧义输入做回归。
2. **P2：主动重新读取可能复用旧请求。** `frontend/src/lib/query.ts` 对同 URL 合并在途自动读取和用户主动 reload。若新代在自动 GET 发出后发布，用户点击重新读取仍可得到旧代。主动操作应发新请求；注销 epoch、401 与旧响应隔离仍须保留。
3. **CI 阻断：新增接收历史扩大指针峰值。** `local_display_read.py` 把逐代增长的接收证明写入 latest/previous 指针。`test_display_cache_rolling.py` 的旧合成固定元数据余量已小于当前真实峰值；分块路径还需计入 staged body 与 1,024 B 收据预留。本地和全量 CI 均复现两例失败。不能从 `used_bytes` 扣除实际仍在盘上的数据来造 PASS。应按真实指针/临时文件/暂存峰值更新合成余量，并以 `max_generations=3` 等明确条件继续强制检验旧包回收、current/previous 保留及用量不超限；生产 64 MiB/320 MiB 门槛不变。

这些问题已送回同一远端任务 `c2c_a7f2` 的 PR53 修复回合；第三项容量根因也已本地核对并回传。

### 后继候选 `f89b382` 的增量接收

远端先以 `850c007aea5a4f453ec6265a991d01593ce3dc79` 补两项 P2 回归，再以 `f89b3826b637df95e0310a5fdb2a36e21912f9b8` 修复；本地隔离树已检出该 SHA，tree `309bb523b5c8d793e8f15b05a51bdae66d707e6d`。独立运行 `test_local_display_consumer_contract.py` 与 `test_receiver_safety.py` 均 exit 0，`query.test.ts` 8/8、Vue 类型检查和增量 diff check PASS。该后继提交只改固定代选择器、主动重读及其测试/收据；P2 边界的本地复核通过。

同一 SHA 再跑 `test_display_cache_rolling.py` 仍为 **1 PASS / 2 FAIL**，与全量 CI 旧 SHA 的两例一致；本记录状态继续 **CHANGES_REQUIRED**。已向同一远端任务回传真实峰值分析与测试夹具要求。等待下一个固定提交后重跑完整门槛，不能把 `bdf3dd0` 的全量前端结果继承为后继 SHA 的完整结果。

### 容量回归修复候选 `fdaf542`

远端在同一 PR53 分支提交 `fdaf5426585d64800dbff60656797cd75306f19e`，父为 `f89b382...`、tree `6c2450558b2f862e4fc5fbd6929a1999c6ae7d33`。GitHub ref、本地对象与隔离树一致。该提交仅修改 `backend/tests/test_display_cache_rolling.py`：合成夹具增加接收历史指针的元数据余量，`max_generations=3` 仍强制第四代后回收旧缓存，并继续断言 `used_bytes<=cap`、current/previous 保留及 chunk hold 释放。生产预算与核算代码未改。

本地绑定此 SHA 已运行：容量滚动测试 **3/3 PASS**；八个受影响后端模块 **149 PASS / 0 FAIL / 0 ERROR / 0 SKIP**（JUnit：`E:\Claude_allow\Download\ETF-PR53-local-acceptance-20261024\focused-pytest-fdaf542.xml`，SHA-256 `0f4368520628be3e185feb50ed31b82cf788bd2da4d3ab622fa8bcdf38246dd2`）；Vue **27 文件/218 测试 PASS**；类型检查、构建、Python compileall、静态 `app.js`、base→head diff check PASS。受控认证 Playwright `local-display-consumption.spec.ts` **1/1 PASS**，可见同代固定读取、可选面板的缺口文案和只读操作入口；这是合成包与测试账号，不是生产正常用户或真实手机。

本地完整 `pytest` 两次尝试均**INTERRUPTED**：首轮执行会话中断；第二轮后台记录到约 22% 后进程终止，没有退出码或 JUnit 文件。因此没有本地全量 PASS 结论；受影响模块的本地 149 项与 GitHub 同一 SHA 的完整 `ci` SUCCESS 是两层独立证据。

新 head 的 [完整 ci](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/39987919133) 与 [audit-platforms](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/39987919123)、[postdeploy-ci](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/39987919423) 已独立核为 SUCCESS；[workspace-ci](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/39987919102) 仍因既有依赖安全门 FAIL，后续前端/浏览器检查 SKIPPED。故本地候选源码可继续审查，整体验收/合并/部署仍未通过。

## CI 与下一接收门槛

- [audit-platforms](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/39978140792) PASS；[postdeploy-ci](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/39978140911) PASS，此名称不代表部署。
- [workspace-ci](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/39978140791) FAIL：依赖安全门检出 1 个 high，后续前端和浏览器门槛 SKIPPED。`frontend/package.json` 与锁文件在 base/head blob 相同，本 PR 未改依赖；仍不能说 CI 全绿。
- [全量 ci](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/39978140814) FAIL：[test job](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/39978140814/job/120498210360) 的两例容量回归失败，后续编译、扫描、迁移和镜像检查 SKIPPED。`f89b382` 的新全量 CI 尚须按它自己的 run 结果另核，不继承此旧 run。
- 当前固定候选为 `fdaf542...`；本地全量测试中断已如实记录，既有依赖安全门仍需独立修复范围和验证。正常登录用户、真实手机、自然调度/两交易日、数据来源与 PIT/OOS 资格仍单列；本轮未合并、未部署。

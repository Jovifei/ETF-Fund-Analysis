# PR54 独立接收记录

状态：**CODE_ACCEPTED / RELEASE_PENDING**。固定源为远端 Draft PR54 `b98d68390072f31591b983ed54fb1d8bf29d7c4d`、tree `9f533cfb18be657fdb5cef54b8c458b1a0952322`。这不是合并或部署批准；若 head 再前进，需重新验收。

## 最终提交与独立复核

- PR54 已前进到 `b98d68390072f31591b983ed54fb1d8bf29d7c4d`，tree `9f533cfb18be657fdb5cef54b8c458b1a0952322`。这是 `0b63ce4` 与并行 PR52 新 head `109253e8` 的双父合并；本地隔离树已切到此 SHA，根 `main` 保持原状。下文 `0b63ce4` 结果是前一候选收据，不能冒充新 head 的完整验收。
- 新增源码差异集中在 Windows OCR **测试**：把轻量 spawn target 移到 `backend/tests/_ocr_workers.py`，`test_holding_import.py` 引用该目标并保留 2 秒 deadline。其余新增差异是项目文档；`git diff --check main..b98d683` 通过。
- 本地 `b98d683` 的 OCR 定点用例 **1 PASS**，整份 `test_holding_import.py` **67 PASS / 2 SKIP / 0 FAIL**；先前误用系统 Python 曾因缺少 `sqlalchemy` 无法载入 `conftest`，随后改用项目 `.venv` 成功。JUnit 位于 `E:\Claude_allow\Download\ETF-PR54-local-acceptance-20261024\holding-import-b98d683.xml`（SHA-256 `7b8b120850159f247512eb465388be6ae74ef2af3c767562e0d22f8ab6f75cb1`）。这不等于重新运行全量测试。
- 同 SHA 的 Vue 单测 **28 文件/228 PASS**、类型检查、Vite 7.3.7 构建通过；受控认证 `local-display-consumption.spec.ts` **1 PASS**，只证明合成包和测试登录。首轮浏览器启动因机器未装 Playwright 自带 Chromium 失败；明确指定已安装 Chrome 后，在独立临时目录重跑通过，未改测试源码。
- `git diff --quiet 0b63ce4 b98d683 -- frontend/package-lock.json frontend/package.json frontend/src backend/app` 退出 0：本次新合并未改生产源码或前端锁文件；旧候选与新候选的结果仍分 SHA 记录。
- **Windows 完整 `pytest -q` 已结束，退出码 0；JUnit 共 2,638 项，2,614 PASS / 24 SKIP / 0 FAIL / 0 ERROR。** 精确结果 `E:\Claude_allow\Download\ETF-PR54-local-acceptance-20261024\full-pytest-b98d683.xml`，SHA-256 `3fc2962a2e754b2ef72e3f1d702a0584724d52c0c4da4afbd6a72dd08128d563`；运行日志和退出码同目录保留。这是本地 Windows 全量证据，不是生产/真实数据验收。
- GitHub 插件与 `git ls-remote` 独立核实 PR54 仍是 Draft/open、未合并，base `main` 固定 `1a4b6652f49c412145d12812fa02820ba0a80991`、head `b98d683`。同 SHA 两组完整 [ci A](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/40055246896)、[ci B](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/40055242746) 均 SUCCESS；两组 workspace 合同、Windows bridge/PostgreSQL、Windows archive/followup 均 SUCCESS。重复完整 CI 的镜像构建、烟测、产物步骤已结束成功。PR 描述顶部现已补最终固定 SHA/本地收据并读回；下方较早 `0b63ce4` 内容明确标为历史。

## 前一候选 `0b63ce4` 的接收证据

- [PR54：整合与认证浏览器修复](https://github.com/Jovifei/ETF-Fund-Analysis/pull/54) 在前一候选 `0b63ce4bf0d468d5b816017ff3ee785ca4eebb55` 的 tree 为 `6d73b84b65782ddd2de79f2653bb34ae649f606b`；这些结果只对应当时 head。独立分支仍为 `codex/c2c-6b31-integrated-20261024`，`main` 仍是 `1a4b6652f49c412145d12812fa02820ba0a80991`。
- `0b63ce4` 是双父提交：第一父 `fac4d2b0d9aea12b5869b5b27d5b479ae74f5a20`（本任务失败证据及受控 E2E 修复），第二父 `82916e5acc9d036606b1bcd84bc0a9d17f9c690f`（并行 PR52 的更新）。相对第二父仅改容量回归测试并加审计/交接文档；原 PR51/52/53 分支未由本地改写。
- PR51 的 Vite 7.3.7 安全补丁在此候选祖先内；PR51 更强的 `watch_atomic_peak` 夹具保留，增量仅补 `used+held<=cap`、精确保留代数及 hold 释放。认证 E2E 模拟响应补 `read_contract`，本地模式断言无指数历史入口与零 K 线请求，未降低同代和零写入要求。
- 本地在 `E:\project\ETF-Fund-Analysis\.local\c2c-6b31-acceptance-20261024` detached 检出同一 SHA/tree，工作树无已跟踪修改；根 `main` 的未提交文档与旧接收树证据保留。

## 本地实际运行

| 检查 | 结果 | 边界 |
| --- | --- | --- |
| 精确锁文件 `npm ci` | PASS，Vite 7.3.7；缓存/下载在 `E:\Claude_allow\Download\npm-cache-etf-pr54` | 仅隔离树安装；尚有 1 low、2 moderate |
| `npm audit --audit-level=high --prefix frontend` | PASS，退出 0 | 高危阈值，不表示零漏洞 |
| Vue `npm test` | **28 文件/228 测试 PASS** | 同一候选 head |
| Vue `typecheck`、`build` | PASS | 先构建 `workspace_dist` 再跑浏览器 |
| 八个受影响后端模块 | **126 PASS / 0 FAIL / 0 ERROR / 0 SKIP** | JUnit `E:\Claude_allow\Download\ETF-PR54-local-acceptance-20261024\focused-pytest-0b63ce4.xml`，SHA-256 `85b835496089c36a0b6ef1a9f5ea484f99ff3019ee575b3603f1c9ecbbc2a46a`；聚焦，不是全量 |
| 受控认证 `local-display-consumption.spec.ts` | **1 PASS** | 合成包/测试账号；非生产正常用户 |
| Python compileall、静态 `app.js`、base→head diff check | PASS | 静态检查 |

首次本地受控 E2E 在登录页定位前超时；隔离树当时未生成 `backend/app/workspace_dist`。完成前端构建后，用独立临时目录重跑同一测试 **1 PASS**。保留首轮失败，不把测试环境准备缺口称作生产产品故障。

最终代码接收：`b98d683` 的固定分支、GitHub 全部当前检查、Windows 全量与受控网页均通过；复审未发现新增生产代码差异。真实生产账号、实体手机、实际收盘/自然调度和两个交易日、来源许可/时间/单位/PIT/OOS/校准尚未由本阶段证明，继续 `UNKNOWN / actionable=false / not_calibrated`。不合并、不部署。下一步是按项目路线另行安排这些真实环境门槛，并在任何新代码阶段前取得 Jovi 的具体授权。

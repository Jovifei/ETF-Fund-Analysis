# OPERATIONS — 每次提交/收尾必须执行的步骤 + 错误记录

> 本文档是**必须执行的**。每次提交（或每个阶段收尾）前过一遍第一部分；每次遇到编译/测试/部署错误，把根因和解决方案**追加**到第二部分的记录表里，供后续会话直接复用。
> 建立：2026-11-07（docs 重组会话）。治理边界以 [AGENTS](AGENTS.md) 为准，本文不放宽任何门禁。

## 一、每次提交前必须执行（按顺序，全部通过才能提交）

```bash
# 0) 环境确认——必须用项目 venv，系统 Python 缺 sqlalchemy 等依赖会造成假失败
.venv/Scripts/python.exe --version && .venv/Scripts/python.exe -m pytest --version

# 1) 全量测试门（AGENTS.md 规定）
.venv/Scripts/python.exe -m pytest -q

# 2) 编译门
.venv/Scripts/python.exe -m compileall -q backend/app

# 3) 前端语法门
node --check backend/app/static/app.js
```

附加规则：

1. **版本联动**：改 app 版本号时，四处联动 + CHANGELOG 必须同步（`test_release_version` 会锁定这一点）；没升版本的策略修改不提交。
2. **策略类改动**（指标/特征/权重/阈值/门控/字段口径）必须升版本并跑 AGENTS.md 的策略门；**禁止**为单次回测结果自动调阈值。
3. **文档移动**后必须跑相对链接检查（本仓库曾用脚本扫描 `](...)` 相对链接并核对目标存在）；`docs/` 中被程序/测试/配置引用的"承重文件"路径不得改动（清单见 [docs/README.md](docs/README.md)）。
4. **git 纪律**：`git pull --ff-only`；不在 main 上直接开发；提交前 `git status` 确认没有把别人的未提交修改（如其他会话的 AGENTS.md 草稿）一起打包。
5. **数据口径冲突**（复权/单位/时间）→ 停止信号生成，不做猜测；Mock 数据结果必须阻断 actionable。
6. **Hub 报告**：阶段收尾、阻塞出现时按 AGENTS.md 的 hub 块用 `bound_report.py` 上报；连接失败保留 pending JSON、停止自动重试并明示错误。

### 部署上线（每次发布按此顺序，2026-11-08 实战验证）

```bash
# 1) 前置：main CI 三 workflow 全 success；确认 alembic head 与生产库一致
.venv/Scripts/python.exe -m alembic heads          # 对比生产 alembic_version

# 2) 备份（先备份再切，不可跳过）
#    服务器：pg_dump -Fc → sha256 → pg_restore -l 验证 TOC 条数

# 3) 本机构建镜像（服务器内存小、多项目共存，不要在上面构建）
docker build -f backend/Dockerfile -t china-fund-decision:deploy-<sha> .

# 4) 镜像内验证：akshare 版本、腾讯历史测试、alembic heads/check
# 5) 沙盘演练：独立项目/网络/副本库/独立端口跑 upgrade head + health + 401 + workspace_image_smoke
# 6) 传输：docker save | gzip | ssh 'gunzip | docker load'
# 7) 切换：停旧容器（保留）→ compose --env-file .env -f new.yml up -d → 等 healthy
# 8) 上线核验：本机 8080 + 公网 health、未认证 401、CSP、api/worker 日志无 error、restarts=0
```

部署硬规则：编排文件从上一版已验证规格派生并 `diff` 留痕；身份环境变量（生产者 sha）不随应用镜像改动；旧镜像与旧容器保留到下次发布；回滚 = `compose down` + `docker start` 旧容器（零迁移时无需迁移文件旁挂）。

## 二、错误记录与解决方案（持续追加，最新在上）

| 日期 | 错误现象 | 根因 | 解决方案 | 预防 |
| --- | --- | --- | --- | --- |
| 2026-11-14 | Windows 全量 pytest 两处预存失败：`test_structure_weight_replay` 多用例（代码抛 `frozen_formula_source_changed_review_required`，测试期望 `source_code_identity_mismatch`）、`test_historical_archive[symlink]` | 前者高度疑似 CRLF 检出改变冻结公式文件哈希（CI ubuntu 绿、Windows 挂）；后者为 Windows 符号链接权限。均已在 main `1c0fd6d` 上复现 = 预存，非新改动引入 | 未改（语义裁决留 structure 负责人）；部署判读按"CI 绿 + Windows 环境类"放行并记录 | Windows 涉及文件哈希/符号链接的测试失败先与 main 对照定性，再决定是否阻断 |
| 2026-11-08 | 沙盘演练起 API 失败：`生产环境必须配置已存在的 OCR_TRANSIENT_ROOT`，随后 `local_paddle 必须配置已存在的 OCR_LOCAL_MODEL_DIR` | `APP_ENV=production` 时配置校验要求 OCR 相关目录存在且私有；生产编排靠 tmpfs 与挂载满足 | 演练时补 tmpfs `/var/lib/china-fund-decision/ocr-transient` + `OCR_TRANSIENT_ROOT`，并显式 `OCR_MODE=disabled`（生产规格本就完整） | 本地演练若用 `APP_ENV=production`，必须一并带上生产的 OCR 环境变量与 tmpfs，否则会误判镜像有问题 |
| 2026-11-07 | docs 重组后 `test_password_auth::test_deployment_handoffs…` 失败 | 该测试断言 6 份部署文档存在且含认证标记，其中 2 份 V070 文档在删除清单内；引用扫描输出被截断漏检 | 测试文档清单改为 4 份活文档（ALIYUN 移至 docs/guides/，已验证全部承载 6 个标记） | 引用扫描不得截断输出；删除文档前对 `backend/tests` 全量 grep 文件名 |
| 2026-11-07 | ✅已修复：下行 PR63 timeout 守卫回归 | — | 守卫已改为 `not kwargs.get('timeout')` 并合入 main（fix/bounded-tencent-timeout-20261107）；`test_tencent_history_freshness` 恢复通过 | 同下 |
| 2026-11-07 | 拉取 PR #63 后 `test_tencent_history_freshness` 失败（timeout 记录为 None） | akshare 1.18.94 的 `stock_zh_a_hist_tx` 内部总是显式传 `timeout=None`，而 `_BoundedTencentRequests` 的注入守卫 `'timeout' not in kwargs` 只判断键存在，导致传输层超时没注入 | 守卫改为 `not kwargs.get('timeout')`（None 视为未设置；调用者显式正值保留）——待修复 | 传输层改动后必须跑全量 pytest；注意 `akshare>=1.17.0` 无上界，函数行为随版本漂移 |
| 2026-11-07 | pytest 直接收集失败 `ModuleNotFoundError: No module named 'sqlalchemy'` | 用了系统 Python 而不是项目 `.venv` | 统一用 `.venv/Scripts/python.exe -m pytest` | 见第一部分步骤 0 |
| 2026-11-07 | 研究库 `daily_bars` 出现 ±50%~+221% 单日"收益"（512480/512200/516160/513100 等 11 只） | 份额拆分/合并未复权，provider 的 `close/pre_close/pct_change` 都带伪影 | 分析侧按交易所涨跌幅界限确定性剔除（非跨境 ±20.5%、QDII ±30%），不修复猜测；接入侧建议加价格界限校验+拆分因子修复 | 数据摄入管道加界限校验；口径冲突按 AGENTS.md 停止信号 |
| 2026-11-06 | codex-project-hub 上报连接拒绝（WinError 10061） | Hub 服务未运行 | 保留 pending JSON，停止自动重试，人工恢复后再报（契约要求） | 收尾时先探活再批量上报 |
| 2026-10-25 | 周末网站空白事件 | 周末无结算数据触发 board-only 临时路径 | 见 `docs/audits/INCIDENT_20261025_WEEKEND_BLANK_SITE.md`；缺口问题仍 OPEN | 周末空窗缺口修复前排期 |

## 三、本文件维护规则

- 错误表**只追加不删改**历史行；撤销某条结论时新加一行说明。
- 新增必执行步骤时同步更新 AGENTS.md（如有冲突以 AGENTS.md 为准）。
- 步骤全部通过才允许提交；跳过的步骤必须在提交说明里写明原因。
